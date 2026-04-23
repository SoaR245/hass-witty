"""Switch platform for witty_one."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components import bluetooth
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.exceptions import HomeAssistantError

from custom_components.witty_one.witty_one.parser import WittyOneChargeMode

from .const import LOGGER
from .entity import WittyOneEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import WittyOneDataUpdateCoordinator
    from .data import WittyOneConfigEntry


# When the switch is turned ON we restore BOOST (full power), unless the
# charger is currently in another non-OFF mode (slow/solar/...) in which case
# we keep it. When turned OFF we always send mode 1 (PAUSE).
DEFAULT_ON_MODE = WittyOneChargeMode.MODE_BOOST


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: WittyOneConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    coordinator = entry.runtime_data.coordinator
    if coordinator.data.charge_mode.mode == 0:
        # Characteristic could not be read at startup, do not expose the switch.
        return
    async_add_entities(
        [
            WittyOneChargeEnableSwitch(
                coordinator=coordinator,
                entity_description=SwitchEntityDescription(
                    key="charge_enabled",
                    translation_key="charge_enabled",
                ),
            )
        ]
    )


class WittyOneChargeEnableSwitch(WittyOneEntity, SwitchEntity):
    """Enable / disable the Witty One charging station.

    Backed by the BLE chargeMode characteristic (`6080`):
        OFF  -> mode 1 (PAUSE)
        ON   -> mode 2 (BOOST), or the previously known mode if non-OFF.
    """

    entity_description: SwitchEntityDescription
    _last_on_mode: int = DEFAULT_ON_MODE

    def __init__(
        self,
        coordinator: WittyOneDataUpdateCoordinator,
        entity_description: SwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, entity_description.key)
        self.entity_description = entity_description
        # Remember the last non-OFF mode so a turn-on restores the user's choice.
        current = coordinator.data.charge_mode.mode
        if current and current != WittyOneChargeMode.MODE_OFF:
            self._last_on_mode = current

    @property
    def is_on(self) -> bool | None:
        """Return True when the charger is in any non-OFF mode."""
        mode = self.coordinator.data.charge_mode.mode
        if mode == 0:
            return None
        return mode != WittyOneChargeMode.MODE_OFF

    async def _write_mode(self, mode: int) -> None:
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

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Enable the charger."""
        # Use last known non-OFF mode if available, otherwise BOOST.
        current = self.coordinator.data.charge_mode.mode
        if current and current != WittyOneChargeMode.MODE_OFF:
            target = current
        else:
            target = self._last_on_mode or DEFAULT_ON_MODE
        await self._write_mode(target)

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Disable (pause) the charger."""
        current = self.coordinator.data.charge_mode.mode
        if current and current != WittyOneChargeMode.MODE_OFF:
            self._last_on_mode = current
        await self._write_mode(WittyOneChargeMode.MODE_OFF)
