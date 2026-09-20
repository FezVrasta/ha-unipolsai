"""mitmdump addon: write the interesting Unipol requests out as JSON lines.

Loaded with `mitmdump -s tools/capture_addon.py`. Runs inside mitmproxy's own
interpreter, so it needs no packages installed on the system python.

Writes to captures/flows.jsonl and prints the APIC credentials as soon as they
appear, since those are the main thing a capture session is for.
"""
import json
import os
import pathlib

KEEP = "apphub.unipolsai.it"
DROP = ("tiqcdn", "tealium", "firebase", "crashlytics", "googleapis",
        "glassbox", "clarisite", "igodigital", "app-measurement")

HEADERS_OF_INTEREST = (
    "authorization", "x-ibm-client-id", "x-ibm-client-secret",
    "x-unipol-tenant", "x-unipol-canale", "x-unipol-requestid",
    "source", "user-agent",
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "captures" / "flows.jsonl"

_seen_creds = {}


def _jsonify(raw):
    try:
        return json.loads(raw)
    except Exception:
        try:
            return raw.decode("utf-8", "replace")
        except Exception:
            return None


def response(flow):
    host = flow.request.pretty_host
    if KEEP not in host or any(d in host for d in DROP):
        return

    for h in ("x-ibm-client-id", "x-ibm-client-secret", "x-unipol-tenant"):
        v = flow.request.headers.get(h)
        if v and _seen_creds.get(h) != v:
            _seen_creds[h] = v
            print(f"[apic] {h}: {v}")

    entry = {
        "method": flow.request.method,
        "url": flow.request.pretty_url,
        "path": flow.request.path.split("?")[0],
        "status": flow.response.status_code,
        "request_headers": {
            k.lower(): v for k, v in flow.request.headers.items()
            if k.lower() in HEADERS_OF_INTEREST
        },
        "request_body": _jsonify(flow.request.content) if flow.request.content else None,
        "response": _jsonify(flow.response.content) if flow.response.content else None,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "a") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    if "telematici" in entry["path"] or entry["path"].endswith("/login"):
        print(f"[unipol] {entry['status']} {entry['method']} {entry['path']}")
