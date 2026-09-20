"""Typed models for the Unipol telematics API.

The API's own types are not trustworthy: dates are declared `String` in the
app but sent as epoch milliseconds, distances are metres, times are seconds,
`heading` is a cardinal letter rather than degrees, and `accuracy` is a small
quality grade rather than a radius. Every one of those is normalised here so
callers never have to know.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# The API returns a cardinal letter. Degrees are offered as a convenience;
# the resolution loss is the API's, not ours.
HEADING_DEGREES: dict[str, float] = {
    "N": 0,
    "NNE": 22.5,
    "NE": 45,
    "ENE": 67.5,
    "E": 90,
    "ESE": 112.5,
    "SE": 135,
    "SSE": 157.5,
    "S": 180,
    "SSW": 202.5,
    "SW": 225,
    "WSW": 247.5,
    "W": 270,
    "WNW": 292.5,
    "NW": 315,
    "NNW": 337.5,
}


def _dt(value: Any) -> datetime | None:
    """Epoch milliseconds to an aware datetime."""
    if not isinstance(value, (int, float)):
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC)


@dataclass(frozen=True, slots=True)
class Quota:
    """The daily budget for *forced* position refreshes.

    Plain reads do not count against this; only `update=true` does.
    """

    used: int | None = None
    limit: int | None = None

    @property
    def remaining(self) -> int | None:
        """Forced refreshes left today, or None if the API did not say."""
        if self.used is None or self.limit is None:
            return None
        return max(0, self.limit - self.used)

    @property
    def exhausted(self) -> bool:
        """Whether the daily budget is spent."""
        return self.remaining == 0

    @classmethod
    def from_api(cls, data: dict | None) -> Quota:
        """Build from a `dailyFruitions` object."""
        data = data or {}
        return cls(used=data.get("current"), limit=data.get("max"))


@dataclass(frozen=True, slots=True)
class Position:
    """A vehicle position reading."""

    latitude: float | None = None
    longitude: float | None = None
    speed: int | None = None
    heading: str | None = None
    quality: int | None = None
    timestamp: datetime | None = None
    pending_request: bool = False
    quota: Quota = field(default_factory=Quota)

    @property
    def heading_degrees(self) -> float | None:
        """Bearing, if the cardinal letter maps to one."""
        return HEADING_DEGREES.get(self.heading or "")

    @classmethod
    def from_api(cls, data: dict | None) -> Position:
        """Build from a `lastPosition` object."""
        data = data or {}
        return cls(
            latitude=data.get("lat"),
            longitude=data.get("lon"),
            speed=data.get("speed"),
            heading=data.get("heading"),
            # NOT metres. A small integer grade; do not pass it off as a
            # GPS accuracy radius.
            quality=data.get("accuracy"),
            timestamp=_dt(data.get("date")),
            pending_request=bool(data.get("pendingRequest")),
            quota=Quota.from_api(data.get("dailyFruitions")),
        )


@dataclass(frozen=True, slots=True)
class TelematicDevice:
    """The black box itself."""

    device_id: str | None = None
    imei: str | None = None
    device_type: str | None = None

    @classmethod
    def from_api(cls, data: dict | None) -> TelematicDevice:
        """Build from a `dispositivoTelematico` object."""
        data = data or {}
        return cls(
            device_id=data.get("idDispositivo"),
            imei=data.get("imei"),
            device_type=data.get("tipoDispositivo"),
        )


@dataclass(frozen=True, slots=True)
class Vehicle:
    """A vehicle with a Unibox on it."""

    plate: str
    make: str | None = None
    model: str | None = None
    contract_id: str | None = None
    contract_open: bool = False
    terminal_active: bool = False
    device: TelematicDevice = field(default_factory=TelematicDevice)

    @property
    def api_plate(self) -> str:
        """Country-prefixed plate, which is what every path segment wants."""
        return normalise_plate(self.plate)

    @property
    def usable(self) -> bool:
        """Whether it's worth talking to this vehicle at all."""
        return self.contract_open and self.terminal_active

    @classmethod
    def from_api(cls, data: dict | None) -> Vehicle | None:
        """Build from one contract, or None if it carries no plate."""
        data = data or {}
        vehicle = data.get("veicolo") or {}
        plate = vehicle.get("targa")
        if not plate:
            return None
        return cls(
            plate=plate,
            make=vehicle.get("marca"),
            model=vehicle.get("modello"),
            contract_id=data.get("identificativoTelematico"),
            contract_open=data.get("statoContratto") == "open",
            terminal_active=data.get("statoTerminale") == "active",
            device=TelematicDevice.from_api(data.get("dispositivoTelematico")),
        )


@dataclass(frozen=True, slots=True)
class Service:
    """One value-added service on the box.

    `credits_available` is a slower, separate budget from `Quota`: it pays for
    having the service switched on, not for each read.
    """

    name: str
    enabled: bool = False
    activated: bool = False
    requires_credits: bool = False
    credits_available: int | None = None
    credits_used: int | None = None
    recharge_owner: str | None = None

    @classmethod
    def from_api(cls, data: dict) -> Service:
        """Build from one `vehicleVAS` entry."""
        return cls(
            name=data["serviceName"],
            enabled=bool(data.get("isServiceEnabled")),
            activated=bool(data.get("isServiceActivated")),
            requires_credits=bool(data.get("serviceRequiredCredits")),
            credits_available=data.get("serviceAvailableCredits"),
            credits_used=data.get("serviceCreditUsed"),
            recharge_owner=data.get("rechargeOwnership"),
        )


@dataclass(frozen=True, slots=True)
class Notification:
    """An alert event produced by one service.

    Carries its own coordinates, which are where the event happened and are
    independent of the vehicle's current position.
    """

    id: str
    occurred_at: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None
    speed: int | None = None
    speed_limit: int | None = None
    plate: str | None = None
    provider: str | None = None

    @classmethod
    def from_api(cls, data: dict) -> Notification:
        """Build from one `serviceNotifications` entry."""
        return cls(
            id=data["id"],
            occurred_at=_dt(data.get("eventDate")),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            speed=data.get("speed"),
            # Zeroed for services where it has no meaning, e.g. engineOn.
            speed_limit=data.get("speedLimitValue") or None,
            plate=data.get("vehiclePlate"),
            provider=data.get("tspName"),
        )


@dataclass(frozen=True, slots=True)
class UsageStats:
    """Driving statistics.

    The API sends **metres** and **seconds**. Raw values are kept as sent and
    the convenience properties convert, so nothing is lost to rounding.
    """

    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def period_start(self) -> datetime | None:
        """Start of the window these figures cover."""
        return _dt(self.raw.get("fromDate"))

    @property
    def period_end(self) -> datetime | None:
        """End of the window these figures cover."""
        return _dt(self.raw.get("toDate"))

    @property
    def days_analysed(self) -> int | None:
        """How many days went into the analysis."""
        return self.raw.get("totalDaysUsedForAnalysis")

    @property
    def top_province(self) -> str | None:
        """Province with the most distance driven in it."""
        return self.raw.get("higherMileageProvinceFullName")

    @property
    def top_province_share(self) -> float | None:
        """Percentage of distance driven in that province."""
        return self.raw.get("higherMileageProvinceDrivingPerc")

    def distance_m(self, kind: str = "total") -> int | None:
        """Distance in metres.

        `kind` is total, city, extraUrban, highway, other, daylight, or a
        weekday name such as monday.
        """
        return self.raw.get(_DISTANCE_FIELDS.get(kind, kind))

    def distance_km(self, kind: str = "total") -> float | None:
        """Distance in kilometres, rounded to one decimal."""
        value = self.distance_m(kind)
        return None if value is None else round(value / 1000, 1)

    def time_s(self, kind: str = "total") -> int | None:
        """Driving time in seconds, same `kind` vocabulary as distance."""
        return self.raw.get(_TIME_FIELDS.get(kind, kind))

    def time_h(self, kind: str = "total") -> float | None:
        """Driving time in hours, rounded to two decimals."""
        value = self.time_s(kind)
        return None if value is None else round(value / 3600, 2)

    @classmethod
    def from_api(cls, data: dict | None) -> UsageStats:
        """Build from one `vehicleUsages` entry."""
        return cls(raw=data or {})


_KINDS = (
    "total",
    "city",
    "extraUrban",
    "highway",
    "other",
    "daylight",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
_DISTANCE_FIELDS = {
    k: ("totalDistance" if k == "total" else f"{k}DrivingDistance") for k in _KINDS
}
_TIME_FIELDS = {
    k: ("totalDrivingTime" if k == "total" else f"{k}DrivingTime") for k in _KINDS
}


def normalise_plate(plate: str) -> str:
    """`AB123CD` to `IT-AB123CD`. A bare plate is rejected by the API."""
    plate = plate.strip().upper().replace(" ", "")
    return plate if "-" in plate else f"IT-{plate}"
