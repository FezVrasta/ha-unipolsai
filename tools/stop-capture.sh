#!/usr/bin/env bash
# Unset the emulator proxy and stop mitmdump.
set -euo pipefail

adb shell settings put global http_proxy :0 2>/dev/null || true
adb shell settings delete global http_proxy 2>/dev/null || true
echo "emulator proxy cleared"

pkill -f 'mitmdump.*8080' 2>/dev/null && echo "mitmdump stopped" || echo "mitmdump not running"
