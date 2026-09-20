# Unipol Assicurazioni Android app: reverse engineering notes

Static analysis of the Android app, done to work out whether a Home Assistant integration can read the Unibox telematics GPS position and driving data.

Short answer: yes. There's a clean REST API behind a JWT, and `lastPosition` returns exactly what a `device_tracker` needs. The catch is a server-side daily quota on position refreshes.

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

The fallback, if the config call ever stops going over the wire, is SharedPreferences after the app has run once:

```bash
adb shell run-as com.UnipolSaiApp cat \
  /data/data/com.UnipolSaiApp/shared_prefs/UniPicUpPref.xml | grep -i 'ibm\|tenant'
```

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

6.3.6 had a parallel `api/priv/telematici/commercio/v1/...` tree for the home/business Unibox (IP cameras, RF sensors, alarm kits, `liveStreamingURL`, `snapshot`). **6.3.18 dropped it from the app**, which probably means it moved to a separate app rather than that the server stopped serving it. Worth a look if the house ever gets one, but the paths in this repo's history are no longer evidence that they still work.

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

One practical catch: **scope the interception to `apphub.unipolsai.it`**. Proxying everything breaks the app's web content. `www.unipol.it` returns a `Set-Cookie` value with surrounding whitespace, which trips mitmproxy's HTTP/2 header parser and kills the connection, and the analytics hosts fail noisily if local DNS sinkholes them. `--allow-hosts 'apphub\.unipolsai\.it'` passes everything else through as raw TCP and the app behaves normally.

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

Settled:

- ~~The `x-ibm-*` credentials.~~ Captured pre-login, in `.env.local`. `appSuffix` is `hub`.
- ~~Whether the telematics API changed between 6.3.6 and 6.3.18.~~ It didn't.

Still open. All of these need one authenticated session against an account with a Unibox, which static analysis and an unauthenticated capture can't provide:

1. Exact `date` format and timezone handling in `lastPosition`.
2. Units of `accuracy`, and whether it's ever non-zero.
3. What `max` actually is in `dailyFruitions`, and whether the quota is per day, per vehicle, or per account. **This one decides the polling design.**
4. The `pendingRequest` cycle: how long until a forced fix lands, and the right poll cadence while waiting.
5. Whether the gateway rejects a non-app `User-Agent`. `tools/probe.py` sends an honest one by default and has `--impersonate-app` to test the difference.
6. Whether login triggers OTP/2FA on a new device fingerprint. There's a lot of OTP machinery in `LoginApi`.
7. Rate limits on the non-telematics endpoints.

## Legal note

This documents a private API for the purpose of letting an account holder read their own data. That's interoperability, not circumvention: no DRM is broken, no pinning is bypassed, no auth is defeated. Worth keeping it that way. Stay within the documented quota, don't hammer the gateway, and don't publish credentials.

Unipol's terms of service may still say something about automated access. Check before publishing an integration under your name.
