# ha-unipolsai

Groundwork for a Home Assistant integration that reads Unibox telematics data (GPS position, driving stats, crash events) out of the Unipol Assicurazioni account API.

Ships a working `custom_components/unipolsai` plus the research it came from.

## What's here

- [`docs/FINDINGS.md`](docs/FINDINGS.md) — the reverse engineering writeup. API base URL, auth flow, required headers, the telematics endpoints, response models, and the integration design that falls out of them. Start here.
- [`docs/endpoints.txt`](docs/endpoints.txt) — all 312 endpoint path templates extracted from the dex.
- [`docs/CAPTURE.md`](docs/CAPTURE.md) — how to capture live traffic to fill the remaining gaps.
- `custom_components/unipolsai/` — the integration.
- `tools/` — emulator capture scripts and a standalone API probe.
- `apk/`, `decompiled/`, `captures/` — gitignored working directories.

## State of play

Static analysis is done, and the API is now **verified working end to end against a real account with an active Unibox**.

```
GET https://apphub.unipolsai.it/hub/api/priv/telematici/auto/v1/vehicles/IT-AB123CD/lastPosition?update=false
-> {"operationResult":{"type":0},
    "lastPosition":{"date":1789889311000,"lat":45.464200,"lon":9.1900,"speed":0,
                    "heading":"N","accuracy":1,"pendingRequest":false,
                    "dailyFruitions":{"current":0,"max":5}}}
```

The five things that were not knowable from the code, and would each have broken a first attempt:

1. **The bearer token alone gets you HTTP 403.** There's an F5 BIG-IP session cookie layer (`MRHSession`, `JSESSIONID`) established at login that must be carried on every call. The integration needs a cookie-persisting session and a real login, not a stored token.
2. **The plate is country-prefixed**: `IT-AB123CD`. A bare plate doesn't work, and the prefix appears nowhere in the app or its code.
3. **Telematics calls need two extra headers**, `service_type: Vehicle` and `company_id: unipolsai`. These fill the `@HeaderMap` the decompile left empty.
4. **`update` is a required query parameter.** Omitting it is a 400.
5. **Field types in the decompiled models are wrong.** `date` is epoch millis despite being declared `String`, `heading` is a cardinal letter (`"N"`) not degrees, and `accuracy` is a small grade, not metres.

**Quota, which drives the whole polling design:** reads are free. `dailyFruitions` was `0/5` after many `update=false` calls, so only forcing a fresh fix counts, and you get five a day. Separately, `vehicleVAS` carries a slower per-service credit pool (`carFinder` at 9 of 10). `rangeStatistics` needs no credits at all, so driving statistics are free to poll.

Still open: the `pendingRequest` cycle. No forced refresh has been made yet, so how long a fresh fix takes to land, and which of the two counters it spends, are unknown. Everything else needed to write the integration is settled.

## Reproducing the analysis

Needs `adb`, `jadx`, `apktool`, `apkeep`, and an Android SDK with an arm64 system image.

Seed the emulator from a mirror, then let Play update it. **The mirror build won't run**: the app force-updates and refuses to get past its launch screen, and minSdk moved 24 to 32 between 6.3.6 and 6.3.18.

```bash
apkeep -a com.UnipolSaiApp -d apk-pure apk/
unzip apk/com.UnipolSaiApp.xapk -d apk/
adb install-multiple -r apk/com.UnipolSaiApp.apk apk/config.arm64_v8a.apk apk/config.xxhdpi.apk
```

Update it through the Play Store on the emulator, then pull what actually runs. That's better provenance than any mirror, since it's the binary Play shipped:

```bash
mkdir -p apk/current
for p in $(adb shell pm path com.UnipolSaiApp | sed 's/package://' | tr -d '\r'); do
  adb pull "$p" apk/current/
done
apksigner verify --print-certs apk/current/base.apk
```

Expected signer SHA-256: `ed79efb5c7a7b65a2346c9dbe6c709fafe00b8341064779f8ec3363241b165a8`

Then:

```bash
jadx -d decompiled/jadx --show-bad-code --deobf -j 8 apk/current/base.apk
apktool d -f -o decompiled/apktool apk/current/base.apk
```

The telematics API lives in `com/UnipolSaiApp/newapp/network/services/TelematicsAutoService.java` and the header/auth interceptor in `com/UnipolSaiApp/newapp/network/C5673b.java`.

## Probing the API directly

The APIC credentials are already in `.env.local`. Add your account to it, then:

```bash
set -a; source .env.local; set +a
./tools/probe.py contracts
./tools/probe.py position AB123CD
```

`--update` forces the box to report a fresh fix and spends one unit of the daily quota, so it's opt-in.

## Scope

This reads an account holder's own data. It doesn't break pinning, defeat auth, or circumvent any protection. Keep it that way: respect the quota, don't hammer the gateway, and check Unipol's terms before publishing anything under your name.

## Installing

Copy `custom_components/unipolsai` into your HA config directory and restart, then add **UnipolSai Unibox** from Settings → Devices & services.

The config flow asks for your Unipol username and password, plus the three gateway values (`x-ibm-client-id`, `x-ibm-client-secret`, `x-unipol-tenant`). Those are the app's own API Connect credentials and are not hardcoded, because Unipol can rotate them; [`docs/CAPTURE.md`](docs/CAPTURE.md) explains how to capture them, and it needs no account.

### Entities, per vehicle

| Entity | Notes |
|---|---|
| `device_tracker` | last known position. No `gps_accuracy`: the API's `accuracy` is a quality grade, not metres |
| `sensor` speed, heading, last fix | heading is a cardinal letter, so it's a text sensor |
| `sensor` refreshes used / remaining today | the 5-a-day forced-refresh budget |
| `sensor` Car Finder credits | the separate, slower service-credit pool |
| `sensor` total / city / extra-urban / motorway distance, driving time | from `vehicleUsages`, free to poll |
| `sensor` most driven province and its share | |
| `binary_sensor` refresh pending, Car Finder active | |
| `button` Locate now | forces a fresh fix; unavailable once the daily budget is gone |

Position and statistics polling are free, so they run on a normal interval. **Locate now** is the only thing that spends quota, which is why it's a button and not automatic. Pressing it fires the request and then waits out the roughly five-minute cycle; if the car is parked with the engine off the box will not answer and the position stays unchanged, which costs nothing.
