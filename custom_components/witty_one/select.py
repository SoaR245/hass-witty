"""Select platform for witty_one."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity

from .entity import WittyOneEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import WittyOneDataUpdateCoordinator
    from .data import WittyOneConfigEntry

# Mapping between the "chargeMode" BLE characteristic (address 6080) raw
# values and Home Assistant select options. Values 0, 4 and 5 are defined in
# the app but not observed on real devices.
CHARGE_MODE_TO_OPTION = {
    1: "off",
    2: "boost",
    3: "slow",
    6: "solar",
    7: "solar_eco",
}
OPTION_TO_CHARGE_MODE = {value: key for key, value in CHARGE_MODE_TO_OPTION.items()}


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: WittyOneConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform."""
    async_add_entities([WittyOneChargeModeSelect(entry.runtime_data.coordinator)])


class WittyOneChargeModeSelect(WittyOneEntity, SelectEntity):
    """Select entity to read and change the Witty One charge mode."""

    _attr_translation_key = "charge_mode"
    _attr_options = list(OPTION_TO_CHARGE_MODE)

    def __init__(self, coordinator: WittyOneDataUpdateCoordinator) -> None:
        """Initialize the charge mode select entity."""
        super().__init__(coordinator, "charge_mode")

    @property
    def current_option(self) -> str | None:
        """Return the current charge mode."""
        return CHARGE_MODE_TO_OPTION.get(
            self.coordinator.data.configuration.charge_mode
        )

    async def async_select_option(self, option: str) -> None:
        """Change the charge mode of the device."""
        await self.coordinator.async_set_charge_mode(OPTION_TO_CHARGE_MODE[option])
