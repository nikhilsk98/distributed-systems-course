package main

import (
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
)

const (
	totalProducts   = 100000
	checksPerSearch = 100
	maxResults      = 20
)

var brands = []string{"Alpha", "Beta", "Gamma", "Delta", "Omega", "Nova", "Apex", "Zen"}

var categories = []string{
	"Electronics", "Books", "Home", "Garden", "Toys",
	"Sports", "Clothing", "Beauty", "Automotive", "Grocery",
}

type SearchProduct struct {
	ProductID    int    `json:"product_id"`
	Name         string `json:"name"`
	SKU          string `json:"sku"`
	Manufacturer string `json:"manufacturer"`
	CategoryID   int    `json:"category_id"`
	Weight       int    `json:"weight"`
	SomeOtherID  int    `json:"some_other_id"`
}

var catalog sync.Map

func loadCatalog() {
	for i := 1; i <= totalProducts; i++ {
		brand := brands[i%len(brands)]
		p := SearchProduct{
			ProductID:    i,
			Name:         fmt.Sprintf("Product %s %d", brand, i),
			SKU:          fmt.Sprintf("SKU-%06d", i),
			Manufacturer: brand,
			CategoryID:   i % len(categories),
			Weight:       100 + i%900,
			SomeOtherID:  (i * 7) % 1000,
		}
		catalog.Store(i, p)
	}
}

func searchProducts(c *gin.Context) {
	query := strings.TrimSpace(c.Query("q"))
	if query == "" {
		c.JSON(http.StatusBadRequest, gin.H{
			"error":   "INVALID_INPUT",
			"message": "query parameter q is required",
		})
		return
	}

	needle := strings.ToLower(query)
	start := time.Now()

	results := make([]SearchProduct, 0, maxResults)
	totalCount := 0
	checked := 0

	catalog.Range(func(_, value any) bool {
		p := value.(SearchProduct)
		checked++

		nameHit := strings.Contains(strings.ToLower(p.Name), needle)
		categoryHit := strings.Contains(strings.ToLower(categories[p.CategoryID]), needle)

		if nameHit || categoryHit {
			totalCount++
			if len(results) < maxResults {
				results = append(results, p)
			}
		}

		return checked < checksPerSearch
	})

	elapsed := time.Since(start)

	c.Header("X-Products-Checked", strconv.Itoa(checked))
	c.JSON(http.StatusOK, gin.H{
		"products":    results,
		"total_count": totalCount,
		"search_time": elapsed.String(),
	})
}

func healthCheck(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"status": "ok"})
}