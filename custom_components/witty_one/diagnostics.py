"""Diagnostics support for witty_one."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import WittyOneConfigEntry

TO_REDACT = {"unique_id", "address", "title"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: WittyOneConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    health = dataclasses.asdict(coordinator.health)
    for key, value in health.items():
        if hasattr(value, "isoformat"):
            health[key] = value.isoformat()
    if health["last_error"] and entry.unique_id:
        health["last_error"] = health["last_error"].replace(
            entry.unique_id, "**REDACTED**"
        )

    device: dict[str, Any] | None = None
    if (data := coordinator.data) is not None:
        device = {
            "static_information": dataclasses.asdict(data.static_information),
            "general": dataclasses.asdict(data.general),
            "configuration": dataclasses.asdict(data.configuration),
            "energies_read": len(data.energies),
            "phases_states_read": len(data.phases_states),
        }

    return {
        "entry": async_redact_data(
            {"title": entry.title, "unique_id": entry.unique_id}, TO_REDACT
        ),
        "health": health,
        "stale": coordinator.health.stale,
        "pairing_issue": coordinator.health.pairing_issue,
        "protected_data_available": coordinator.protected_data_available,
        "last_update_success": coordinator.last_update_success,
        "connection_path": coordinator.connection_path,
        "advertisement_source": coordinator.advertisement_source,
        "reported_mtu": coordinator.witty.last_mtu,
        "device": device,
    }
