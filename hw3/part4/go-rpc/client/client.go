package main

import (
	"bufio"
	"fmt"
	"net"
	"os"
	"strings"
)

func main() {
	conn, err := net.Dial("tcp4", "localhost:8080")
	if err != nil {
		fmt.Print("Error connecting!")
	}
	fmt.Fprintf(conn, "DUMP\n")
	input_reader := bufio.NewReader(conn)
	msg, err := input_reader.ReadString('\n')
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to read message from connection: %v", err.Error())
		return
	}
	msg = strings.TrimRight(msg, "\n")
	for {
		msg, _ := input_reader.ReadString('\n')
		msg = strings.TrimRight(msg, "\n")
		if strings.Contains(msg, "END") {
			break
		}
		fmt.Println(msg)
	}
	fmt.Fprintf(conn, "GET 1\n")
	msg, _ = input_reader.ReadString('\n')
	msg = strings.TrimRight(msg, "\n")
	fmt.Printf("\"%v\"\n", msg)

	fmt.Fprintf(conn, "STORE title:author:24.99\n")
	msg, _ = input_reader.ReadString('\n')
	fmt.Printf("\"%v\"\n", msg)

	fmt.Fprintf(conn, "SEARCH Blue\n")
	msg, _ = input_reader.ReadString('\n')
	msg = strings.TrimRight(msg, "\n")
	for {
		msg, _ := input_reader.ReadString('\n')
		msg = strings.TrimRight(msg, "\n")
		if strings.Contains(msg, "END") {
			break
		}
		fmt.Println(msg)
	}

	fmt.Fprintf(conn, "DUMP\n")
	msg, _ = input_reader.ReadString('\n')
	msg = strings.TrimRight(msg, "\n")
	for {
		msg, _ := input_reader.ReadString('\n')
		msg = strings.TrimRight(msg, "\n")
		if strings.Contains(msg, "END") {
			break
		}
		fmt.Println(msg)
	}
	fmt.Fprintf(conn, "CLOSE\n")
	conn.Close()

}
