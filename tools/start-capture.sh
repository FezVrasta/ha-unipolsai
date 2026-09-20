#!/usr/bin/env bash
# Boot the capture AVD, start mitmdump, trust its CA as a user cert, point the
# emulator at it. The app has no pinning and trusts user CAs, so that's enough.
set -euo pipefail

AVD=unipol_capture
PORT=8080
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CAPTURES="$ROOT/captures"
EMULATOR="$HOME/Library/Android/sdk/emulator/emulator"

mkdir -p "$CAPTURES"

if ! adb devices | grep -q emulator; then
  echo "booting $AVD..."
  nohup "$EMULATOR" -avd "$AVD" -no-snapshot-load -writable-system \
    -gpu swiftshader_indirect > "$CAPTURES/emulator.log" 2>&1 &
  adb wait-for-device
  until [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do
    sleep 2
  done
  echo "booted."
else
  echo "emulator already running."
fi

if pgrep -f "mitmdump.*$PORT" > /dev/null; then
  echo "mitmdump already running."
else
  FLOW="$CAPTURES/unipol-$(date +%Y%m%d-%H%M%S).flow"
  echo "starting mitmdump -> $FLOW (+ captures/flows.jsonl)"
  nohup mitmdump --listen-port "$PORT" -w "$FLOW" -s "$ROOT/tools/capture_addon.py" \
    > "$CAPTURES/mitmdump.log" 2>&1 &
  sleep 3
  echo "$FLOW" > "$CAPTURES/.current-flow"
fi

CA="$HOME/.mitmproxy/mitmproxy-ca-cert.pem"
[ -f "$CA" ] || { echo "no mitmproxy CA at $CA, run mitmproxy once first"; exit 1; }

# Android looks up user CAs by subject hash.
HASH=$(openssl x509 -inform PEM -subject_hash_old -in "$CA" | head -1)
TMP=$(mktemp -d)
cp "$CA" "$TMP/$HASH.0"
adb push "$TMP/$HASH.0" /data/local/tmp/ > /dev/null
adb shell "mkdir -p /data/misc/user/0/cacerts-added 2>/dev/null; \
           cp /data/local/tmp/$HASH.0 /data/misc/user/0/cacerts-added/ 2>/dev/null; \
           chmod 644 /data/misc/user/0/cacerts-added/$HASH.0 2>/dev/null" || true
rm -rf "$TMP"
echo "CA installed as user cert ($HASH.0)"

# 10.0.2.2 is the host as seen from inside the emulator.
adb shell settings put global http_proxy "10.0.2.2:$PORT"
echo "proxy set to 10.0.2.2:$PORT"

cat <<'EOF'

Ready. Now, on the emulator:
  1. open the Unipol app and log in
  2. open the vehicle / Unibox position screen
  3. force a position refresh
  4. open the driving statistics screen

Then run ./tools/extract-flows.sh
EOF
