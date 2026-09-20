<p align="center">
  <img src="custom_components/unipolsai/brand/icon.png" width="128" alt="">
</p>

<h1 align="center">UnipolSai Unibox for Home Assistant</h1>

<p align="center">
  Track the car your Unipol black box already tracks.<br>
  Position, driving statistics and engine alerts, without spending your refresh allowance.
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=FezVrasta&repository=ha-unipolsai&category=integration">
    <img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open this repository in HACS">
  </a>
</p>

<p align="center">
  <img src="https://github.com/FezVrasta/ha-unipolsai/actions/workflows/ci.yml/badge.svg" alt="CI">
  <img src="https://img.shields.io/badge/HACS-custom-41BDF5.svg" alt="HACS custom repository">
  <img src="https://img.shields.io/badge/Home%20Assistant-2026.8%2B-41BDF5" alt="Home Assistant">
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="Alpha">
  <img src="https://img.shields.io/badge/config-no%20YAML-41BDF5" alt="No YAML">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT">
</p>

---

If your Unipol motor policy came with a Unibox, the box already knows where the car is, how far it has been driven and when the engine was last started. The Unipol app shows you some of that; nothing shows it to Home Assistant. This adds the car as a `device_tracker`, with the driving statistics and the engine-start alert alongside it.

**Forcing a fresh position is rationed.** Unipol allows five forced refreshes a day, shared with the phone app. Reading the last known position costs nothing, so this polls freely and puts the forced refresh behind a button you press deliberately.

**Engine alerts are polled, not pushed.** The phone app gets a push notification; there is no push channel into Home Assistant. An engine start shows up on the next poll, so up to five minutes late, and two starts inside one interval collapse into one.

## What you get

One device per vehicle with an active box.

| Entity | What it is |
| --- | --- |
| `device_tracker` | Last known position. Reports no `gps_accuracy` on purpose, because the API's accuracy field is a quality grade rather than a radius in metres |
| `sensor` Speed, Heading, Last fix | Heading is a cardinal letter, because that is what the box reports |
| `sensor` Refreshes used / remaining today | The five-a-day forced-refresh budget |
| `sensor` Car Finder credits | A second, slower budget that pays for the service being switched on |
| `sensor` Total, city, extra-urban and motorway distance, total driving time | Free to poll; cumulative since the contract started |
| `sensor` Most driven province and its share | |
| `binary_sensor` Refresh pending, Car Finder | |
| `event` Engine started | Fires on a new alert, carrying the coordinates the engine was started at |
| `sensor` Last engine start | Timestamp of that event |
| `button` Locate now | Asks the box for a fresh fix. Unavailable once the daily budget is gone |

Alert entities are created only for services your contract has switched on, so speed-limit, target-area and moved-with-engine-off alerts appear by themselves if you activate them.

## Install

Add this repository to HACS as a custom repository, install **UnipolSai Unibox**, restart Home Assistant, then add the integration from **Settings → Devices & services**. It asks for your Unipol username and password, and nothing else.

## Options

The integration talks to Unipol's API gateway with credentials that ship inside the Unipol app. Working values are built in, so there is normally nothing to configure. If Unipol rotates them the integration stops authenticating, and **Configure** on the integration lets you paste new ones without waiting for a release. [`docs/CAPTURE.md`](docs/CAPTURE.md) explains how to capture them; it needs no account.

## What it cannot do

- **No live tracking.** The box reports on its own schedule, and forcing a fix is capped at five a day. This is not a real-time tracker and cannot be made into one.
- **A forced refresh fails quietly when the car is parked.** With the engine off the box does not answer, the position stays where it was, and about five minutes later the attempt gives up. It costs no quota, but it is indistinguishable from a car that has not moved.
- **Crash events are not exposed yet.** The API has them, including per-sample GPS traces and accelerometer data.
- **Home and business Unibox is out of scope.** Cameras, sensors and alarm kits live behind a different API tree, which the current app no longer ships.

## For contributors

The protocol lives in [`pyunipolsai`](pyunipolsai/), a standalone async client with no Home Assistant dependency and its own test suite. The integration is a thin layer over it.

- [`docs/FINDINGS.md`](docs/FINDINGS.md): how the API was worked out, and every counter-intuitive thing it does
- [`docs/CAPTURE.md`](docs/CAPTURE.md): capturing live traffic from the Android app
- [`docs/endpoints.txt`](docs/endpoints.txt): every endpoint extracted from the app

```bash
scripts/setup
scripts/test
```

## Interoperability and European law

This exists because Unipol publishes no API for the Unibox. The box records where my car is and how it is driven, and that data is reachable only through their app. This project closes that gap, and the work behind it sits squarely inside the exceptions European law provides for exactly this situation.

**Directive 2009/24/EC on the legal protection of computer programs.** Article 5(3) entitles a person with a right to use a copy of a program to observe, study and test how it functions in order to determine the ideas and principles underlying it, without the rightholder's authorisation. Article 6 permits reproducing and translating the code where that is indispensable to obtain the information needed to make an independently created program interoperate. `pyunipolsai` is that independently created program. Article 8 is worth quoting in full: *"Any contractual provisions contrary to Article 6 or to the exceptions provided for in Article 5(2) and (3) shall be null and void."* A clause in an app's conditions of use cannot remove a right the Directive grants.

**Regulation (EU) 2023/2854, the Data Act**, applicable since 12 September 2025. Article 4 gives the user of a connected product the right to access the data generated by their use of it, and obliges the data holder to make that data available, readily, in a commonly used machine-readable format, and of the same quality as is available to the data holder. Article 5 extends that to sharing it with a third party of the user's choosing. A telematics box fitted to a car is a connected product.

**Regulation (EU) 2016/679, GDPR.** The positions are personal data about the policyholder. Article 15 grants a right of access to them and Article 20 a right to receive them in a structured, commonly used, machine-readable format.

### What this deliberately does not do

It defeats no authentication, breaks no certificate pinning, and circumvents no technical protection measure. There was nothing to circumvent: the app carries no pinning and trusts user certificates, which is documented in [`docs/FINDINGS.md`](docs/FINDINGS.md) along with everything else. It signs in with the account holder's own credentials and reads that account's own data, through the same endpoints the app uses, and it respects the server-side quotas rather than working around them.

It reproduces none of Unipol's code, competes with no product of theirs, and reveals nothing beyond what interoperability requires. The notes in `docs/` are published so this work can be audited rather than taken on trust.

If Unipol would rather this went through a documented API, that is a better outcome for everyone and I would retire this in favour of it.

Not legal advice, and not a claim on Unipol's behalf. If anyone at Unipol thinks something here oversteps, [open an issue](https://github.com/FezVrasta/ha-unipolsai/issues) and I will engage with it properly.
