# Same pattern as Part II: compile natively on the Mac, cross-compile for the
# target platform (linux/amd64 for Fargate). go mod tidy downloads the AWS SDK.
FROM --platform=$BUILDPLATFORM golang:alpine AS build
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
COPY . .
RUN [ -f go.mod ] || go mod init mapreduce
RUN go mod tidy
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build -o /worker .

FROM alpine:3.20
# CA certificates so the worker can talk to S3 over HTTPS
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=build /worker /worker
EXPOSE 8080
ENTRYPOINT ["/worker"]
