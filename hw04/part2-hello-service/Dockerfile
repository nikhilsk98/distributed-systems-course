FROM --platform=$BUILDPLATFORM golang:alpine AS build
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
COPY . .
RUN [ -f go.mod ] || go mod init hello-service
RUN go mod tidy
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build -o /server .

FROM alpine:3.20
COPY --from=build /server /server
EXPOSE 8080
ENTRYPOINT ["/server"]
