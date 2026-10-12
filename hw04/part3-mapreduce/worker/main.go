// MapReduce word-count worker.
//
// One small Go program exposes all three MapReduce roles over HTTP:
//
//	GET /split?url=s3://bucket/key&n=3   -> splits the file into n chunks in S3
//	GET /map?url=s3://bucket/chunk       -> counts words in one chunk, writes JSON to S3
//	GET /reduce?urls=s3://a,s3://b,...   -> merges mapper JSON files into final counts
//	GET /health                          -> liveness check
//
// Every ECS task runs this same image; the driver decides which task acts as
// the splitter, which ones are mappers, and which one is the reducer.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path"
	"strconv"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

var (
	s3c      *s3.Client
	hostname string
)

// timings is returned by every endpoint so the driver can see where time goes.
type timings struct {
	DownloadMs float64 `json:"download_ms"`
	ComputeMs  float64 `json:"compute_ms"`
	UploadMs   float64 `json:"upload_ms"`
	TotalMs    float64 `json:"total_ms"`
}

func ms(d time.Duration) float64 { return float64(d.Microseconds()) / 1000.0 }

// A "word" is a maximal run of ASCII letters/digits, lowercased.
// driver.py uses exactly the same rule (regex [A-Za-z0-9]+) to verify results.
func isWordByte(c byte) bool {
	return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')
}

// ---------- S3 helpers ----------

func parseS3URL(raw string) (string, string, error) {
	if !strings.HasPrefix(raw, "s3://") {
		return "", "", fmt.Errorf("expected s3://bucket/key, got %q", raw)
	}
	rest := strings.TrimPrefix(raw, "s3://")
	i := strings.Index(rest, "/")
	if i <= 0 || i == len(rest)-1 {
		return "", "", fmt.Errorf("expected s3://bucket/key, got %q", raw)
	}
	return rest[:i], rest[i+1:], nil
}

func s3URL(bucket, key string) string { return "s3://" + bucket + "/" + key }

func getObject(ctx context.Context, bucket, key string) ([]byte, error) {
	out, err := s3c.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return nil, fmt.Errorf("get s3://%s/%s: %w", bucket, key, err)
	}
	defer out.Body.Close()
	return io.ReadAll(out.Body)
}

func putObject(ctx context.Context, bucket, key string, data []byte, contentType string) error {
	_, err := s3c.PutObject(ctx, &s3.PutObjectInput{
		Bucket:      aws.String(bucket),
		Key:         aws.String(key),
		Body:        bytes.NewReader(data),
		ContentType: aws.String(contentType),
	})
	if err != nil {
		return fmt.Errorf("put s3://%s/%s: %w", bucket, key, err)
	}
	return nil
}

// ---------- HTTP helpers ----------

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func writeErr(w http.ResponseWriter, status int, err error) {
	log.Printf("error: %v", err)
	writeJSON(w, status, map[string]string{"error": err.Error(), "host": hostname})
}

// ---------- core logic ----------

// splitChunks cuts data into n roughly equal byte ranges. Each cut point is
// moved forward to the next non-word byte so no word is split across chunks.
func splitChunks(data []byte, n int) [][]byte {
	chunks := make([][]byte, 0, n)
	start := 0
	for i := 1; i <= n; i++ {
		if start >= len(data) {
			chunks = append(chunks, []byte{})
			continue
		}
		if i == n {
			chunks = append(chunks, data[start:])
			break
		}
		end := len(data) * i / n
		if end < start {
			end = start
		}
		for end < len(data) && isWordByte(data[end]) {
			end++
		}
		chunks = append(chunks, data[start:end])
		start = end
	}
	return chunks
}

// countWords returns word -> count and the total number of words.
func countWords(data []byte) (map[string]int, int) {
	counts := make(map[string]int)
	total := 0
	buf := make([]byte, 0, 32)
	for i := 0; i <= len(data); i++ {
		if i < len(data) && isWordByte(data[i]) {
			c := data[i]
			if c >= 'A' && c <= 'Z' {
				c += 'a' - 'A'
			}
			buf = append(buf, c)
			continue
		}
		if len(buf) > 0 {
			counts[string(buf)]++
			total++
			buf = buf[:0]
		}
	}
	return counts, total
}

// jobs/<id>/chunks/chunk-000.txt -> jobs/<id>/maps/chunk-000.json
func mapOutputKey(key string) string {
	stem := strings.TrimSuffix(key, path.Ext(key))
	if strings.Contains(stem, "/chunks/") {
		return strings.Replace(stem, "/chunks/", "/maps/", 1) + ".json"
	}
	return stem + ".counts.json"
}

// jobs/<id>/maps/chunk-000.json -> jobs/<id>/final.json
func reduceOutputKey(key string) string {
	if i := strings.Index(key, "/maps/"); i >= 0 {
		return key[:i] + "/final.json"
	}
	d := path.Dir(key)
	if d == "." {
		return "final.json"
	}
	return d + "/final.json"
}

// ---------- handlers ----------

func handleSplit(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	q := r.URL.Query()
	bucket, key, err := parseS3URL(q.Get("url"))
	if err != nil {
		writeErr(w, http.StatusBadRequest, err)
		return
	}
	n := 3
	if v := q.Get("n"); v != "" {
		n, err = strconv.Atoi(v)
		if err != nil || n < 1 || n > 1000 {
			writeErr(w, http.StatusBadRequest, fmt.Errorf("n must be an integer from 1 to 1000"))
			return
		}
	}

	t0 := time.Now()
	data, err := getObject(r.Context(), bucket, key)
	if err != nil {
		writeErr(w, http.StatusBadGateway, err)
		return
	}
	t1 := time.Now()
	chunks := splitChunks(data, n)
	t2 := time.Now()

	jobID := strconv.FormatInt(time.Now().UnixNano(), 10)
	urls := make([]string, len(chunks))
	sizes := make([]int, len(chunks))
	for i, c := range chunks {
		k := fmt.Sprintf("jobs/%s/chunks/chunk-%03d.txt", jobID, i)
		if err := putObject(r.Context(), bucket, k, c, "text/plain"); err != nil {
			writeErr(w, http.StatusBadGateway, err)
			return
		}
		urls[i] = s3URL(bucket, k)
		sizes[i] = len(c)
	}
	t3 := time.Now()

	log.Printf("split %s into %d chunks (%d bytes)", s3URL(bucket, key), n, len(data))
	writeJSON(w, http.StatusOK, map[string]any{
		"host":        hostname,
		"job_id":      jobID,
		"input_bytes": len(data),
		"chunks":      urls,
		"chunk_bytes": sizes,
		"timings": timings{
			DownloadMs: ms(t1.Sub(t0)),
			ComputeMs:  ms(t2.Sub(t1)),
			UploadMs:   ms(t3.Sub(t2)),
			TotalMs:    ms(time.Since(start)),
		},
	})
}

func handleMap(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	q := r.URL.Query()
	bucket, key, err := parseS3URL(q.Get("url"))
	if err != nil {
		writeErr(w, http.StatusBadRequest, err)
		return
	}
	outBucket, outKey := bucket, mapOutputKey(key)
	if o := q.Get("out"); o != "" {
		outBucket, outKey, err = parseS3URL(o)
		if err != nil {
			writeErr(w, http.StatusBadRequest, err)
			return
		}
	}

	t0 := time.Now()
	data, err := getObject(r.Context(), bucket, key)
	if err != nil {
		writeErr(w, http.StatusBadGateway, err)
		return
	}
	t1 := time.Now()
	counts, total := countWords(data)
	body, err := json.Marshal(counts)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, err)
		return
	}
	t2 := time.Now()
	if err := putObject(r.Context(), outBucket, outKey, body, "application/json"); err != nil {
		writeErr(w, http.StatusBadGateway, err)
		return
	}
	t3 := time.Now()

	log.Printf("mapped %s: %d words, %d unique", s3URL(bucket, key), total, len(counts))
	writeJSON(w, http.StatusOK, map[string]any{
		"host":         hostname,
		"input":        s3URL(bucket, key),
		"output":       s3URL(outBucket, outKey),
		"chunk_bytes":  len(data),
		"total_words":  total,
		"unique_words": len(counts),
		"timings": timings{
			DownloadMs: ms(t1.Sub(t0)),
			ComputeMs:  ms(t2.Sub(t1)),
			UploadMs:   ms(t3.Sub(t2)),
			TotalMs:    ms(time.Since(start)),
		},
	})
}

func handleReduce(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	q := r.URL.Query()
	raw := q.Get("urls")
	if raw == "" {
		writeErr(w, http.StatusBadRequest, fmt.Errorf("missing urls parameter (comma-separated s3:// URLs)"))
		return
	}

	merged := make(map[string]int)
	var download, compute time.Duration
	var firstBucket, firstKey string
	inputs := 0
	for _, p := range strings.Split(raw, ",") {
		p = strings.TrimSpace(p)
		if p == "" {
			continue
		}
		b, k, err := parseS3URL(p)
		if err != nil {
			writeErr(w, http.StatusBadRequest, err)
			return
		}
		if firstBucket == "" {
			firstBucket, firstKey = b, k
		}
		t0 := time.Now()
		data, err := getObject(r.Context(), b, k)
		if err != nil {
			writeErr(w, http.StatusBadGateway, err)
			return
		}
		t1 := time.Now()
		var part map[string]int
		if err := json.Unmarshal(data, &part); err != nil {
			writeErr(w, http.StatusBadGateway, fmt.Errorf("parse %s: %w", p, err))
			return
		}
		for word, c := range part {
			merged[word] += c
		}
		download += t1.Sub(t0)
		compute += time.Since(t1)
		inputs++
	}
	if inputs == 0 {
		writeErr(w, http.StatusBadRequest, fmt.Errorf("no valid urls given"))
		return
	}

	outBucket, outKey := firstBucket, reduceOutputKey(firstKey)
	if o := q.Get("out"); o != "" {
		var err error
		outBucket, outKey, err = parseS3URL(o)
		if err != nil {
			writeErr(w, http.StatusBadRequest, err)
			return
		}
	}

	t2 := time.Now()
	total := 0
	for _, c := range merged {
		total += c
	}
	body, err := json.Marshal(merged)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, err)
		return
	}
	compute += time.Since(t2)
	t3 := time.Now()
	if err := putObject(r.Context(), outBucket, outKey, body, "application/json"); err != nil {
		writeErr(w, http.StatusBadGateway, err)
		return
	}
	upload := time.Since(t3)

	log.Printf("reduced %d inputs: %d words, %d unique", inputs, total, len(merged))
	writeJSON(w, http.StatusOK, map[string]any{
		"host":         hostname,
		"inputs":       inputs,
		"output":       s3URL(outBucket, outKey),
		"total_words":  total,
		"unique_words": len(merged),
		"timings": timings{
			DownloadMs: ms(download),
			ComputeMs:  ms(compute),
			UploadMs:   ms(upload),
			TotalMs:    ms(time.Since(start)),
		},
	})
}

func main() {
	region := os.Getenv("AWS_REGION")
	if region == "" {
		region = "us-west-2"
	}
	cfg, err := config.LoadDefaultConfig(context.Background(), config.WithRegion(region))
	if err != nil {
		log.Fatalf("loading AWS config: %v", err)
	}
	s3c = s3.NewFromConfig(cfg)
	hostname, _ = os.Hostname()

	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok", "host": hostname})
	})
	http.HandleFunc("/split", handleSplit)
	http.HandleFunc("/map", handleMap)
	http.HandleFunc("/reduce", handleReduce)

	srv := &http.Server{Addr: ":8080", ReadHeaderTimeout: 10 * time.Second}
	log.Printf("mapreduce worker listening on :8080 (region %s)", region)
	log.Fatal(srv.ListenAndServe())
}
