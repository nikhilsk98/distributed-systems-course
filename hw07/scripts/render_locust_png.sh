#!/usr/bin/env bash
# Render every Locust HTML report to a PNG with headless Chrome.
set -euo pipefail
cd "$(dirname "$0")/../results/locust"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
mkdir -p ../screenshots
for f in *.html; do
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=1400,2600 \
    --virtual-time-budget=8000 --screenshot="$PWD/../screenshots/locust_${f%.html}.png" "file://$PWD/$f" >/dev/null 2>&1
  echo "rendered $f"
done
