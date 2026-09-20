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

# Reads are free: dailyFruitions only moves for update=true. Five minutes is
# plenty given the box reports on its own schedule anyway.
SCAN_INTERVAL = timedelta(minutes=5)
# rangeStatistics needs no credits, but the numbers change daily at most.
USAGE_SCAN_INTERVAL = timedelta(hours=6)

# A forced fix takes ~5 minutes to resolve, and can resolve to "no answer".
REFRESH_POLL_INTERVAL = 30
REFRESH_TIMEOUT = 420

# Observed cardinal headings. The API returns a letter, not degrees.
HEADING_DEGREES = {
    "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5,
    "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5,
    "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5,
    "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5,
}
