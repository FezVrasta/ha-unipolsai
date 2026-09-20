"""Async client for the Unipol (UnipolSai) Unibox telematics API."""

from __future__ import annotations

from .client import UnipolSaiClient
from .const import (
    ALERT_SERVICES,
    BASE_URL,
    DEFAULT_CLIENT_ID,
    DEFAULT_CLIENT_SECRET,
    DEFAULT_TENANT,
    DEFAULT_USER_AGENT,
    SERVICE_CAR_FINDER,
    SERVICE_RANGE_STATISTICS,
)
from .exceptions import (
    UnipolSaiAuthError,
    UnipolSaiConnectionError,
    UnipolSaiError,
)
from .models import (
    HEADING_DEGREES,
    Notification,
    Position,
    Quota,
    Service,
    TelematicDevice,
    UsageStats,
    Vehicle,
    normalise_plate,
)

__version__ = ""

__all__ = [
    "ALERT_SERVICES",
    "BASE_URL",
    "DEFAULT_CLIENT_ID",
    "DEFAULT_CLIENT_SECRET",
    "DEFAULT_TENANT",
    "DEFAULT_USER_AGENT",
    "HEADING_DEGREES",
    "SERVICE_CAR_FINDER",
    "SERVICE_RANGE_STATISTICS",
    "Notification",
    "Position",
    "Quota",
    "Service",
    "TelematicDevice",
    "UnipolSaiAuthError",
    "UnipolSaiClient",
    "UnipolSaiConnectionError",
    "UnipolSaiError",
    "UsageStats",
    "Vehicle",
    "__version__",
    "normalise_plate",
]
