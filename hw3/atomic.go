package main

import (
	"fmt"
	"sync"
	"sync/atomic"
)

func main() {

	var regularCounter int64
	var atomicCounter int64

	var wg sync.WaitGroup

	for i := 0; i < 1000; i++ {

		wg.Add(1)

		go func() {
			defer wg.Done()

			for j := 0; j < 1000; j++ {

				// Normal increment
				regularCounter++

				// Atomic increment
				atomic.AddInt64(&atomicCounter, 1)
			}
		}()
	}

	wg.Wait()

	fmt.Println("Expected:", 1000000)
	fmt.Println("Regular Counter:", regularCounter)
	fmt.Println("Atomic Counter:", atomicCounter)
}