# ha-unipolsai

Groundwork for a Home Assistant integration that reads Unibox telematics data (GPS position, driving stats, crash events) out of the Unipol Assicurazioni account API.

Right now this is research, not an integration. No `custom_components/` yet.

## What's here

- [`docs/FINDINGS.md`](docs/FINDINGS.md) — the reverse engineering writeup. API base URL, auth flow, required headers, the telematics endpoints, response models, and the integration design that falls out of them. Start here.
- [`docs/endpoints.txt`](docs/endpoints.txt) — all 339 endpoint path templates extracted from the dex.
- [`docs/CAPTURE.md`](docs/CAPTURE.md) — how to capture live traffic to fill the remaining gaps.
- `tools/` — emulator capture scripts and a standalone API probe.
- `apk/`, `decompiled/`, `captures/` — gitignored working directories.

## State of play

Static analysis is done and the API is fully mapped. The GPS endpoint is:

```
GET https://apphub.unipolsai.it/hub/api/priv/telematici/auto/v1/vehicles/{plate}/lastPosition
```

returning `lat`, `lon`, `speed`, `heading`, `accuracy`, `date`, and a `dailyFruitions` quota counter. Login is a form POST returning a JWT. There's no certificate pinning and the app trusts user CAs, so capturing traffic is straightforward.

Two things block writing the integration:

1. **The `x-ibm-client-id` / `x-ibm-client-secret` pair.** Not in the APK; fetched at runtime from a hash-guarded config endpoint. Has to come off the wire or out of the app's SharedPreferences.
2. **The `dailyFruitions` quota semantics.** There's a hard server-side daily cap on forced position refreshes, and the polling design depends entirely on what `max` is and whether it's per day, per vehicle, or per account.

Both need one capture session with a real account. See [`docs/CAPTURE.md`](docs/CAPTURE.md).

## Reproducing the analysis

Needs `adb`, `jadx`, `apktool`, `apkeep`, and an Android SDK with an arm64 system image.

```bash
apkeep -a com.UnipolSaiApp -d apk-pure apk/
unzip apk/com.UnipolSaiApp.xapk -d apk/
```

Verify it's the real thing before touching it. The signer must be Unipol and the Play source stamp must verify:

```bash
apksigner verify --print-certs apk/com.UnipolSaiApp.apk
```

Expected signer SHA-256: `ed79efb5c7a7b65a2346c9dbe6c709fafe00b8341064779f8ec3363241b165a8`

Then:

```bash
adb install-multiple -r apk/com.UnipolSaiApp.apk apk/config.arm64_v8a.apk apk/config.xxhdpi.apk
jadx -d decompiled/jadx --show-bad-code --deobf -j 8 apk/com.UnipolSaiApp.apk
apktool d -f -o decompiled/apktool apk/com.UnipolSaiApp.apk
```

The telematics API lives in `com/UnipolSaiApp/newapp/network/services/TelematicsAutoService.java` and the header/auth interceptor in `com/UnipolSaiApp/newapp/network/C5673b.java`.

## Probing the API directly

```bash
export UNIPOL_USERNAME=... UNIPOL_PASSWORD=...
export UNIPOL_IBM_CLIENT_ID=... UNIPOL_IBM_CLIENT_SECRET=...

./tools/probe.py contracts
./tools/probe.py position AB123CD
```

`--update` forces the box to report a fresh fix and spends one unit of the daily quota, so it's opt-in.

## Scope

This reads an account holder's own data. It doesn't break pinning, defeat auth, or circumvent any protection. Keep it that way: respect the quota, don't hammer the gateway, and check Unipol's terms before publishing anything under your name.
