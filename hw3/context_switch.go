package main

import (
	"fmt"
	"runtime"
	"time"
)

func runTest(procs int) {
	runtime.GOMAXPROCS(procs)

	const n = 1000000

	ping := make(chan struct{})
	pong := make(chan struct{})

	start := time.Now()

	go func() {
		for i := 0; i < n; i++ {
			<-ping
			pong <- struct{}{}
		}
	}()

	for i := 0; i < n; i++ {
		ping <- struct{}{}
		<-pong
	}

	elapsed := time.Since(start)

	avg := elapsed / time.Duration(2*n)

	fmt.Println("GOMAXPROCS:", procs)
	fmt.Println("Total time:", elapsed)
	fmt.Println("Average switch time:", avg)
	fmt.Println()
}

func main() {
	runTest(1)
	runTest(runtime.NumCPU())
}