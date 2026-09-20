#!/usr/bin/env bash
# Summarise captures/flows.jsonl (written by tools/capture_addon.py) and split
# it into one JSON file per endpoint under captures/parsed/.
#
# Uses only the stdlib, so it runs on the system python. The mitmproxy package
# lives in its own brew venv and isn't importable here.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JSONL="${1:-$ROOT/captures/flows.jsonl}"
OUT="$ROOT/captures/parsed"

[ -f "$JSONL" ] || {
  echo "no $JSONL yet. Run ./tools/start-capture.sh, then use the app." >&2
  exit 1
}

mkdir -p "$OUT"

python3 - "$JSONL" "$OUT" <<'PY'
import collections, json, re, sys

jsonl, out_dir = sys.argv[1], sys.argv[2]

by_path = collections.OrderedDict()
creds = {}

with open(jsonl) as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        for k in ("x-ibm-client-id", "x-ibm-client-secret", "x-unipol-tenant"):
            v = e.get("request_headers", {}).get(k)
            if v:
                creds[k] = v
        by_path.setdefault(e.get("path", "unknown"), []).append(e)

for path, entries in by_path.items():
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", path).strip("-")[:120] or "root"
    with open(f"{out_dir}/{slug}.json", "w") as fh:
        json.dump(entries, fh, indent=2, ensure_ascii=False)

print(f"{sum(len(v) for v in by_path.values())} calls across "
      f"{len(by_path)} endpoints -> {out_dir}\n")

if creds:
    print("APIC credentials captured (these go in the integration config):")
    for k, v in creds.items():
        print(f"  {k}: {v}")
else:
    print("No x-ibm-* headers seen yet. Has the app actually made a call?")

print("\nTelematics and login calls:")
hits = [p for p in by_path if "telematici" in p or p.endswith("/login")]
if hits:
    for p in hits:
        print(f"  {len(by_path[p]):3d}x  {p}")
else:
    print("  none yet; open the vehicle position screen in the app")

# The two answers the writeup is actually waiting on.
for path, entries in by_path.items():
    if not path.endswith("lastPosition"):
        continue
    for e in entries:
        loc = (e.get("response") or {}).get("lastPosition")
        if isinstance(loc, dict):
            q = loc.get("dailyFruitions") or {}
            print(f"\nlastPosition sample:")
            print(f"  date            {loc.get('date')!r}")
            print(f"  accuracy        {loc.get('accuracy')!r}")
            print(f"  pendingRequest  {loc.get('pendingRequest')!r}")
            print(f"  dailyFruitions  {q.get('current')}/{q.get('max')}")
            break
    break
PY
