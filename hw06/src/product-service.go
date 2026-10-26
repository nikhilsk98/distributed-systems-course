package main

import (
	"net/http"
	"os"
	"strconv"
	"sync"

	"github.com/gin-gonic/gin"
)

// Product matches the Product schema in api.yaml.
// Weight uses a pointer: 0 is valid, but a missing weight is not.
type Product struct {
	ProductID    int32  `json:"product_id" binding:"required,min=1"`
	SKU          string `json:"sku" binding:"required,min=1,max=100"`
	Manufacturer string `json:"manufacturer" binding:"required,min=1,max=200"`
	CategoryID   int32  `json:"category_id" binding:"required,min=1"`
	Weight       *int32 `json:"weight" binding:"required,min=0"`
	SomeOtherID  int32  `json:"some_other_id" binding:"required,min=1"`
}

// APIError matches the Error schema in api.yaml.
type APIError struct {
	Error   string `json:"error"`
	Message string `json:"message"`
	Details string `json:"details,omitempty"`
}

// Store products in memory and protect concurrent access.
var products = make(map[int32]Product)
var productsMu sync.RWMutex

func main() {
		loadCatalog()
	// Seed one product for testing because the specification
	// does not provide a separate catalog-creation endpoint.
	weight := int32(1250)

	products[1] = Product{
		ProductID:    1,
		SKU:          "ABC-123",
		Manufacturer: "Acme Corporation",
		CategoryID:   456,
		Weight:       &weight,
		SomeOtherID:  789,
	}

	router := gin.New()
	configureObservability(router)  //The function is defined in observability.go. used lets its middleware measure
	// downstream Product request processing, including recovered 500s.

	// Recover from panics and return the specified JSON error.
	// This must come before the controlled failure middleware.
	router.Use(gin.CustomRecovery(func(c *gin.Context, recovered any) {
		c.AbortWithStatusJSON(
			http.StatusInternalServerError,
			APIError{
				Error:   "INTERNAL_SERVER_ERROR",
				Message: "An unexpected server error occurred",
			},
		)
	}))

	// Controlled failure test.
	// Both the environment flag and request header are required.
	enableFailureTests := os.Getenv("ENABLE_FAILURE_TESTS") == "true"

	router.Use(func(c *gin.Context) {
		if enableFailureTests &&
			c.GetHeader("X-Test-Failure") == "true" {
			panic("intentional test failure")
		}

		c.Next()
	})

	//Register GET/POST endpopints
	router.GET("/products/:productId", getProduct)
	router.POST("/products/:productId/details", addProductDetails)
	router.GET("/products/search", searchProducts)
	router.GET("/health", healthCheck)

	if err := router.Run(":8080"); err != nil {
		panic(err)
	}
}

// Parse and Validate the URL ID as a positive 32-bit integer for product ID.
func parseProductID(c *gin.Context) (int32, bool) {
	id, err := strconv.ParseInt(c.Param("productId"), 10, 32)

	if err != nil || id < 1 {
		return 0, false
	}

	return int32(id), true
}

// GET /products/:productId
// Return 200 for an existing product or 404 when not found.
func getProduct(c *gin.Context) {
	id, valid := parseProductID(c)

	if !valid {
		c.JSON(http.StatusNotFound, APIError{
			Error:   "NOT_FOUND",
			Message: "Product not found",
			Details: "Product ID must be a positive int32",
		})
		return
	}

	// Release the read lock before writing the response.
	productsMu.RLock()
	product, exists := products[id]
	productsMu.RUnlock()

	if !exists {
		c.JSON(http.StatusNotFound, APIError{
			Error:   "NOT_FOUND",
			Message: "Product not found",
		})
		return
	}

	c.JSON(http.StatusOK, product)
}

// POST /products/:productId/details
// Update an existing product after validating the request.
// Return 204 on success, 400 for invalid input, or 404 if absent.
func addProductDetails(c *gin.Context) {
	id, valid := parseProductID(c)

	if !valid {
		c.JSON(http.StatusBadRequest, APIError{
			Error:   "INVALID_INPUT",
			Message: "Invalid product ID",
			Details: "Product ID must be a positive int32",
		})
		return
	}

	var product Product

	if err := c.ShouldBindJSON(&product); err != nil { //Decode the incoming JSON into product.
		c.JSON(http.StatusBadRequest, APIError{
			Error:   "INVALID_INPUT",
			Message: "Invalid product data",
			Details: err.Error(),
		})
		return
	}

	//We check that the URL and body refer to the same product before updating the map.
	if product.ProductID != id {
		c.JSON(http.StatusBadRequest, APIError{
			Error:   "INVALID_INPUT",
			Message: "Body product_id must match the URL productId",
		})
		return
	}

	// Check and update within one exclusive lock.
	productsMu.Lock()
	_, exists := products[id]

	if exists {
		products[id] = product
	}

	productsMu.Unlock()

	if !exists {
		c.JSON(http.StatusNotFound, APIError{
			Error:   "NOT_FOUND",
			Message: "Product not found",
		})
		return
	}

	// A 204 response has no body.
	c.Status(http.StatusNoContent)
}
