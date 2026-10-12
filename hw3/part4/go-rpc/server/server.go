package main

/*
 * Entry point for the server program that implements the KV_PROTOCOL.
 * Defaults to serving on port 8080, but can be configured via command line
 * to serve on another port.
 *
 * OPTIONAL COMMAND LINE ARGS:
 * -port=XYZ : If present and XYZ is a valid port number,
 *             changes the service port to XYZ.
 */

import (
	"fmt"
	"log"
	"net"
	"os"
	"strconv"
	"strings"
)

const DEFAULT_PORT = 8080

func main() {

	args := os.Args[1:] //Removes program name

	port := DEFAULT_PORT
	if len(args) > 0 {
		port = extract_port_number(args)
	}

	// Listen for a connection
	ln, err := net.Listen("tcp", fmt.Sprintf(":%v", port))
	if err != nil {
		fmt.Println("Failed to listen")
	}

	fmt.Printf("Listening on port %v\n", port)

	// Accept the first connection
	conn, err := ln.Accept()
	if err != nil {
		fmt.Println("Error in accepting")
	}

	Handle_client(conn)
}

// Finds the first occurence of the "-port" command line argument
// and attempts to extract the port number.
//
// Returns the port number as an integer if successful.
// If not an integer or not positive, the error is logged and the program exits.
func extract_port_number(args []string) int {
	for _, arg := range args {
		if strings.Contains(arg, "-port") {
			val := strings.Split(arg, "=")[1]
			val = strings.TrimSuffix(val, "\n")
			port_num, err := strconv.Atoi(val)
			if err != nil || port_num <= 0 {
				log.Fatalf("Unknown port number: \"%v\"", port_num)
			}
		}
	}
	return DEFAULT_PORT
}
