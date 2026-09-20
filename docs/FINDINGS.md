# Unipol Assicurazioni Android app: reverse engineering notes

Working out whether a Home Assistant integration can read the Unibox telematics GPS position and driving data. Static analysis of the app, plus a verified live session against a real account with an active box.

Short answer: yes, and it's confirmed working end to end. `lastPosition` returns exactly what a `device_tracker` needs. Two things aren't obvious from the code: auth needs the login cookie jar and not just the JWT, and reading the position is free while *forcing* a fresh fix is capped at 5 a day.

## The binary

| | |
|---|---|
| Package | `com.UnipolSaiApp` |
| Store name | Unipol Assicurazioni (formerly UnipolSai) |
| Version analysed | 6.3.18, version code 42642 |
| minSdk / targetSdk | 32 / 36 |
| ABI analysed | arm64-v8a (split APK, 163 MB total) |
| Capacitor appId | `it.unipol.unipolsai.store.clientitpd.coll` |

Signer:

```
CN=developers@unipolassicurazioni.it, OU=UnipolSai S.p.a., O=UnipolSai, L=Bologna, ST=Italia, C=IT
SHA-256  ed79efb5c7a7b65a2346c9dbe6c709fafe00b8341064779f8ec3363241b165a8
SHA-1    0d19bb735153ecc04610ede8d3f28f92bd719277
RSA 2048, APK Signature Scheme v2 + v3
```

**The app force-updates.** 6.3.6 from a mirror installs fine but refuses to get past its launch screen, so it has to be updated through the Play Store before it's usable. The analysed 6.3.18 was therefore pulled straight off the device with `adb pull` after Play installed it, which is the best provenance available: it's the binary Play actually shipped, and the signer matches. The google_apis emulator image has `com.android.vending` even with `PlayStore.enabled=no` in the AVD config, so this works without a Play-enabled image.

Verify the signer on any future pull with `apksigner verify --print-certs`. A mirror-sourced APK additionally carries a Google Play source stamp (`CN=Android, O=Google Inc.`) that should verify.

Everything below was first mapped on 6.3.6 and re-verified against 6.3.18. The auth layer, header set, `network_security_config` and the entire `telematici/auto` tree are unchanged between the two. What did change: `telematici/commercio` (the home/business Unibox tree) was dropped, `contesto-utente/me/polizze` went v2 to v3, `polizze-previdenza` v1 to v2, and two `registrazioni` OTP endpoints disappeared. 312 endpoints now, down from 339.

## Architecture

Three UI stacks in one app, which is why it runs to 163 MB:

- **Native Android** (Kotlin/Java, Compose in places). All the telematics and account code lives here. This is the part that matters.
- **Capacitor** web bundle in `assets/public/` (Angular). Configured with `server.hostname = mobile.unipolsai.it`. Plugins: `@capacitor/geolocation`, `app`, `browser`, `device`, `network`, plus two in-house ones from Reply (`us-actionmanager-plugin`, `us-imagemanager-plugin`).
- **Flutter** module in `assets/flutter_assets/`.

The web bundle contains no API hosts. Endpoints are all native constants.

Third-party SDKs worth knowing about, because they show up in captured traffic as noise: Firebase/Crashlytics, Tealium (`tags.tiqcdn.com`, `collect.tealiumiq.com`), Glassbox/Clarisite session recording, Salesforce iGoDigital, Nexi XPay for payments, Unblu chat.

## API surface

Base URL: `https://apphub.unipolsai.it/hub/`

It's an IBM API Connect gateway. 312 distinct endpoint path templates were extracted from the dex; the full list is in [`endpoints.txt`](endpoints.txt).

### Authentication

Login is a plain form POST. No OAuth dance, no PKCE.

```
POST https://apphub.unipolsai.it/hub/login
Content-Type: application/x-www-form-urlencoded

username=<user>&password=<pass>
```

Response:

```json
{ "JWT": { "identity": "...", "expires_in": 3600, "token": "<jwt>" } }
```

Note the JSON key for the token is `token`, not `value`, even though the Kotlin field is called `value`.

Refresh, using the current (still valid) bearer token:

```
POST https://apphub.unipolsai.it/hub/login/refresh
```

Same `LoginResponse` shape back.

The app refreshes **120 seconds before expiry** and hard-clears the session once past it. On a 401/403 with `errorCode` `403003` or `codice`/`stato` of `401100` or `401000`, it clears the token, re-logs in, and replays the original request once. Any client should copy that behaviour.

### Required headers

From the OkHttp interceptor (`com.UnipolSaiApp.newapp.network.C5673b`), applied to every request:

| Header | Value |
|---|---|
| `Authorization` | `Bearer <JWT.token>` (omitted when not logged in) |
| `User-Agent` | `UnipolSaiApp/6.3.18 Version Code 42642 (Android <rel>; <model>; <brand> <device>;)` |
| `source` | `mobile` |
| `x-unipol-canale` | `APP` |
| `x-unipol-requestid` | fresh random UUID v4 per request |
| `x-ibm-client-id` | from APIC config, see below |
| `x-ibm-client-secret` | from APIC config, see below |
| `x-unipol-tenant` | from SharedPreferences, set alongside the APIC pair |
| `x-unipol-firebase-config` | Firebase Remote Config variant selector |
| `x-unipol-glassbox-session-id` | session recording id, empty string is accepted |

The `x-ibm-*` pair isn't hardcoded. The app fetches it at runtime:

```
POST api/pub/configurazioni/v1/unipolsai-mobile/apicConfig/hub
Body: { algId, hash, timestamp }
```

`appSuffix` is `hub`. That request is guarded by a hash, so it isn't trivially replayable on its own.

It doesn't need to be. **The app fetches the APIC config at cold start, before any login, and then sends the resulting headers on every subsequent request including the unauthenticated ones.** So proxying a fresh install as far as the login screen is enough to capture all three values. No account required.

Captured that way on 2026-09-20 and written to `.env.local` (gitignored, values deliberately not in this file). They're app-wide, not per-user: the same triple works for any account, and Unipol can rotate them whenever they like. Treat them as configuration with an expiry date, not as a constant.

The fallback, if the config call ever stops going over the wire, is SharedPreferences after the app has run once. The real file is `UNIPOLSAI.xml`, not `UniPicUpPref.xml` as the constant name suggested:

```bash
adb shell cat /data/data/com.UnipolSaiApp/shared_prefs/UNIPOLSAI.xml | grep -i 'ibm\|tenant'
```

### The bearer token is not sufficient on its own

This is the thing static analysis completely missed, and it invalidates the obvious "just replay the JWT" approach.

Replaying a valid `Authorization: Bearer` with the full documented header set returns:

```
HTTP 403  {"errorCode":403003,"errorMessage":"No credential"}
```

which is exactly the code the interceptor treats as a re-auth trigger. **There is a stateful session layer in front of the JWT.** A working request also carries:

```
Cookie: MRHSession=...; LastMRH_Session=...; JSESSIONID=...; TS0179686b=...; TS01ccf0d6=...; TS66e4e8f9027=...
```

`MRHSession` is F5 BIG-IP Access Policy Manager and the `TS*` cookies are F5 ASM. They're established during `POST /hub/login` and must be carried on every subsequent call. Any client therefore needs a cookie-persisting session and must perform a real login. A stored long-lived token is not a workable auth model here.

### Two extra headers on telematics calls

The `@HeaderMap Map<String, String>` parameter on every `TelematicsAutoService` method, which the decompile left unresolved, carries:

```
service_type: Vehicle
company_id: unipolsai
```

Both are required. Without them the telematics endpoints do not behave. They're lowercase with underscores, unlike every other custom header in the app.

A minimal working request is the six standard headers, plus these two, plus `accept: application/json`, plus the login cookie jar. `x-unipol-firebase-config` and `x-unipol-glassbox-session-id` were sent in the verified call but are probably optional, since they're analytics plumbing.

## Telematics endpoints

All from `com.UnipolSaiApp.newapp.network.services.TelematicsAutoService`.

**`{plate}` is country-prefixed**: `IT-AB123CD`, not `AB123CD`. A bare plate does not work. The prefix is not visible anywhere in the decompiled code or in the app UI, which shows the plate unprefixed.

| Method | Path (relative to `/hub/`) | Returns |
|---|---|---|
| GET | `api/priv/telematici/contratti/v1/contracts/myTelematicContracts` | the vehicles you have a box on |
| GET | `api/priv/telematici/auto/v1/vehicles/{plate}/lastPosition?update={bool}` | **GPS position**, `update` required |
| GET | `api/priv/telematici/auto/v1/vehicles/{plate}/vehicleUsages?dateRange=` | driving stats |
| GET | `api/priv/telematici/auto/v1/vehicles/{plate}/crashes` | crash events |
| GET | `api/priv/telematici/auto/v1/vehicles/{plate}/crashes/{crashId}` | one crash |
| GET | `api/priv/telematici/auto/v1/vehicles/{plate}/lastNotifications?vehicleVAS=` | last alerts |
| GET | `api/priv/telematici/auto/v1/vehicles/{plate}/vehicleVAS` | which services are active |
| GET | `api/priv/telematici/auto/v1/vehicles/{plate}/speedLimits` | configured speed alerts |
| GET | `api/priv/telematici/auto/v1/vehicles/{plate}/lastSpeedLimit` | current speed alert |
| POST | `api/priv/telematici/auto/v1/vehicles/{plate}/lastSpeedLimit/modify` | set speed alert |
| GET | `api/priv/telematici/auto/v1/vehicles/{plate}/lastTargetArea` | current geofence |
| POST | `api/priv/telematici/auto/v1/vehicles/{plate}/lastTargetArea/modify` | set geofence |
| GET | `api/priv/contratti/veicolo/v1/vehicleInfoProvider/vehicles/{plate}/basicInsuranceCoverage` | RCA validity |

Also useful outside the telematics tree:

- `api/priv/contesto-utente/v2/me/contrattiTelematici` and the v1 form
- `api/priv/contesto-utente/v1/me/targhe`, plates on the account
- `api/priv/mobilita/targhe/v1/utente/targhe`

6.3.6 had a parallel `api/priv/telematici/commercio/v1/...` tree for the home/business Unibox (IP cameras, RF sensors, alarm kits, `liveStreamingURL`, `snapshot`). **6.3.18 dropped it from the app**, which probably means it moved to a separate app rather than that the server stopped serving it. Worth a look if the house ever gets one, but the paths in this repo's history are no longer evidence that they still work.

## Data models

### `lastPosition`

Real observed response, `GET .../IT-AB123CD/lastPosition?update=false`:

```jsonc
{
  "operationResult": { "type": 0 },
  "lastPosition": {
    "date": 1789889311000,      // epoch MILLISECONDS, not a string
    "lat": 45.464200,
    "lon": 9.1900,
    "speed": 0,                 // int, km/h
    "heading": "N",             // CARDINAL letter, not degrees
    "timeZone": 0,
    "daylightSavingTime": 0,
    "accuracy": 1,              // small int grade, not metres
    "pendingRequest": false,
    "dailyFruitions": { "current": 0, "max": 5 }
  }
}
```

**`update` is a required query parameter.** Omitting it returns HTTP 400 with an empty body, even though the Retrofit signature types it as a nullable `Boolean`. Always send `update=false` for a plain read.

Four corrections to what the decompiled models implied:

- **`date` is an epoch-millisecond integer.** The Kotlin field is `private String date`, but the wire sends a number. Don't trust the declared type.
- **`heading` is a cardinal letter** (`"N"`, presumably `"NE"`, `"S"` and so on), not a bearing in degrees. An HA integration wanting degrees has to map it, and loses resolution doing so.
- **`accuracy` is a small integer grade**, not a radius in metres. Observed `1`. Do not feed it to `gps_accuracy` as if it were metres, that would tell HA the fix is accurate to 1 m.
- **Every telematics response is wrapped in `operationResult`.** `type: 0` is success. Unwrap before parsing.

`timeZone: 0` and `daylightSavingTime: 0` alongside a plausible local timestamp suggest `date` is UTC, but that isn't proven. Check it against a known movement before relying on it.

### The two quotas

There are **two independent budgets**, which is the single most important thing for the polling design.

**`dailyFruitions {current, max}`: observed `max` of 5.** Five forced position refreshes a day. `current` was `0` after several `update=false` reads, so **plain reads are free** and only `update=true` counts. That's the key fact: an HA integration can poll `lastPosition?update=false` as often as it likes and will simply see a stale fix until the car next reports on its own.

**`serviceAvailableCredits` / `serviceCreditUsed` on `vehicleVAS`: a separate, longer-lived pool.** Observed 9 available and 1 used for `carFinder`, out of an apparent 10. `rechargeOwnership: "Unipol"` suggests Unipol refills it. Whether a forced refresh spends a daily fruition, a service credit, or both is still unverified.

So the design is: poll `update=false` freely on a normal interval, and expose `update=true` as an explicit button or service that refuses when `current >= max`.

### `vehicleVAS`

```jsonc
{
  "operationResult": { "type": 0 },
  "vehicleVAS": [
    { "serviceName": "carFinder", "isServiceEnabled": true, "isServiceActivated": true,
      "serviceRequiredCredits": true, "serviceAvailableCredits": 9,
      "serviceCreditUsed": 1, "rechargeOwnership": "Unipol" }
    // ...
  ]
}
```

The six `serviceName` values, which are the `{serviceName}` path segment elsewhere in the API:

| `serviceName` | UI label | Needs credits |
|---|---|---|
| `carFinder` | CAR FINDER | yes |
| `speedLimit` | SPEED LIMIT | yes |
| `targetArea` | TARGET AREA | yes |
| `engineOn` | ALERT ACCENSIONE | yes |
| `carMovedEngineOff` | ALERT SPOSTAMENTO | yes |
| `rangeStatistics` | PERCORRENZE | **no** |

`rangeStatistics` has `serviceRequiredCredits: false`, so the driving statistics behind `vehicleUsages` are **free to poll**. Check `isServiceActivated` before creating entities: a position sensor is meaningless if `carFinder` is off.

### `vehicleUsages`

A wide statistics record, not a trip list. **Free to poll**: `rangeStatistics` has `serviceRequiredCredits: false` and it doesn't touch `dailyFruitions`.

**`dateRange` is a single letter, and only two are valid.** Not the `LAST_MONTH`-style enum the Retrofit signature suggests. Anything else returns `400100 "dateRange fornito non è corretto"`.

| Value | Meaning | Extra params |
|---|---|---|
| `g` | the whole contract period | none |
| `t` | custom range | `startDate` and `endDate`, **epoch millis**, required |

ISO dates on `t` return HTTP 500. With `g`, `fromDate` comes back equal to the contract's `dataInizio`, so `g` really is "everything since the policy started", not "today".

Real response for `dateRange=g` over 91 days:

```jsonc
{
  "operationResult": { "type": 0 },
  "vehicleUsages": [{
    "statisticsDate": 1789689600000, "fromDate": 1781913600000, "toDate": 1789689600000,
    "totalDistance": 5431730,          // METRES
    "totalDrivingTime": 420215,        // SECONDS
    "daylightDrivingDistance": 5395460, "daylightDrivingTime": 417010,
    "cityDrivingDistance": 1378360, "extraUrbanDrivingDistance": 1667250,
    "highwayDrivingDistance": 1888260, "otherDrivingDistance": 497860,
    "cityDrivingTime": 149951, "extraUrbanDrivingTime": 176327,
    "highwayDrivingTime": 62519, "otherDrivingTime": 31418,
    "higherMileageProvince": "XX", "higherMileageProvinceFullName": "<Province>",
    "higherMileageProvinceDrivingPerc": 41.58, "higherMileageProvinceTimePerc": 52.54,
    "mondayDrivingDistance": 749450, /* ... through sunday ... */
    "mondayDrivingTime": 65509,      /* ... through sunday ... */
    "totalDaysUsedForAnalysis": 91
  }]
}
```

**Units are metres and seconds.** Not stated anywhere; derived by cross-check. 5431730 / 420215 = 12.9 m/s = 46 km/h average over mixed driving, which is the only reading that makes sense. Anything treating `totalDistance` as kilometres will be out by 1000x.

Four fields the 6.3.6 model didn't have: `toDate`, `totalDistance`, `totalDrivingTime`, `totalDaysUsedForAnalysis`. The decompiled `VehicleUsage` class is incomplete relative to the live API, so trust the wire over the model.

Good material for long-term-statistics sensors, not for live state. It's a cumulative record, so feed it as a total, not a delta.

There's also a `Positions` model (note the plural, distinct from `Location`) with `latitude`, `longitude`, `speed`, `heading`, `quality`, `samplingRate`, `isClimax`, `date`, and a list of `accelerations`. It's the per-sample crash reconstruction shape, reachable through the `crashes` endpoints. That's where actual GPS traces live, though only around crash events.

## Traffic interception

This app is unusually easy to intercept:

- **No certificate pinning.** No `CertificatePinner` anywhere in the app's own code.
- **`network_security_config` trusts user CAs**:
  ```xml
  <base-config>
    <trust-anchors>
      <certificates src="system" />
      <certificates src="user" />
    </trust-anchors>
  </base-config>
  ```

So mitmproxy works with just the CA installed as a user cert. No Frida, no system partition remount, no APK patching. See [`CAPTURE.md`](CAPTURE.md).

One practical catch: **scope the interception to `apphub.unipolsai.it`**. Proxying everything breaks the app's web content. `www.unipol.it` returns a `Set-Cookie` value with surrounding whitespace, which trips mitmproxy's HTTP/2 header parser and kills the connection, and the analytics hosts fail noisily if local DNS sinkholes them. `--allow-hosts 'apphub\.unipolsai\.it'` passes everything else through as raw TCP and the app behaves normally.

## Home Assistant integration design

What maps cleanly:

| Entity | Source | Watch out for |
|---|---|---|
| `device_tracker` per vehicle | `lastPosition.lat` / `.lon` | **Do not** map `accuracy` to `gps_accuracy`. It's a grade, not metres; `1` would claim a 1 m fix. Leave `gps_accuracy` unset. |
| `sensor` speed | `lastPosition.speed` | km/h, int |
| `sensor` heading | `lastPosition.heading` | cardinal letter, so this is a text sensor, not degrees |
| `sensor` position age | `lastPosition.date` | epoch **millis**, divide by 1000 |
| `sensor` forced refreshes used today | `dailyFruitions.current` / `.max` | expose both so automations can back off |
| `sensor` service credits left | `vehicleVAS[carFinder].serviceAvailableCredits` | the second, slower budget |
| `binary_sensor` refresh pending | `lastPosition.pendingRequest` | never yet observed true |
| `sensor` total distance / driving time | `vehicleUsages` totals | **metres and seconds**; cumulative, so `total`, not `total_increasing` |
| `sensor` distance by road type / weekday | `vehicleUsages` | long-term statistics material |
| `binary_sensor` RCA valid | `basicInsuranceCoverage` | |
| event on crash | `crashes` | |

Design notes:

- **Config flow**: username + password, plus the `x-ibm-client-id` / `x-ibm-client-secret` / `x-unipol-tenant` triple until a cleaner way to derive them exists. Discover vehicles from `contrattiTelematici` (see below) rather than asking for plates, and remember to country-prefix the plate before using it as a path segment.
- **Use one cookie-persisting session for everything.** The F5 cookies from login are as load-bearing as the JWT. `requests.Session` or `aiohttp.ClientSession` with a cookie jar, and a real login on startup. Don't build a stored-token model.
- **Poll `lastPosition?update=false` freely.** It doesn't consume quota. The position simply goes stale between the car's own reports, which is fine for a `device_tracker`.
- **Expose forcing a refresh as a button, never as automatic behaviour.** Five a day, shared across whatever else uses the account, including the phone app. Refuse when `current >= max`.
- **Gate entity creation on `vehicleVAS`.** If `carFinder` has `isServiceActivated: false`, there's no position to read and the integration should say so rather than producing an unavailable tracker.
- `vehicleUsages` is free and changes daily at most. Once or twice a day.
- Reuse the app's 401/403 handling: on `403003`, re-login (which rebuilds the cookies) and replay once.
- Send a truthful `User-Agent` identifying the integration rather than impersonating the app, unless the gateway rejects it. The verified call used the app's string, so this still needs one comparison run.

### Vehicle discovery

`api/priv/contesto-utente/v2/me/contrattiTelematici` is a better discovery call than `myTelematicContracts`: one request, and it returns everything a config flow needs.

```jsonc
{ "auto": { "contrattiAuto": [{
      "identificativoTelematico": "...", "statoContratto": "open",
      "dataInizio": 1781913600000, "dataFine": 1813449600000,
      "statoTerminale": "active",
      "veicolo": { "tipo": 1, "marca": "<MAKE>", "modello": "<MODEL>", "targa": "AB123CD" },
      "dispositivoTelematico": { "idDispositivo": "...", "tipoDispositivo": "F", "imei": "..." }
    }], "codice": 200200 },
  "immobili": { "contrattiImmobili": [], "codice": 404404, "message": "Contratti non trovati" },
  "pet":      { "contrattiPet": [],      "codice": 404,    "message": "Contratti non trovati" } }
```

Note the per-section status codes. An empty section reports `404404` or `404` with `"Contratti non trovati"` inside an HTTP 200. That's a normal empty result, not an error, and the codes aren't consistent between sections. Check `statoContratto: "open"` and `statoTerminale: "active"` before creating entities. `targa` here is unprefixed and needs the `IT-` prefix adding.

## Open questions

Settled by the live session:

- ~~The `x-ibm-*` credentials.~~ Captured pre-login, in `.env.local`. `appSuffix` is `hub`.
- ~~Whether the telematics API changed between 6.3.6 and 6.3.18.~~ It didn't.
- ~~`date` format.~~ Epoch milliseconds, despite the declared `String` type.
- ~~`accuracy` units.~~ Not metres. A small integer grade; observed `1`.
- ~~`dailyFruitions.max`.~~ 5. And plain reads don't count against it, only `update=true`.
- ~~Whether a bearer token is enough.~~ It isn't. The F5 session cookies from login are mandatory.
- ~~What fills the `@HeaderMap`.~~ `service_type: Vehicle` and `company_id: unipolsai`.
- ~~Plate format.~~ Country-prefixed, `IT-AB123CD`.
- ~~Login OTP on a new device.~~ None was triggered on a fresh install and fresh emulator.
- ~~`vehicleUsages` `dateRange` vocabulary.~~ `g` and `t` only, and the units are metres and seconds.

Still open:

1. **The `pendingRequest` cycle.** Never observed as `true`, because no forced refresh has been made yet. How long a forced fix takes to land, and the right poll cadence while waiting, are unknown.
2. **Whether a forced refresh spends a `dailyFruitions` unit, a `serviceAvailableCredits` unit, or both.** The two counters were 0/5 and 9/10 respectively at rest.
3. Whether the gateway rejects a non-app `User-Agent`. The verified call impersonated the app. `tools/probe.py` sends an honest one by default, so this needs one comparison run.
4. Whether `heading` uses 8-point (`"NE"`) or 16-point (`"NNE"`) cardinals. Only `"N"` observed.
5. How long the F5 session lasts, and whether `login/refresh` renews the cookies or only the JWT. This decides how often the integration must fully re-login.
7. Rate limits on the non-telematics endpoints.

## Legal note

This documents a private API for the purpose of letting an account holder read their own data. That's interoperability, not circumvention: no DRM is broken, no pinning is bypassed, no auth is defeated. Worth keeping it that way. Stay within the documented quota, don't hammer the gateway, and don't publish credentials.

Unipol's terms of service may still say something about automated access. Check before publishing an integration under your name.
