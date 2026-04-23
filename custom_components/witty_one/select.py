"""Select platform for witty_one."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components import bluetooth
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.exceptions import HomeAssistantError

from custom_components.witty_one.witty_one.parser import WittyOneChargeMode

from .const import LOGGER
from .entity import WittyOneEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import WittyOneDataUpdateCoordinator
    from .data import WittyOneConfigEntry


# User-selectable modes (subset of all known modes — solar requires a Modbus
# TCP energy controller that we cannot configure from the integration).
MODE_OPTION_TO_VALUE: dict[str, int] = {
    "off": WittyOneChargeMode.MODE_OFF,
    "boost": WittyOneChargeMode.MODE_BOOST,
    "slow": WittyOneChargeMode.MODE_SLOW,
}
VALUE_TO_MODE_OPTION: dict[int, str] = {v: k for k, v in MODE_OPTION_TO_VALUE.items()}


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: WittyOneConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform."""
    coordinator = entry.runtime_data.coordinator
    if coordinator.data.charge_mode.mode == 0:
        return
    async_add_entities(
        [
            WittyOneChargeModeSelect(
                coordinator=coordinator,
                entity_description=SelectEntityDescription(
                    key="charge_mode_select",
                    translation_key="charge_mode_select",
                    options=list(MODE_OPTION_TO_VALUE.keys()),
                ),
            )
        ]
    )


class WittyOneChargeModeSelect(WittyOneEntity, SelectEntity):
    """Select OFF / BOOST / SLOW charge mode on the Witty One."""

    entity_description: SelectEntityDescription

    def __init__(
        self,
        coordinator: WittyOneDataUpdateCoordinator,
        entity_description: SelectEntityDescription,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, entity_description.key)
        self.entity_description = entity_description
        self._attr_options = entity_description.options or []

    @property
    def current_option(self) -> str | None:
        """Return the currently selected mode, if known."""
        return VALUE_TO_MODE_OPTION.get(self.coordinator.data.charge_mode.mode)

    async def async_select_option(self, option: str) -> None:
        """Write the selected mode to the device."""
        mode = MODE_OPTION_TO_VALUE.get(option)
        if mode is None:
            msg = f"Unsupported charge mode option: {option}"
            raise HomeAssistantError(msg)
        address = self.coordinator.config_entry.unique_id
        if not address:
            msg = "Witty One device address is unknown"
            raise HomeAssistantError(msg)
        ble_device = bluetooth.async_ble_device_from_address(self.hass, address)
        if not ble_device:
            msg = f"Could not find Witty One device with address {address}"
            raise HomeAssistantError(msg)
        try:
            await self.coordinator.witty.write_charge_mode(ble_device, mode)
        except Exception as err:
            LOGGER.exception("Failed to write charge mode")
            msg = f"Failed to write charge mode: {err}"
            raise HomeAssistantError(msg) from err
        await self.coordinator.async_request_refresh()
