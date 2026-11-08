// Lambda order processor: invoked directly by SNS, same 3s simulated payment.
package main

import (
	"context"
	"encoding/json"
	"log"
	"time"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
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

func handler(ctx context.Context, ev events.SNSEvent) error {
	for _, rec := range ev.Records {
		var o Order
		if err := json.Unmarshal([]byte(rec.SNS.Message), &o); err != nil {
			log.Printf("bad message %s: %v", rec.SNS.MessageID, err)
			continue
		}
		start := time.Now()
		time.Sleep(3 * time.Second) // simulated payment processing
		o.Status = "completed"
		log.Printf("processed order %s customer=%d items=%d in %s", o.OrderID, o.CustomerID, len(o.Items), time.Since(start))
	}
	return nil
}

func main() { lambda.Start(handler) }
