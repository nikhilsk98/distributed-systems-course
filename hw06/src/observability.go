package main

import (
	"log/slog"
	"os"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var requestCount = prometheus.NewCounterVec(
	prometheus.CounterOpts{
		Name: "product_http_requests_total",
		Help: "Total API requests by method, endpoint, and status.",
	},
	[]string{"method", "endpoint", "status"},
)

var errorCount = prometheus.NewCounterVec(
	prometheus.CounterOpts{
		Name: "product_http_errors_total",
		Help: "Total API responses outside the 2xx range.",
	},
	[]string{"method", "endpoint"},
)

var requestDuration = prometheus.NewHistogramVec(
	prometheus.HistogramOpts{
		Name: "product_http_request_duration_seconds",
		Help: "API request duration in seconds.",
		Buckets: []float64{
			0.0001, 0.0005, 0.001, 0.005,
			0.01, 0.025, 0.05, 0.1,
			0.25, 0.5, 1, 2.5, 5, 10,
		},
	},
	[]string{"method", "endpoint"},
)

func configureObservability(router *gin.Engine) {
	prometheus.MustRegister(
		requestCount,
		errorCount,
		requestDuration,
	)

	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	// Register before recovery so recovered 500s are recorded too.
	router.Use(func(c *gin.Context) {
		start := time.Now()
		c.Next()

		duration := time.Since(start)
		endpoint := c.FullPath()
		if endpoint == "" {
			endpoint = "unmatched"
		}

		status := c.Writer.Status()
		method := c.Request.Method

		// Log every request as JSON.
		logger.Info("http_request",
			"method", method,
			"endpoint", endpoint,
			"status", status,
			"duration_ms", float64(duration)/float64(time.Millisecond),
		)

		// Keep monitoring scrapes out of API traffic metrics.
		if endpoint == "/metrics" {
			return
		}

		requestCount.WithLabelValues(
			method, endpoint, strconv.Itoa(status),
		).Inc()

		// Initialize the error series even when there are no errors.
		errors := errorCount.WithLabelValues(method, endpoint)
		if status < 200 || status >= 300 {
			errors.Inc()
		}

		requestDuration.WithLabelValues(
			method, endpoint,
		).Observe(duration.Seconds())
	})

	router.GET("/metrics", gin.WrapH(promhttp.Handler()))
}
