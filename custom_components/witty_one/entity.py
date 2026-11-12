"""BlueprintEntity class."""

from __future__ import annotations

from homeassistant.helpers.device_registry import (
    CONNECTION_BLUETOOTH,
    DeviceInfo,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import WittyOneDataUpdateCoordinator
from .witty_one.parser import model_id_to_name


class WittyOneEntity(CoordinatorEntity[WittyOneDataUpdateCoordinator]):
    """Define a base WittyOne Entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WittyOneDataUpdateCoordinator,
        suffix: str,
        *,
        protected: bool = True,
    ) -> None:
        """
        Initialize.

        Protected entities need an encrypted link to be read; they become
        unavailable when only unprotected values are fresh.
        """
        super().__init__(coordinator)
        self._protected = protected

        self._attr_unique_id = f"{coordinator.config_entry.unique_id}_{suffix}"
        self._attr_device_info = DeviceInfo(
            connections={
                (CONNECTION_BLUETOOTH, (str)(coordinator.config_entry.unique_id))
            },
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            manufacturer=MANUFACTURER,
            name=coordinator.data.static_information.name,
            model=model_id_to_name(coordinator.data.static_information.model),
            model_id=coordinator.data.static_information.model,
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and (
            not self._protected or self.coordinator.protected_data_available
        )
