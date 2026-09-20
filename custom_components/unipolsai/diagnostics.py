"""Diagnostics dump."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import UnipolSaiUniboxConfigEntry

#: Anything identifying the account, the vehicle or the box, plus the gateway
#: credentials. The plate and the device id are as identifying as a serial.
TO_REDACT = {
    "username",
    "password",
    "ibm_client_id",
    "ibm_client_secret",
    "tenant",
    "unique_id",
    "plate",
    "api_plate",
    "device_id",
    "imei",
    "serial_number",
    "latitude",
    "longitude",
    "event_id",
    "id",
}


def _dump(value: Any) -> Any:
    """Make dataclasses and their nesting JSON-friendly."""
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _dump(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {k: _dump(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_dump(v) for v in value]
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: UnipolSaiUniboxConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data

    vehicles: dict[str, Any] = {}
    for index, (plate, coordinator) in enumerate(data.vehicles.items()):
        usage = data.usage.get(plate)
        # Key by index rather than plate: the key itself would survive
        # redaction of the values.
        vehicles[f"vehicle_{index}"] = {
            "last_update_success": coordinator.last_update_success,
            "vehicle": _dump(coordinator.vehicle),
            "data": _dump(coordinator.data),
            "usage": {
                "last_update_success": usage.last_update_success,
                "data": usage.data.raw if usage.data else None,
            }
            if usage
            else None,
        }

    return async_redact_data(
        {
            "entry": {
                "data": dict(entry.data),
                "options": dict(entry.options),
                "unique_id": entry.unique_id,
            },
            "vehicles": vehicles,
        },
        TO_REDACT,
    )
