"""Model tests.

Fixtures are real payloads captured from the live API, with identifiers
replaced. They exist mainly to pin the parts of this API that are
counter-intuitive: epoch-millisecond dates declared as strings, distances in
metres, a cardinal-letter heading, and an `accuracy` that is a grade rather
than a radius.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pyunipolsai.models import normalise_plate

from pyunipolsai import Notification, Position, Service, UsageStats, Vehicle

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("AB123CD", "IT-AB123CD"),
        ("ab123cd", "IT-AB123CD"),
        (" ab 123 cd ", "IT-AB123CD"),
        ("IT-AB123CD", "IT-AB123CD"),
    ],
)
def test_normalise_plate(raw: str, expected: str) -> None:
    assert normalise_plate(raw) == expected


class TestPosition:
    def test_parses_real_payload(self) -> None:
        position = Position.from_api(load("last_position")["lastPosition"])
        assert position.latitude == 45.4642
        assert position.longitude == 9.19
        assert position.speed == 0
        assert position.pending_request is False

    def test_date_is_epoch_millis_not_a_string(self) -> None:
        """The app declares this field String; the wire sends a number."""
        position = Position.from_api(load("last_position")["lastPosition"])
        assert position.timestamp == datetime(2026, 9, 20, 7, 28, 31, tzinfo=UTC)

    def test_heading_is_cardinal_with_degrees_derived(self) -> None:
        position = Position.from_api({"heading": "NE"})
        assert position.heading == "NE"
        assert position.heading_degrees == 45

    def test_unknown_heading_has_no_degrees(self) -> None:
        assert Position.from_api({"heading": "??"}).heading_degrees is None

    def test_accuracy_is_exposed_as_quality_not_metres(self) -> None:
        """Naming matters here: 1 is a grade, not a one-metre fix."""
        position = Position.from_api(load("last_position")["lastPosition"])
        assert position.quality == 1
        assert not hasattr(position, "accuracy")

    def test_empty_payload_is_survivable(self) -> None:
        position = Position.from_api(None)
        assert position.latitude is None
        assert position.quota.remaining is None


class TestQuota:
    def test_remaining_and_exhausted(self) -> None:
        quota = Position.from_api(load("last_position")["lastPosition"]).quota
        assert (quota.used, quota.limit) == (0, 5)
        assert quota.remaining == 5
        assert quota.exhausted is False

    def test_exhausted_when_spent(self) -> None:
        quota = Position.from_api({"dailyFruitions": {"current": 5, "max": 5}}).quota
        assert quota.remaining == 0
        assert quota.exhausted is True

    def test_never_goes_negative(self) -> None:
        quota = Position.from_api({"dailyFruitions": {"current": 9, "max": 5}}).quota
        assert quota.remaining == 0


class TestVehicle:
    def test_parses_and_prefixes_plate(self) -> None:
        contracts = load("contracts")["auto"]["contrattiAuto"]
        vehicle = Vehicle.from_api(contracts[0])
        assert vehicle is not None
        assert vehicle.plate == "AB123CD"
        assert vehicle.api_plate == "IT-AB123CD"
        assert vehicle.make == "VOLKSWAGEN"
        assert vehicle.device.imei == "000000000000000"
        assert vehicle.usable is True

    def test_inactive_terminal_is_not_usable(self) -> None:
        contracts = load("contracts")["auto"]["contrattiAuto"]
        vehicle = Vehicle.from_api(contracts[1])
        assert vehicle is not None
        assert vehicle.terminal_active is False
        assert vehicle.usable is False

    def test_missing_plate_yields_nothing(self) -> None:
        assert Vehicle.from_api({"veicolo": {}}) is None


class TestService:
    def test_parses_credit_pool(self) -> None:
        services = {
            s["serviceName"]: Service.from_api(s)
            for s in load("vehicle_vas")["vehicleVAS"]
        }
        car_finder = services["carFinder"]
        assert car_finder.activated is True
        assert car_finder.requires_credits is True
        assert car_finder.credits_available == 9

    def test_statistics_needs_no_credits(self) -> None:
        services = {
            s["serviceName"]: Service.from_api(s)
            for s in load("vehicle_vas")["vehicleVAS"]
        }
        assert services["rangeStatistics"].requires_credits is False


class TestNotification:
    def test_parses_real_payload(self) -> None:
        raw = load("notifications")["serviceNotifications"][0]
        notification = Notification.from_api(raw)
        assert notification.occurred_at == datetime(2026, 9, 20, 6, 32, 37, tzinfo=UTC)
        assert notification.latitude == 45.48
        assert notification.provider == "Alfa"

    def test_zero_speed_limit_becomes_none(self) -> None:
        """Zeroed fields become None.

        `speedLimitValue` is shared across alert types and comes back zero
        where it has no meaning, e.g. for engineOn.
        """
        raw = load("notifications")["serviceNotifications"][0]
        assert Notification.from_api(raw).speed_limit is None


class TestUsageStats:
    def test_converts_metres_and_seconds(self) -> None:
        usage = UsageStats.from_api(load("usage")["vehicleUsages"][0])
        assert usage.distance_m("total") == 5431730
        assert usage.distance_km("total") == 5431.7
        assert usage.time_s("total") == 420215
        assert usage.time_h("total") == 116.73

    def test_average_speed_is_plausible(self) -> None:
        """Sanity-check the units.

        Metres over seconds should land in a believable range for mixed
        driving. Treating distance as kilometres would put this at about
        46,000 km/h.
        """
        usage = UsageStats.from_api(load("usage")["vehicleUsages"][0])
        kmh = usage.distance_km() / usage.time_h()
        assert 20 < kmh < 90

    def test_breakdowns(self) -> None:
        usage = UsageStats.from_api(load("usage")["vehicleUsages"][0])
        assert usage.distance_km("city") == 1378.4
        assert usage.distance_km("highway") == 1888.3
        assert usage.distance_km("monday") == 749.5
        assert usage.time_h("city") == 41.65

    def test_metadata(self) -> None:
        usage = UsageStats.from_api(load("usage")["vehicleUsages"][0])
        assert usage.days_analysed == 91
        assert usage.top_province == "Province"
        assert usage.top_province_share == 41.58
        # Equals the contract's dataInizio: dateRange 'g' really is
        # "everything since the policy started".
        assert usage.period_start == datetime(2026, 6, 20, 0, 0, tzinfo=UTC)

    def test_unknown_kind_is_none_not_a_crash(self) -> None:
        usage = UsageStats.from_api(load("usage")["vehicleUsages"][0])
        assert usage.distance_km("spaceship") is None

    def test_empty_payload(self) -> None:
        assert UsageStats.from_api(None).distance_km() is None
