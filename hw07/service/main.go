// Order API: synchronous vs asynchronous order processing.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"os"
	"strconv"
	"sync/atomic"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/sns"
)

type Item struct {
	ProductID string  `json:"product_id"`
	Quantity  int     `json:"quantity"`
	Price     float64 `json:"price"`
}

type Order struct {
	OrderID    string    `json:"order_id"`
	CustomerID int       `json:"customer_id"`
	Status     string    `json:"status"` // pending, processing, completed
	Items      []Item    `json:"items"`
	CreatedAt  time.Time `json:"created_at"`
}

// paymentSlots models the external payment processor's limited capacity.
// A buffered channel acts as a semaphore: only cap(paymentSlots) payments can be
// in flight at once; every other request blocks waiting for a slot.
var paymentSlots chan struct{}

var paymentDelay = 3 * time.Second

var (
	snsClient *sns.Client
	topicARN  string
	inflight  atomic.Int64
	waiting   atomic.Int64
)

func processPayment(ctx context.Context) error {
	waiting.Add(1)
	select {
	case paymentSlots <- struct{}{}:
		waiting.Add(-1)
	case <-ctx.Done():
		waiting.Add(-1)
		return ctx.Err()
	}
	inflight.Add(1)
	defer func() { <-paymentSlots; inflight.Add(-1) }()
	time.Sleep(paymentDelay)
	return nil
}

func newOrderID() string {
	return fmt.Sprintf("ord-%d-%06d", time.Now().UnixNano(), rand.Intn(1000000))
}

func decodeOrder(r *http.Request) (Order, error) {
	var o Order
	if r.Body != nil && r.ContentLength != 0 {
		if err := json.NewDecoder(r.Body).Decode(&o); err != nil {
			return o, err
		}
	}
	if o.OrderID == "" {
		o.OrderID = newOrderID()
	}
	if o.CreatedAt.IsZero() {
		o.CreatedAt = time.Now().UTC()
	}
	return o, nil
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func syncHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	start := time.Now()
	o, err := decodeOrder(r)
	if err != nil {
		http.Error(w, "bad order: "+err.Error(), http.StatusBadRequest)
		return
	}
	o.Status = "processing"
	if err := processPayment(r.Context()); err != nil {
		http.Error(w, "payment cancelled: "+err.Error(), http.StatusServiceUnavailable)
		return
	}
	o.Status = "completed"
	writeJSON(w, http.StatusOK, map[string]any{
		"order":      o,
		"latency_ms": time.Since(start).Milliseconds(),
	})
}

func asyncHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	o, err := decodeOrder(r)
	if err != nil {
		http.Error(w, "bad order: "+err.Error(), http.StatusBadRequest)
		return
	}
	o.Status = "pending"
	body, _ := json.Marshal(o)
	if snsClient == nil {
		http.Error(w, "SNS not configured", http.StatusInternalServerError)
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()
	if _, err := snsClient.Publish(ctx, &sns.PublishInput{
		TopicArn: aws.String(topicARN),
		Message:  aws.String(string(body)),
	}); err != nil {
		log.Printf("sns publish failed: %v", err)
		http.Error(w, "publish failed", http.StatusBadGateway)
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"order_id": o.OrderID, "status": o.Status})
}

func healthHandler(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"status":           "ok",
		"payments_active":  inflight.Load(),
		"payments_waiting": waiting.Load(),
	})
}

func envInt(k string, def int) int {
	if v, err := strconv.Atoi(os.Getenv(k)); err == nil && v > 0 {
		return v
	}
	return def
}

func main() {
	paymentSlots = make(chan struct{}, envInt("PAYMENT_CONCURRENCY", 1))
	paymentDelay = time.Duration(envInt("PAYMENT_DELAY_MS", 3000)) * time.Millisecond
	topicARN = os.Getenv("SNS_TOPIC_ARN")
	if topicARN != "" {
		cfg, err := config.LoadDefaultConfig(context.Background())
		if err != nil {
			log.Fatalf("aws config: %v", err)
		}
		snsClient = sns.NewFromConfig(cfg)
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/orders/sync", syncHandler)
	mux.HandleFunc("/orders/async", asyncHandler)
	mux.HandleFunc("/health", healthHandler)
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	log.Printf("order-api listening on :%s payment_concurrency=%d delay=%s topic=%q",
		port, cap(paymentSlots), paymentDelay, topicARN)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}
