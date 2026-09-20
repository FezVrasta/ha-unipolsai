# Capturing live traffic

The app has no certificate pinning and its `network_security_config` trusts user CAs, so a plain mitmproxy setup works. No Frida, no system CA, no repackaging.

I can't log in for you, so the login step is yours. Everything up to it is scripted.

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

The five things static analysis couldn't answer:

- **`x-ibm-client-id` / `x-ibm-client-secret` / `x-unipol-tenant`** on any request. These are the credentials the integration needs and they're not in the APK.
- **`POST /hub/login`** response, to confirm the `{"JWT": {...}}` shape and the real `expires_in`.
- **`lastPosition`** response, for the true `date` format, `accuracy` units, and the `dailyFruitions.max` value on your account.
- **A forced refresh**, to see the `pendingRequest: true` → `false` cycle and how long it takes.
- **Whether login triggers an OTP** on a device it hasn't seen before.

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
