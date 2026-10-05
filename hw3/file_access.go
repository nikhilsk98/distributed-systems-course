package main

import (
	"bufio"
	"fmt"
	"os"
	"time"
)

func unbufferedWrite() time.Duration {
	f, _ := os.Create("unbuffered.txt")
	defer f.Close()

	start := time.Now()

	for i := 0; i < 100000; i++ {
		f.Write([]byte(fmt.Sprintf("Line %d\n", i)))
	}

	return time.Since(start)
}

func bufferedWrite() time.Duration {
	f, _ := os.Create("buffered.txt")
	defer f.Close()

	writer := bufio.NewWriter(f)

	start := time.Now()

	for i := 0; i < 100000; i++ {
		writer.WriteString(fmt.Sprintf("Line %d\n", i))
	}

	writer.Flush()

	return time.Since(start)
}

func main() {
	fmt.Println("Unbuffered:", unbufferedWrite())
	fmt.Println("Buffered:", bufferedWrite())
}