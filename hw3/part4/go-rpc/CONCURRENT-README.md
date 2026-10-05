# Concurrent Server Design

Attached to this README is a server-side implementation of a custom key/value store
RPC protocol called KV_PROTOCOL. In short, it allows someone to store album data on a server and retrieve it either in bulk or via a simple word search.

The protocol and instructions on launching the server are described in depth below. Note that no client is provided, but you are not being asked to implement
anything for this exercise.

## Design Task

Your goal for this exercise is to do the following:

1. Be prepared to perform a code walk through this server code or answer
   questions about how it works.
2. Propose a design to make the server process multiple clients
   concurrently and scale up as the number of requests increase. At the moment,
   the server can only process a single client at a time. Naturally,
   this is not scalable (you should be able to explain _why_).
   
   Consider the following questions we could ask during a mock interview as
   you consider your design:
    - Does your design change the definition of the included data types?
      Why or why not?
    - Explain how your design scales as the number of requests increase.
      Does the response rate change?
    - How does your design prevent a client from being _starved_?
    - Is there a scenario that would force your design to have worst case
      behavior? If so, explain why your design allows for that scenario and
      propose a fix to the design. If not, how do you prevent any such scenario?

   We are **not** asking you to implement that design. As a result,
   there is no client side implementation. You are free to design one
   based off the protocl below. (Consider implementing and formally
   testing the design with a load test as a capstone challenge).

## KV-PROTOCOL

In this protocol, a client can send a server one of the following commands which all end with a newline (`\n`)

- `STORE title:author:price` : This command is the word "store" followed by a space and then the title, author, and price of the album all separated by colons. The title and author can be any string _including_ empty, but the price must be a string that can be converted into a float64.

If the string after store cannot be broken into title, author, and price as specified above, then the server returns the message

`ERR details\n`

where "details" is an appropriate message describing the issue with the input. This also serves as confirmation to the client the message was received.

If this combination is already an album in the server, the unique ID of the album is sent back to the client as confirmation of the completion of the command. If this combination is _not_ already an album in the server, an album is created on the server, associated with a new unique ID, and that ID is sent back to the client as confirmation of the completion of the command.

- `GET ID` : This command is the word "get" followed by a string that should be the unique ID of an album on the server.

If the ID is associated with an album, then that album is returned in the following message

`FOUND title:author:price\n`

where title, author, and price are from the album itself.

If the ID is _not_ associated with an album, then the server sends the following message

`ERR album not found for ID\n`

where ID is the ID sent from the client.

If the message is only the word "get", then the server sends the following message

`ERR Need to input an ID\n`

- `DUMP` :  This command is only the word "dump". The server returns ALL of the albums stored along with their unique IDs in the following format where each line is a message:

```
START\n
id:title:author:price\n
id:title:author:price\n
...
END\n
```

If there are no albums on the server, then there are only two messages sent:

```
START\n
END\n
```

- `SEARCH word/phrase` : This command is the word "search" followed by a word or phrase (a string that does not end in `\n` but can have spaces). The server returns all albums with this word or phrase in the title (case-sensitive) in the following format where each line is a message:

```
START\n
id:title:author:price\n
id:title:author:price\n
...
END\n
```

If no albums have that word/phrase in their title, then only two messages are sent:

```
START\n
END\n
```

Any unknown commands report the message "ERR Unknown command: %v" where "%v" is the message received.

(The protocol and data are both simple and do not use JSON, but serve to keep CPU and storage low and therefore budget costs low and demonstrates _why_ JSON is used for this kind of messaging.)

## Running the server program

The main server program can take an optional command line argument:

- port=NUMBER : If given, the NUMBER is the port to be listened to. If not given or the string is not a number, the port number for the server is 8080. If a number
is not given, unexpected behavior can occur (e.g. it can panic or still work)

For example,
- `go run server.go port=80` will run the server on port 80.
- `go run server.go` will run the server on port 8080.