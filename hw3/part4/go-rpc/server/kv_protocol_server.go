package main

/*
 * Implemenation of the KV_PROTOCOL over a TCP connection.
 * All albums are stored in a different file to separate communication
 * from how storage is handled.
 */

import (
	"bufio"
	"fmt"
	"net"
	"os"
	"strconv"
	"strings"

	"example.com/go-rpc/albums"
)

/*
* Processses all requests from the given connection as per
* the KV_PROTOCOL.

* INPUT: the bi-directional communication to a client
* SIDE-EFFECTS: Can add to the album storage for the server
 */
func Handle_client(conn net.Conn) {
	defer conn.Close() // Will close the connection when Handle_client ends

	input_reader := bufio.NewReader(conn)
	for {
		msg, err := input_reader.ReadString('\n')
		if err != nil {
			fmt.Fprintf(os.Stderr, "Failed to read message from connection: %v", err.Error())
			return
		}

		quit := process_message(input_reader, conn, strings.TrimRight(msg, "\n"))
		if quit {
			return
		}
	}
}

/*
 * Processes a single message from the client.
 *
* INPUT: input_reader: the buffer with input from the connection
*        conn        : the connection with the client
*        msg         : the message to process from the client
* OUTPUT: Returns true if and only if the server must stop communicating with the client
* SIDE-EFFECTS: Sends a message of success or failure to the client via conn
*/
func process_message(input_reader *bufio.Reader, conn net.Conn, msg string) bool {
	command := strings.Split(msg, " ")[0]
	switch command {
	case "STORE":
		{
			album_data := strings.Split(msg, " ")[1]
			process_store_command(album_data, conn)
		}
	case "GET":
		{
			id := strings.TrimRight(strings.Split(msg, " ")[1], "\n")
			process_get_command(id, conn)
		}
	case "DUMP":
		{
			send_albums(conn, albums.Retrieve_all())
		}
	case "CLOSE":
		{
			send_message_to(conn, "CLOSE")
			return true
		}
	case "SEARCH":
		{
			phrase := strings.Join(strings.Split(msg, " ")[1:], " ")
			phrase = strings.TrimRight(phrase, "\n")
			process_search_command(phrase, conn)
		}
	default:
		{
			fmt.Printf("Received unknown command: %v\n", msg)
			send_message_to(conn, "ERR Unknown command sent")
		}
	}
	return false
}

// ///////////////// PROCESS COMMANDS ///////////////////////////

/*
* Reads the id sent as per the KV_PROTOCOL
* and either sends back the album or an error message.
* If an error occurs during the implementation the appropriate
* error message is sent and the command ceases to be processed.
*
* INPUT: id.         : the id of the album
*        conn        : the connection with the client
* SIDE-EFFECTS: Sends a message of success or failure to the client via conn
 */
func process_get_command(id string, conn net.Conn) {
	album, err := albums.Retrieve_by_id(id)
	if err != nil {
		send_message_to(conn, "ERR album not found for "+id)
	}
	send_album_to(conn, *album)
}

/*
* Reads the search phrase as per the KV_PROTOCOL
* and either sends back all albums with titles that contain the phrase
* or an error message.
* If an error occurs during the implementation the appropriate
* error message is sent and the command ceases to be processed.
*
* INPUT: phrase      : the phrase to search for
*        conn        : the connection with the client
* SIDE-EFFECTS: Sends a message of success or failure to the client via conn
 */
func process_search_command(phrase string, conn net.Conn) {
	filtered_albums := albums.Search_titles_with_phrase(phrase)
	fmt.Fprintf(os.Stderr, "%v\n", filtered_albums)
	send_albums(conn, filtered_albums)
}

/*
* Reads the album information sent as per the KV_PROTOCOL.
* If the album is already present or newly stored, sends back the id
* of the album as success.
* If an error occurs during the implementation the appropriate
* error message is sent and the command ceases to be processed.
*
* INPUT: album_data  : the album to store in title:author:price format
*        conn        : the connection with the client
* SIDE-EFFECTS: Sends a message of success with the album ID
*               or failure to the client via conn
*               If the album is not present, the album is added to the storage
 */
func process_store_command(album_data string, conn net.Conn) {
	album_parts := strings.Split(album_data, ":")
	if len(album_parts) != 3 {
		send_message_to(conn, "ERR invalid album data format")
	}

	title := album_parts[0]
	artist := album_parts[1]
	priceStr := album_parts[2]
	price, err := strconv.ParseFloat(priceStr, 64)
	if err != nil {
		send_message_to(conn, "ERR price is not a valid float")
		return
	}
	id := albums.Store_album(title, artist, price)
	fmt.Fprintf(os.Stderr, "ID %v\n", fmt.Sprintf("%v", id))
	send_message_to(conn, fmt.Sprintf("%v", id))
}

// ///////////////// COMMUNICATION UTILITIES ///////////////////////////
func send_album_to(conn net.Conn, album albums.Album) {
	send_message_to(conn,
		fmt.Sprintf("%v:%v:%v", album.Title(), album.Artist(), album.Price()))
}

func send_albums(conn net.Conn, albums []albums.Album) {
	send_message_to(conn, "START")
	for _, album := range albums {
		send_album_to(conn, album)
	}
	send_message_to(conn, "END")
}

func send_message_to(conn net.Conn, message string) {
	fmt.Fprintln(conn, message)
}
