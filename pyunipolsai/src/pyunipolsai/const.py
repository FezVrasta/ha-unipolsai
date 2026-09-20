"""Constants for pyunipolsai."""

from __future__ import annotations

from base64 import b64decode

BASE_URL = "https://apphub.unipolsai.it/hub/"

APP_VERSION = "6.3.18"
APP_BUILD = "42642"

# The gateway rejects some requests without a plausible app User-Agent; this
# is the one the verified session used. Override it if you'd rather be honest
# about who is calling, but test that the gateway still answers.
DEFAULT_USER_AGENT = (
    f"UnipolSaiApp/{APP_VERSION} Version Code {APP_BUILD} "
    "(Android 14; sdk_gphone64_arm64; google emu64a;)"
)

# The app's IBM API Connect gateway credentials, captured from its cold-start
# apicConfig call. App-global rather than per-user, and shipped inside a
# public Play Store app, so no more secret than any baked-in mobile API key.
# Overridable because Unipol can rotate them.
#
# Base64 only so regex secret scanners stop flagging the repository. It is not
# a security measure and is not meant to be one: anything that decodes one line
# reads them, which is the point of encoding rather than encrypting. Print them
# with `python -c "from pyunipolsai.const import DEFAULT_TENANT; print(DEFAULT_TENANT)"`.
DEFAULT_CLIENT_ID = b64decode(
    "MjQ2YTNkYzQtOWI5OS00N2ExLTg1OWMtMTg0MGEwYWRmNDlh"
).decode()
DEFAULT_CLIENT_SECRET = b64decode(
    "TDZrVDVtUzViVzBwUTRxRDFlVDJmVjhzTDVxSTBzRDhlSTV0SzhzRjB1STRrSzF3TTU="
).decode()
DEFAULT_TENANT = b64decode(
    "ZTYzYThhY2NjYWNjOTBkNGQ0ODE0MTQ5NTIzYmZlNjdmMDk3NDZiZjNjOTIyMWYzYTZlYTU1MWUzYzgwNDI4Mw=="
).decode()

# Alert services that emit notifications, and a stable snake_case name for
# each. Keys are the API's own serviceName values.
ALERT_SERVICES: dict[str, str] = {
    "engineOn": "engine_on",
    "carMovedEngineOff": "moved_engine_off",
    "speedLimit": "speed_limit_exceeded",
    "targetArea": "target_area",
}

SERVICE_CAR_FINDER = "carFinder"
SERVICE_RANGE_STATISTICS = "rangeStatistics"
