"""Constants for the UnipolSai Unibox integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "unipolsai"

BASE_URL = "https://apphub.unipolsai.it/hub/"

# The app's own User-Agent. The verified session used this string; an honest one
# has not been tested against the gateway yet. See docs/FINDINGS.md.
APP_VERSION = "6.3.18"
APP_BUILD = "42642"
USER_AGENT = (
    f"UnipolSaiApp/{APP_VERSION} Version Code {APP_BUILD} "
    "(Android 14; sdk_gphone64_arm64; google emu64a;)"
)

CONF_CLIENT_ID = "ibm_client_id"
CONF_CLIENT_SECRET = "ibm_client_secret"
CONF_TENANT = "tenant"

# The app's IBM API Connect gateway credentials, captured from the cold-start
# apicConfig call (see docs/CAPTURE.md). These are app-global, not per-user:
# the same three work for every account, and they ship inside a public Play
# Store app, so they are no more secret than any baked-in mobile API key.
#
# They are defaults, not constants, because Unipol can rotate them. When that
# happens a user can override them from the integration's options without
# waiting for a release. Update these here too, so new installs work.
DEFAULT_CLIENT_ID = "246a3dc4-9b99-47a1-859c-1840a0adf49a"
DEFAULT_CLIENT_SECRET = "L6kT5mS5bW0pQ4qD1eT2fV8sL5qI0sD8eI5tK8sF0uI4kK1wM5"
DEFAULT_TENANT = (
    "e63a8acccacc90d4d4814149523bfe67f09746bf3c9221f3a6ea551e3c804283"
)

# Reads are free: dailyFruitions only moves for update=true. Five minutes is
# plenty given the box reports on its own schedule anyway.
SCAN_INTERVAL = timedelta(minutes=5)
# rangeStatistics needs no credits, but the numbers change daily at most.
USAGE_SCAN_INTERVAL = timedelta(hours=6)

# A forced fix takes ~5 minutes to resolve, and can resolve to "no answer".
REFRESH_POLL_INTERVAL = 30
REFRESH_TIMEOUT = 420

# Alert services that produce notifications, and the HA event type each maps
# to. Keys are serviceName values from vehicleVAS.
ALERT_SERVICES = {
    "engineOn": "engine_on",
    "carMovedEngineOff": "moved_engine_off",
    "speedLimit": "speed_limit_exceeded",
    "targetArea": "target_area",
}

# Observed cardinal headings. The API returns a letter, not degrees.
HEADING_DEGREES = {
    "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5,
    "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5,
    "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5,
    "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5,
}
