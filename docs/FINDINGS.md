# Unipol Assicurazioni Android app: reverse engineering notes

Static analysis of the Android app, done to work out whether a Home Assistant integration can read the Unibox telematics GPS position and driving data.

Short answer: yes. There's a clean REST API behind a JWT, and `lastPosition` returns exactly what a `device_tracker` needs. The catch is a server-side daily quota on position refreshes.

## The binary

| | |
|---|---|
| Package | `com.UnipolSaiApp` |
| Store name | Unipol Assicurazioni (formerly UnipolSai) |
| Version | 6.3.6, version code 42549 |
| minSdk / targetSdk | 24 / 36 |
| ABI analysed | arm64-v8a (split APK, 116 MB total) |
| Capacitor appId | `it.unipol.unipolsai.store.clientitpd.coll` |

Signer:

```
CN=developers@unipolassicurazioni.it, OU=UnipolSai S.p.a., O=UnipolSai, L=Bologna, ST=Italia, C=IT
SHA-256  ed79efb5c7a7b65a2346c9dbe6c709fafe00b8341064779f8ec3363241b165a8
SHA-1    0d19bb735153ecc04610ede8d3f28f92bd719277
RSA 2048, APK Signature Scheme v2 + v3
```

The APK also carries a **Google Play source stamp** signed by `CN=Android, O=Google Inc.` which verifies. That proves the binary is the unmodified Play Store build even though it was fetched through a mirror. Worth re-checking with `apksigner verify --print-certs` on any future pull.

## Architecture

Three UI stacks in one app, which is why it's 116 MB:

- **Native Android** (Kotlin/Java, Compose in places). All the telematics and account code lives here. This is the part that matters.
- **Capacitor** web bundle in `assets/public/` (Angular). Configured with `server.hostname = mobile.unipolsai.it`. Plugins: `@capacitor/geolocation`, `app`, `browser`, `device`, `network`, plus two in-house ones from Reply (`us-actionmanager-plugin`, `us-imagemanager-plugin`).
- **Flutter** module in `assets/flutter_assets/`.

The web bundle contains no API hosts. Endpoints are all native constants.

Third-party SDKs worth knowing about, because they show up in captured traffic as noise: Firebase/Crashlytics, Tealium (`tags.tiqcdn.com`, `collect.tealiumiq.com`), Glassbox/Clarisite session recording, Salesforce iGoDigital, Nexi XPay for payments, Unblu chat.

## API surface

Base URL: `https://apphub.unipolsai.it/hub/`

It's an IBM API Connect gateway. 339 distinct endpoint path templates were extracted from the dex; the full list is in [`endpoints.txt`](endpoints.txt).

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
| `User-Agent` | `UnipolSaiApp/6.3.6 Version Code 42549 (Android <rel>; <model>; <brand> <device>;)` |
| `source` | `mobile` |
| `x-unipol-canale` | `APP` |
| `x-unipol-requestid` | fresh random UUID v4 per request |
| `x-ibm-client-id` | from APIC config, see below |
| `x-ibm-client-secret` | from APIC config, see below |
| `x-unipol-tenant` | from SharedPreferences, set alongside the APIC pair |
| `x-unipol-firebase-config` | Firebase Remote Config variant selector |
| `x-unipol-glassbox-session-id` | session recording id, empty string is accepted |

The `x-ibm-*` pair is the one unsolved piece. It isn't hardcoded. The app fetches it at runtime:

```
POST api/pub/configurazioni/v1/unipolsai-mobile/apicConfig/{appSuffix}
Body: { algId, hash, timestamp }
```

That request is itself guarded by a hash, so it isn't trivially replayable. Two practical ways around it:

1. Read the values out of the device after the app has run once. They land in SharedPreferences (`UniPicUpPref` prefs file) under the keys `x-ibm-client-id`, `x-ibm-client-secret`, `x-unipol-tenant`.
2. Capture them off the wire with mitmproxy, which is easier and gets the tenant at the same time.

They look like long-lived app-wide credentials rather than per-user ones, so pinning them in the integration config is probably fine, with the caveat that Unipol can rotate them.

## Telematics endpoints

All from `com.UnipolSaiApp.newapp.network.services.TelematicsAutoService`. `{plate}` is the vehicle plate, uppercase, no spaces.

| Method | Path (relative to `/hub/`) | Returns |
|---|---|---|
| GET | `api/priv/telematici/contratti/v1/contracts/myTelematicContracts` | the vehicles you have a box on |
| GET | `api/priv/telematici/auto/v1/vehicles/{plate}/lastPosition?update={bool}` | **GPS position** |
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

There's a parallel `api/priv/telematici/commercio/v1/...` tree for the home/business Unibox (IP cameras, RF sensors, alarm kits, `liveStreamingURL`, `snapshot`). Out of scope here but it's there if the house ever gets one.

## Data models

### `lastPosition`

```jsonc
{
  "lastPosition": {
    "lat": 44.4949,
    "lon": 11.3426,
    "speed": 0,                 // int
    "heading": "0",             // STRING here, int elsewhere
    "accuracy": 0,              // int, units unconfirmed
    "date": "...",              // string, format unconfirmed
    "timeZone": 1,
    "daylightSavingTime": 1,
    "pendingRequest": false,    // see below
    "dailyFruitions": { "current": 3, "max": 10 }
  }
}
```

Two things drive the integration design:

**`pendingRequest`.** Calling with `?update=true` asks the box to report a fresh fix, which is not instant. The response almost certainly comes back with `pendingRequest: true` and a stale position, and you poll again without `update` until it flips false. Treat `update=true` as "start a refresh", not "give me the position now".

**`dailyFruitions {current, max}`.** A server-side daily quota on forced refreshes. This is the single most important constraint. A naive 30-second poll with `update=true` will burn the day's allowance in minutes and probably annoy Unipol. The integration must read `max`, track `current`, and budget.

Field names are transcribed from the Moshi `@Json(name=)` annotations, so they're accurate. Values above are illustrative, not observed. The exact `date` format and `accuracy` units need a live capture to confirm.

### `vehicleUsages`

A wide statistics record, not a trip list. Distances and times broken down by:

- road type: `cityDriving*`, `extraUrbanDriving*`, `highwayDriving*`, `otherDriving*`
- day of week: `mondayDriving*` through `sundayDriving*`
- daylight vs night: `daylightDriving*`
- top province: `higherMileageProvince`, `higherMileageProvinceFullName`, `higherMileageProvinceDrivingPerc`, `higherMileageProvinceTimePerc`
- window: `fromDate`, `statisticsDate` (epoch millis)

Each `*Distance` / `*Time` pair is an int. Good material for long-term-statistics sensors, not for live state.

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

## Home Assistant integration design

What maps cleanly:

| Entity | Source |
|---|---|
| `device_tracker` per vehicle | `lastPosition` → `lat`/`lon`, with `gps_accuracy` from `accuracy` |
| `sensor` speed | `lastPosition.speed` |
| `sensor` heading | `lastPosition.heading` |
| `sensor` position age | `lastPosition.date` |
| `sensor` refreshes used today | `dailyFruitions.current` / `.max`, exposed so automations can back off |
| `binary_sensor` refresh pending | `pendingRequest` |
| `sensor` distance by road type / weekday | `vehicleUsages`, long-term statistics |
| `binary_sensor` RCA valid | `basicInsuranceCoverage` |
| event on crash | `crashes` |

Design notes:

- **Config flow**: username + password, plus the `x-ibm-client-id` / `x-ibm-client-secret` / `x-unipol-tenant` triple until a cleaner way to derive them exists. Discover vehicles from `myTelematicContracts` rather than asking for plates.
- **Two coordinators.** A cheap one polling `lastPosition` without `update` on a normal interval, and a separate quota-aware path for forced refreshes. Never call `update=true` from the routine poll.
- **Expose forcing a refresh as a service/button**, not as automatic behaviour, so the quota stays under the user's control. Refuse the call when `current >= max`.
- `vehicleUsages` changes daily at most. Poll it a couple of times a day.
- Reuse the app's 401/403 handling: clear token, re-login, replay once.
- Send a truthful `User-Agent` identifying the integration rather than impersonating the app, unless the gateway rejects it. Worth testing which the API tolerates.

## Open questions

Everything below needs a live capture with a real account to settle. Static analysis can't answer them.

1. Exact `date` format and timezone handling in `lastPosition`.
2. Units of `accuracy`, and whether it's ever non-zero.
3. What `max` actually is in `dailyFruitions`, and whether the quota is per day, per vehicle, or per account.
4. The `pendingRequest` cycle: how long until a forced fix lands, and the right poll cadence while waiting.
5. Whether `x-ibm-client-id` / `x-ibm-client-secret` are stable across app versions and accounts.
6. Whether the gateway rejects a non-app `User-Agent`.
7. Whether login triggers OTP/2FA on a new device fingerprint. There's a lot of OTP machinery in `LoginApi`.
8. Rate limits on the non-telematics endpoints.

## Legal note

This documents a private API for the purpose of letting an account holder read their own data. That's interoperability, not circumvention: no DRM is broken, no pinning is bypassed, no auth is defeated. Worth keeping it that way. Stay within the documented quota, don't hammer the gateway, and don't publish credentials.

Unipol's terms of service may still say something about automated access. Check before publishing an integration under your name.
