#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../lambda"
mkdir -p build
GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -tags lambda.norpc -trimpath -ldflags="-s -w" -o build/bootstrap .
ls -l build/bootstrap
