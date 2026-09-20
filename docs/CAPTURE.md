# Capturing live traffic

The app has no certificate pinning and its `network_security_config` trusts user CAs, so a plain mitmproxy setup works. No Frida, no system CA, no repackaging.

**The APIC credentials are already captured.** They're in `.env.local`. The app fetches them at cold start before any login, so that part needed no account and is done. What's left needs an authenticated session, and that means someone typing a password into the emulator.

Two things to know before you start:

- **The app force-updates.** A sideloaded mirror APK installs but won't get past the launch screen. Install it, then update through the Play Store on the emulator (`com.android.vending` is present on the google_apis image even with `PlayStore.enabled=no`).
- **Interception is scoped to `apphub.unipolsai.it`.** Proxying everything breaks the app's web content: `www.unipol.it` sends a `Set-Cookie` with surrounding whitespace that trips mitmproxy's HTTP/2 parser, and the analytics hosts fail loudly against a DNS sinkhole. `start-capture.sh` passes `--allow-hosts` so everything else goes through as raw TCP.

## One-time setup

Boot the emulator and wire up the proxy:

```bash
./tools/start-capture.sh
```

That script boots the `unipol_capture` AVD if it isn't running, starts `mitmdump` on port 8080 writing to `captures/`, installs the mitmproxy CA as a **user** certificate, and points the emulator's global proxy at the host.

## Capture a session

1. Open the Unipol app on the emulator.
2. Log in with your account.
3. Go to the car section and open the Unibox / vehicle position screen.
4. Force a position refresh so a `?update=true` call goes out.
5. Open the driving statistics screen.

Then pull out the interesting requests:

```bash
./tools/extract-flows.sh
```

That filters the flow dump down to `apphub.unipolsai.it` and writes one JSON file per endpoint into `captures/parsed/`, dropping the Tealium, Firebase and Glassbox noise.

## What to look for

What's still unanswered, in priority order:

- **`lastPosition`** response, for the true `date` format, `accuracy` units, and the `dailyFruitions.max` value on your account. `extract-flows.sh` prints these four fields automatically as soon as it sees one.
- **A forced refresh**, to see the `pendingRequest: true` → `false` cycle and how long it takes. This and `max` together decide the polling design, so they matter more than everything else here.
- **`POST /hub/login`** response, to confirm the `{"JWT": {...}}` shape and the real `expires_in`.
- **Whether login triggers an OTP** on a device it hasn't seen before. There's a lot of OTP machinery in `LoginApi` and none of it has been exercised.
- **`myTelematicContracts`**, to see how vehicles are described and whether the plate is the only usable key.

## Reading the values off the device instead

If you'd rather not proxy, the APIC credentials land in SharedPreferences once the app has run. On the emulator:

```bash
adb shell run-as com.UnipolSaiApp cat /data/data/com.UnipolSaiApp/shared_prefs/UniPicUpPref.xml | grep -i 'ibm\|tenant'
```

`run-as` only works because this is a debuggable-by-default emulator image. It won't work on a physical device with the Play build.

## Cleaning up

```bash
./tools/stop-capture.sh
```

Unsets the emulator proxy and stops mitmdump. The CA stays installed, which is fine for a throwaway AVD but worth remembering.

## A word on what goes in the captures

Flow dumps contain your bearer token, your username and password from the login POST, your plate, and your actual GPS position. `captures/` is gitignored. Keep it that way, and scrub before pasting anything into an issue or a commit.
