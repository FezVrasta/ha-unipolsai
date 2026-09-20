# pyunipolsai

Async Python client for the Unipol (UnipolSai) **Unibox** telematics API: vehicle position, driving statistics, and alert events for the black box fitted under an Italian Unipol motor policy.

Built by reverse engineering the Android app and verifying every call against a live account. The findings behind it are written up in [`docs/FINDINGS.md`](https://github.com/FezVrasta/ha-unipolsai/blob/main/docs/FINDINGS.md).

```python
import asyncio
from pyunipolsai import UnipolSaiClient


async def main():
    async with UnipolSaiClient(username="you@example.com", password="...") as client:
        for vehicle in await client.async_get_vehicles():
            position = await client.async_get_position(vehicle)
            print(
                vehicle.plate,
                position.latitude,
                position.longitude,
                position.timestamp,
                f"{position.quota.remaining} refreshes left",
            )


asyncio.run(main())
```

## What it does

| Method | Returns | Cost |
|---|---|---|
| `async_get_vehicles()` | `list[Vehicle]`, usable ones by default | free |
| `async_get_position(vehicle)` | `Position` | free |
| `async_get_position(vehicle, force_refresh=True)` | `Position` | **spends daily quota** |
| `async_get_services(vehicle)` | `dict[str, Service]` | free |
| `async_get_notifications(vehicle, service)` | `list[Notification]` | free |
| `async_get_usage(vehicle)` | `UsageStats` | free |

## Things this API does that will surprise you

The library handles all of these; they're listed so the behaviour isn't mistaken for a bug.

**A bearer token is not enough.** Login also sets F5 BIG-IP session cookies that must ride on every request. The client keeps one cookie-persisting session and treats a 403 as "log in again" rather than "refresh the token". A stored long-lived token is not a workable auth model here.

**Plates are country-prefixed** in URLs (`IT-AB123CD`). Pass a `Vehicle` or a bare plate; `normalise_plate` sorts it out.

**Declared types lie.** Dates are declared `String` in the app but sent as epoch milliseconds. Distances are metres, times are seconds. `heading` is a cardinal letter (`"N"`), not degrees. `accuracy` is a small quality grade, *not* a radius, which is why this library calls it `Position.quality` — mapping a `1` onto something like Home Assistant's `gps_accuracy` would claim a one-metre fix.

**There are two separate budgets.** `Position.quota` is the daily cap on *forced* refreshes (observed limit: 5). Plain reads never touch it. Separately, `Service.credits_available` is a slower pool that pays for having a service switched on. `rangeStatistics` needs no credits at all, so driving statistics are free to poll.

**`force_refresh=True` is fire and forget.** It returns immediately with the *old* position and `pending_request` False; the flag goes true a few seconds later and the cycle takes roughly five minutes. It can finish without the position changing, which is what a car parked with the engine off looks like — and that costs no quota. Compare `timestamp` against the value you had before to tell success from give-up.

**`async_get_notifications` returns only the most recent event** despite the plural field name, so two events inside one poll interval collapse into one. The app receives these as push; there is no push path here.

**`date_range` is a single letter.** `g` is the whole contract period, `t` is a custom range needing epoch-millisecond `start`/`end`. Word-style values like `LAST_MONTH` are rejected.

## Gateway credentials

Requests carry the app's IBM API Connect credentials (`x-ibm-client-id`, `x-ibm-client-secret`, `x-unipol-tenant`). Working defaults ship in `const.py`: they are app-global rather than per-user, and travel inside a public Play Store app, so they are no more secret than any baked-in mobile API key.

Unipol can rotate them. Override them if that happens, without waiting for a release:

```python
UnipolSaiClient(
    username=..., password=..., client_id=..., client_secret=..., tenant=...
)
```

[`docs/CAPTURE.md`](https://github.com/FezVrasta/ha-unipolsai/blob/main/docs/CAPTURE.md) explains how to capture new ones. It needs no account.

## Install

```bash
pip install pyunipolsai
```

Developed in the [`ha-unipolsai`](https://github.com/FezVrasta/ha-unipolsai) repository
alongside the Home Assistant integration that uses it, and released from a
`pyunipolsai-vX.Y.Z` tag there.

## Tests

```bash
pip install -e '.[test]'
pytest
```

The fixtures are real captured payloads with identifiers replaced.

## Scope

This reads an account holder's own data. It breaks no pinning, defeats no authentication, and circumvents no protection. Respect the quota, don't hammer the gateway, and check Unipol's terms before building anything public on it.
