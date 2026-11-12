"""Sensor platform for witty_one."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.components.sensor.const import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)

from .entity import WittyOneEntity
from .witty_one.health import UpdatePhase

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from homeassistant.helpers.typing import StateType

    from custom_components.witty_one.witty_one.parser import WittyOneDevice

    from .coordinator import WittyOneDataUpdateCoordinator
    from .data import WittyOneConfigEntry


@dataclass(frozen=True, kw_only=True)
class WittyOneSensorEntityDescription(SensorEntityDescription):
    """Describes WLED sensor entity."""

    exists_fn: Callable[[WittyOneDevice], bool] = lambda _: True
    value_fn: Callable[[WittyOneDevice], datetime | StateType]
    protected: bool = True


@dataclass(frozen=True, kw_only=True)
class WittyOneHealthSensorEntityDescription(SensorEntityDescription):
    """Describes a sensor about the BLE link itself."""

    value_fn: Callable[[WittyOneDataUpdateCoordinator], datetime | StateType]


GENERAL_STATES = {
    1: "idle",  # 256
    2: "wait",  # 512
    4: "wait_energy",  # 1024
    6: "charging",  # 1536
    8: "finish",  # 2048
    16: "reserved",  # 4096
    15728640: "error",
}

CABLE_LOCK_STATES = {
    0: "not_locked",
    1: "locked",
    2: "unlocked",
    3: "blocked_in_locked_position",
    4: "blocked_in_unlocked_position",
    5: "blocked",
}

ACCESS_CONTROL_MODES = {
    0: "anyone",
    1: "badge_only",
}

ENTITY_DESCRIPTIONS: tuple[WittyOneSensorEntityDescription, ...] = (
    WittyOneSensorEntityDescription(
        key="total_energy",
        translation_key="total_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda device: device.energies[3].active_import_energy,
    ),
    WittyOneSensorEntityDescription(
        key="phase1_energy",
        translation_key="phase1_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda device: device.energies[0].active_import_energy,
    ),
    WittyOneSensorEntityDescription(
        key="phase2_energy",
        translation_key="phase2_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda device: device.energies[1].active_import_energy,
    ),
    WittyOneSensorEntityDescription(
        key="phase3_energy",
        translation_key="phase3_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda device: device.energies[2].active_import_energy,
    ),
    WittyOneSensorEntityDescription(
        key="current_session_energy",
        translation_key="current_session_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        value_fn=lambda device: device.current_session.energy,
    ),
    WittyOneSensorEntityDescription(
        key="power",
        translation_key="power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.phases_states[3].active_power,
    ),
    WittyOneSensorEntityDescription(
        key="current_session_duration",
        translation_key="current_session_duration",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda device: device.current_session.duration,
    ),
    WittyOneSensorEntityDescription(
        key="state",
        translation_key="state",
        device_class=SensorDeviceClass.ENUM,
        options=list(GENERAL_STATES.values()),
        value_fn=lambda device: GENERAL_STATES[device.general.mainstate],
        protected=False,
    ),
    WittyOneSensorEntityDescription(
        key="cable_lock",
        translation_key="cable_lock",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=list(CABLE_LOCK_STATES.values()),
        value_fn=lambda device: CABLE_LOCK_STATES.get(device.configuration.cable_lock),
    ),
    WittyOneSensorEntityDescription(
        key="access_control_mode",
        translation_key="access_control_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=list(ACCESS_CONTROL_MODES.values()),
        value_fn=lambda device: ACCESS_CONTROL_MODES.get(
            device.configuration.access_control_mode
        ),
    ),
    WittyOneSensorEntityDescription(
        key="max_current",
        translation_key="max_current",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        value_fn=lambda device: device.configuration.max_current,
    ),
    WittyOneSensorEntityDescription(
        key="reduce_current",
        translation_key="reduce_current",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        value_fn=lambda device: device.configuration.reduce_current,
    ),
    WittyOneSensorEntityDescription(
        key="fallback_current",
        translation_key="fallback_current",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        value_fn=lambda device: device.configuration.fallback_current,
    ),
    WittyOneSensorEntityDescription(
        key="ambient_temperature",
        translation_key="ambient_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.diagnostics.ambient_temperature,
    ),
    WittyOneSensorEntityDescription(
        key="relay_temperature",
        translation_key="relay_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.diagnostics.relay_temperature,
    ),
    WittyOneSensorEntityDescription(
        key="startup_counter",
        translation_key="startup_counter",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda device: device.diagnostics.startup_counter,
    ),
    WittyOneSensorEntityDescription(
        key="vehicle_detection_number",
        translation_key="vehicle_detection_number",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda device: device.diagnostics.vehicle_detection_number,
    ),
    WittyOneSensorEntityDescription(
        key="charging_session_number",
        translation_key="charging_session_number",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda device: device.diagnostics.charging_session_number,
    ),
    WittyOneSensorEntityDescription(
        key="relay4c_commutations",
        translation_key="relay4c_commutations",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda device: device.diagnostics.relay4c_commutations,
    ),
    WittyOneSensorEntityDescription(
        key="relay_out1_commutations",
        translation_key="relay_out1_commutations",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda device: device.diagnostics.relay_out1_commutations,
    ),
    WittyOneSensorEntityDescription(
        key="duration_no_ev_plug",
        translation_key="duration_no_ev_plug",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda device: device.diagnostics.duration_no_ev_plug,
    ),
    WittyOneSensorEntityDescription(
        key="duration_wait_charging",
        translation_key="duration_wait_charging",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda device: device.diagnostics.duration_wait_charging,
    ),
    WittyOneSensorEntityDescription(
        key="duration_effective_load",
        translation_key="duration_effective_load",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda device: device.diagnostics.duration_effective_load,
    ),
    WittyOneSensorEntityDescription(
        key="duration_error",
        translation_key="duration_error",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda device: device.diagnostics.duration_error,
    ),
)

HEALTH_DESCRIPTIONS: tuple[WittyOneHealthSensorEntityDescription, ...] = (
    WittyOneHealthSensorEntityDescription(
        key="last_successful_update",
        translation_key="last_successful_update",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda coordinator: coordinator.health.last_success,
    ),
    WittyOneHealthSensorEntityDescription(
        key="consecutive_errors",
        translation_key="consecutive_errors",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.health.consecutive_errors,
    ),
    WittyOneHealthSensorEntityDescription(
        key="last_failure_phase",
        translation_key="last_failure_phase",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=["none", *UpdatePhase],
        value_fn=lambda coordinator: coordinator.health.last_error_phase or "none",
    ),
    WittyOneHealthSensorEntityDescription(
        key="next_pairing_attempt",
        translation_key="next_pairing_attempt",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda coordinator: coordinator.health.next_pairing_attempt,
    ),
    WittyOneHealthSensorEntityDescription(
        key="connection_path",
        translation_key="connection_path",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.connection_path,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: WittyOneConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        WittyOneSensor(
            coordinator=entry.runtime_data.coordinator,
            entity_description=entity_description,
        )
        for entity_description in ENTITY_DESCRIPTIONS
        if entity_description.exists_fn(coordinator.data)
    )
    async_add_entities(
        WittyOneHealthSensor(coordinator, entity_description)
        for entity_description in HEALTH_DESCRIPTIONS
    )


class WittyOneSensor(WittyOneEntity, SensorEntity):
    """witty_one Sensor class."""

    entity_description: WittyOneSensorEntityDescription

    def __init__(
        self,
        coordinator: WittyOneDataUpdateCoordinator,
        entity_description: WittyOneSensorEntityDescription,
    ) -> None:
        """Initialize the sensor class."""
        super().__init__(
            coordinator,
            entity_description.key,
            protected=entity_description.protected,
        )
        self.entity_description = entity_description

    @property
    def native_value(self) -> datetime | StateType:
        """Return the native value of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)


class WittyOneHealthSensor(WittyOneEntity, SensorEntity):
    """Sensor describing the BLE link, available even when the station is not."""

    entity_description: WittyOneHealthSensorEntityDescription

    def __init__(
        self,
        coordinator: WittyOneDataUpdateCoordinator,
        entity_description: WittyOneHealthSensorEntityDescription,
    ) -> None:
        """Initialize the sensor class."""
        super().__init__(coordinator, entity_description.key, protected=False)
        self.entity_description = entity_description

    @property
    def available(self) -> bool:
        """Return True: link health is known even when the poll failed."""
        return True

    @property
    def native_value(self) -> datetime | StateType:
        """Return the native value of the sensor."""
        return self.entity_description.value_fn(self.coordinator)
