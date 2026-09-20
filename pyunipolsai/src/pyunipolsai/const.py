"""Constants for pyunipolsai."""

from __future__ import annotations

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
DEFAULT_CLIENT_ID = "246a3dc4-9b99-47a1-859c-1840a0adf49a"
DEFAULT_CLIENT_SECRET = "L6kT5mS5bW0pQ4qD1eT2fV8sL5qI0sD8eI5tK8sF0uI4kK1wM5"
DEFAULT_TENANT = "e63a8acccacc90d4d4814149523bfe67f09746bf3c9221f3a6ea551e3c804283"

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
