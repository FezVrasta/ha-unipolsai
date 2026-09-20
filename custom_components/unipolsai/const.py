"""Constants for the UnipolSai Unibox.

Protocol knowledge lives in the `pyunipolsai` library, not here.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "unipolsai"

PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.EVENT,
    Platform.SENSOR,
]

CONF_CLIENT_ID: Final = "ibm_client_id"
CONF_CLIENT_SECRET: Final = "ibm_client_secret"
CONF_TENANT: Final = "tenant"

#: Position and service reads cost nothing: only a forced refresh touches the
#: daily quota. This is really about how fresh the box's own reports need to be.
SCAN_INTERVAL: Final = timedelta(minutes=5)

#: Driving statistics need no credits either, but only change daily.
USAGE_SCAN_INTERVAL: Final = timedelta(hours=6)

#: A forced fix resolves in about five minutes, and can resolve to "no answer".
REFRESH_POLL_INTERVAL: Final = 30
REFRESH_TIMEOUT: Final = 420
