// Order processor: long-polls SQS and processes each order in its own goroutine,
// bounded by a configurable worker pool.
package main

import (
	"context"
	"encoding/json"
	"log"
	"os"
	"os/signal"
	"strconv"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/aws/aws-sdk-go-v2/service/sqs/types"
)

type Item struct {
	ProductID string  `json:"product_id"`
	Quantity  int     `json:"quantity"`
	Price     float64 `json:"price"`
}

type Order struct {
	OrderID    string    `json:"order_id"`
	CustomerID int       `json:"customer_id"`
	Status     string    `json:"status"`
	Items      []Item    `json:"items"`
	CreatedAt  time.Time `json:"created_at"`
}

// snsEnvelope is the JSON wrapper SNS puts around the message when delivering to SQS
// (raw message delivery disabled).
type snsEnvelope struct {
	Type    string `json:"Type"`
	Message string `json:"Message"`
}

func envInt(k string, def int) int {
	if v, err := strconv.Atoi(os.Getenv(k)); err == nil && v > 0 {
		return v
	}
	return def
}

func parseOrder(body string) (Order, error) {
	var o Order
	var env snsEnvelope
	if err := json.Unmarshal([]byte(body), &env); err == nil && env.Message != "" {
		body = env.Message
	}
	err := json.Unmarshal([]byte(body), &o)
	return o, err
}

func main() {
	queueURL := os.Getenv("SQS_QUEUE_URL")
	if queueURL == "" {
		log.Fatal("SQS_QUEUE_URL is required")
	}
	workers := envInt("WORKER_COUNT", 1)
	delay := time.Duration(envInt("PAYMENT_DELAY_MS", 3000)) * time.Millisecond

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Fatalf("aws config: %v", err)
	}
	client := sqs.NewFromConfig(cfg)

	// Semaphore bounding the number of concurrent order-processing goroutines.
	sem := make(chan struct{}, workers)
	var wg sync.WaitGroup
	var processed, active atomic.Int64

	go func() {
		t := time.NewTicker(15 * time.Second)
		defer t.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-t.C:
				log.Printf("stats processed=%d active=%d workers=%d", processed.Load(), active.Load(), workers)
			}
		}
	}()

	log.Printf("order-processor started workers=%d delay=%s queue=%s", workers, delay, queueURL)
	for ctx.Err() == nil {
		// Only fetch as many messages as there are free workers (max 10), so messages
		// are not held invisible in memory while they wait for a worker.
		free := workers - int(active.Load())
		if free <= 0 {
			// Block until a worker frees up.
			sem <- struct{}{}
			<-sem
			continue
		}
		max := int32(10)
		if free < 10 {
			max = int32(free)
		}
		out, err := client.ReceiveMessage(ctx, &sqs.ReceiveMessageInput{
			QueueUrl:            aws.String(queueURL),
			MaxNumberOfMessages: max,
			WaitTimeSeconds:     20,
		})
		if err != nil {
			if ctx.Err() != nil {
				break
			}
			log.Printf("receive error: %v", err)
			time.Sleep(2 * time.Second)
			continue
		}
		for _, m := range out.Messages {
			sem <- struct{}{}
			active.Add(1)
			wg.Add(1)
			go func(m types.Message) {
				defer func() { <-sem; active.Add(-1); wg.Done() }()
				o, err := parseOrder(aws.ToString(m.Body))
				if err != nil {
					log.Printf("bad message %s: %v", aws.ToString(m.MessageId), err)
				}
				time.Sleep(delay) // simulated payment processing
				o.Status = "completed"
				dctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
				defer cancel()
				if _, err := client.DeleteMessage(dctx, &sqs.DeleteMessageInput{
					QueueUrl:      aws.String(queueURL),
					ReceiptHandle: m.ReceiptHandle,
				}); err != nil {
					log.Printf("delete failed for %s: %v", o.OrderID, err)
					return
				}
				processed.Add(1)
			}(m)
		}
	}
	log.Printf("shutting down, waiting for %d in-flight orders", active.Load())
	wg.Wait()
	log.Printf("stopped; processed=%d", processed.Load())
}
