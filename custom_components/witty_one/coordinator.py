"""DataUpdateCoordinator for witty_one."""

from __future__ import annotations

import dataclasses
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.components import bluetooth
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from custom_components.witty_one.witty_one.health import ConnectionHealth, UpdatePhase
from custom_components.witty_one.witty_one.parser import (
    WittyOneDevice,
    WittyOneDeviceData,
    WittyOneUpdateError,
)

from .const import DOMAIN, LOGGER

if TYPE_CHECKING:
    from datetime import datetime

    from bleak.backends.device import BLEDevice
    from homeassistant.core import HomeAssistant

    from .data import WittyOneConfigEntry

UPDATE_INTERVAL = timedelta(minutes=1)
# Failed polls are served with previous values while consecutive_errors is
# below this limit; protected entities become unavailable afterwards.
MAX_RETRY = 4


class WittyOneDataUpdateCoordinator(DataUpdateCoordinator[WittyOneDevice]):
    """Class to manage fetching data from the API."""

    config_entry: WittyOneConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: WittyOneConfigEntry) -> None:
        """Initialize the coordinator for the single configured station."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=UPDATE_INTERVAL,
        )
        self.witty = WittyOneDeviceData(LOGGER)
        self.health = ConnectionHealth()
        self.advertisement_source: str | None = None

    @property
    def address(self) -> str:
        """Return the station address."""
        if not (address := self.config_entry.unique_id):
            msg = "No address found in configuration"
            raise HomeAssistantError(msg)
        return address

    @property
    def pairing_issue_id(self) -> str:
        """Return the repair issue id of this entry."""
        return f"pairing_required_{self.config_entry.entry_id}"

    @property
    def protected_data_available(self) -> bool:
        """Return True when values that require encryption may be shown."""
        return (
            self.health.last_success is not None
            and self.health.consecutive_errors < MAX_RETRY
        )

    @property
    def connection_path(self) -> str | None:
        """Return the scanner used for the last connection, or the last seen."""
        return self.witty.last_connection_path or self.advertisement_source

    def _ble_device(self) -> BLEDevice | None:
        return bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )

    def _update_advertisement_source(self) -> None:
        info = bluetooth.async_last_service_info(
            self.hass, self.address, connectable=True
        )
        if info is None:
            return
        scanner = bluetooth.async_scanner_by_source(self.hass, info.source)
        source = scanner.name if scanner else info.source
        if source != self.advertisement_source:
            LOGGER.debug("%s: advertisement seen via %s", self.address, source)
        self.advertisement_source = source

    def _sync_pairing_issue(self) -> None:
        if self.health.pairing_issue:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self.pairing_issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="pairing_required",
                translation_placeholders={"name": self.config_entry.title},
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, self.pairing_issue_id)

    def _fallback(self, message: str, partial: WittyOneDevice | None) -> WittyOneDevice:
        """Return the best data available after a poll that missed some values."""
        previous = self.data
        if partial is not None:
            # Unprotected values are fresh; protected ones keep their last value
            # until protected_data_available turns False.
            if previous is None:
                return partial
            return dataclasses.replace(previous, general=partial.general)
        if previous is not None and self.health.consecutive_errors < MAX_RETRY:
            LOGGER.warning("Error updating device, using previous data: %s", message)
            return previous
        msg = f"Unable to fetch data: {message}"
        raise UpdateFailed(msg)

    def _failure(
        self,
        now: datetime,
        phase: UpdatePhase,
        message: str,
        partial: WittyOneDevice | None,
    ) -> WittyOneDevice:
        self.health.record_failure(now, phase, message)
        if phase == UpdatePhase.PAIR:
            LOGGER.warning(
                "%s: encryption request failed (%s), next attempt after %s",
                self.address,
                message,
                self.health.next_pairing_attempt,
            )
        self._sync_pairing_issue()
        return self._fallback(message, partial)

    async def _async_update_data(self) -> WittyOneDevice:
        """Update data via library."""
        address = self.address
        LOGGER.debug("Updating data from %s ", address)

        now = dt_util.utcnow()
        if not (ble_device := self._ble_device()):
            msg = f"Could not find Witty One device with address {address}"
            return self._failure(now, UpdatePhase.DISCOVERY, msg, None)
        self._update_advertisement_source()

        def ble_device_callback() -> BLEDevice:
            return self._ble_device() or ble_device

        try:
            if not self.health.pairing_allowed(now):
                LOGGER.debug(
                    "%s: encryption deferred until %s",
                    address,
                    self.health.next_pairing_attempt,
                )
                partial = await self.witty.read_unprotected(
                    ble_device, ble_device_callback
                )
                self.health.record_deferred()
                return self._fallback("encryption deferred", partial)
            data = await self.witty.update_device(ble_device, ble_device_callback)
        except WittyOneUpdateError as err:
            return self._failure(now, err.phase, str(err), err.partial)

        self.health.record_success(now)
        self._sync_pairing_issue()
        return data

    async def async_set_charge_mode(self, mode: int) -> None:
        """Set the charge mode on the device."""
        if not (ble_device := self._ble_device()):
            msg = f"Could not find Witty One device with address {self.address}"
            raise HomeAssistantError(msg)

        def ble_device_callback() -> BLEDevice:
            return self._ble_device() or ble_device

        try:
            await self.witty.write_charge_mode(ble_device, mode, ble_device_callback)
        except WittyOneUpdateError as err:
            if err.phase == UpdatePhase.PAIR:
                self.health.record_pairing_failure(dt_util.utcnow())
                self._sync_pairing_issue()
                self.async_update_listeners()
            msg = f"Unable to set charge mode: {err}"
            raise HomeAssistantError(msg) from err

        self.health.record_pairing_success()
        self._sync_pairing_issue()
        await self.async_request_refresh()
