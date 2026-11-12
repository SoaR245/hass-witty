"""Parser for Witty One device."""

import asyncio
import dataclasses
import struct
import time
from typing import TYPE_CHECKING, Any

from bleak import BleakClient
from bleak_retry_connector import (
    close_stale_connections_by_address,
    establish_connection,
)

from .const import (
    ACCESS_CONTROL_MODE_UUID,
    AMBIENT_TEMP_UUID,
    CAR_DETECT_UUID,
    CHARGE_MODE_UUID,
    CHARGING_NUMBER_UUID,
    COMMUTATION_UUID,
    CONFIG_CABLE_LOCK_UUID,
    DEFAULT_CHARGE_STATE_UUID,
    DURATIONS_UUID,
    ELECTRIC_STATE_UUID,
    ENERGY_UUID,
    FALLBACK_CURRENT_UUID,
    MAX_CURRENT_UUID,
    MODEL_UUID,
    NAME_UUID,
    REDUCE_CURRENT_UUID,
    RELAY_TEMP_UUID,
    SESSION_STATE_UUID,
    STARTUP_COUNT_UUID,
    STATE_UUID,
)
from .health import UpdatePhase

if TYPE_CHECKING:
    from collections.abc import Callable
    from logging import Logger
    from uuid import UUID

    from bleak.backends.device import BLEDevice


@dataclasses.dataclass
class WittyOneStaticProperties:
    """Static informations."""

    name: str = ""
    model: str = ""


@dataclasses.dataclass
class WittyOnePhaseEnergy:
    """Different energies for one phase."""

    active_import_energy: float = 0.0
    active_export_energy: float = 0.0
    reactive_import_energy: float = 0.0
    reactive_export_energy: float = 0.0
    apparent_energy: float = 0.0


@dataclasses.dataclass
class WittyOnePhaseState:
    """Voltage, current, power and power factor for one phase."""

    voltage: float = 0.0
    current: float = 0.0
    active_power: float = 0.0
    apparent_power: float = 0.0
    reactive_power: float = 0.0
    power_factor: float = 0.0
    cos_phi: float = 0.0
    quadrant: int = 0
    frequency: float = 0.0


@dataclasses.dataclass
class WittyCurrentSession:
    """Current session data for Witty One device."""

    start: int = 0
    unk1: bytes = b""
    duration: int = 0
    energy: float = 0.0
    unk3: int = 0
    badge: bytes = b""


@dataclasses.dataclass
class WittyOneGeneralState:
    """General state data for Witty One device."""

    mainstate: int = 0
    substate: int = 0


@dataclasses.dataclass
class WittyOneConfiguration:
    """Charging station configuration values."""

    charge_mode: int = 0
    cable_lock: int = 0
    access_control_mode: int = 0
    max_current: int = 0
    reduce_current: int = 0
    fallback_current: int = 0
    default_charge_state: int = 0


@dataclasses.dataclass
class WittyOneDiagnostics:
    """Diagnostic values, mirroring the app's Diagnostic screen."""

    ambient_temperature: float = 0.0
    relay_temperature: float = 0.0
    startup_counter: int = 0
    vehicle_detection_number: int = 0
    charging_session_number: int = 0
    # Order inferred from IEC 61851 states (Ax/Bx/Cx-Dx/F), not verified on a
    # real device yet. See WITTY_ONE_BLE_PROTOCOL.md section 24.2.
    duration_no_ev_plug: int = 0
    duration_wait_charging: int = 0
    duration_effective_load: int = 0
    duration_error: int = 0
    # The wire format has 4 UInt64 slots, the app only names the first two.
    relay4c_commutations: int = 0
    relay_out1_commutations: int = 0


@dataclasses.dataclass
class WittyOneDevice:
    """Reponse data for Witty One device."""

    static_information: WittyOneStaticProperties
    general: WittyOneGeneralState = dataclasses.field(
        default_factory=WittyOneGeneralState
    )
    energies: list[WittyOnePhaseEnergy] = dataclasses.field(default_factory=list)
    phases_states: list[WittyOnePhaseState] = dataclasses.field(default_factory=list)
    current_session: WittyCurrentSession = dataclasses.field(
        default_factory=WittyCurrentSession
    )
    configuration: WittyOneConfiguration = dataclasses.field(
        default_factory=WittyOneConfiguration
    )
    diagnostics: WittyOneDiagnostics = dataclasses.field(
        default_factory=WittyOneDiagnostics
    )


class ParseError(Exception):
    """Error during parse."""


async def _read_string(client: BleakClient, uuid: str | UUID) -> str:
    tmp = await client.read_gatt_char(uuid)
    try:
        (length,) = struct.unpack("<H", tmp[0:2])
        return tmp[2 : 2 + length].rstrip(b"\0").decode("utf-8")
    except struct.error as err:
        msg = (
            f"witty_one for {uuid}, receive buffer[{len(tmp)}] {tmp.hex()} for a string"
        )
        raise ParseError(msg) from err


# Session buffers carry the badge identifier, which must not reach logs.
_REDACTED_BUFFERS = frozenset({"current_session"})


def _dump(buffer: bytearray, property_name: str) -> str:
    return "<redacted>" if property_name in _REDACTED_BUFFERS else buffer.hex()


def _unpack(fmt: str, buffer: bytearray, property_name: str) -> tuple[Any, ...]:
    try:
        return struct.unpack(fmt, buffer)
    except struct.error as err:
        msg = (
            f"witty_one for {property_name} {fmt} receive "
            f"buffer[{len(buffer)}] {_dump(buffer, property_name)}"
        )
        raise ParseError(msg) from err


def _unpack_from(fmt: str, buffer: bytearray, property_name: str) -> tuple[Any, ...]:
    try:
        return struct.unpack_from(fmt, buffer)
    except struct.error as err:
        msg = (
            f"witty_one for {property_name} {fmt} receive "
            f"buffer[{len(buffer)}] {_dump(buffer, property_name)}"
        )
        raise ParseError(msg) from err


async def _read_static_properties(client: BleakClient) -> WittyOneStaticProperties:
    return WittyOneStaticProperties(
        name=await _read_string(client, NAME_UUID),
        model=await _read_string(client, MODEL_UUID),
    )


async def _read_energy(client: BleakClient) -> list[WittyOnePhaseEnergy]:
    tmp = await client.read_gatt_char(ENERGY_UUID)
    values = _unpack("<HQQQQQQQQQQQQQQQQQQQQ", tmp, "energy")
    return [
        WittyOnePhaseEnergy(
            active_import_energy=values[1] / 1000,
            active_export_energy=values[2] / 1000,
            reactive_import_energy=values[3] / 1000,
            reactive_export_energy=values[4] / 1000,
            apparent_energy=values[5] / 1000,
        ),
        WittyOnePhaseEnergy(
            active_import_energy=values[6] / 1000,
            active_export_energy=values[7] / 1000,
            reactive_import_energy=values[8] / 1000,
            reactive_export_energy=values[9] / 1000,
            apparent_energy=values[10] / 1000,
        ),
        WittyOnePhaseEnergy(
            active_import_energy=values[11] / 1000,
            active_export_energy=values[12] / 1000,
            reactive_import_energy=values[13] / 1000,
            reactive_export_energy=values[14] / 1000,
            apparent_energy=values[15] / 1000,
        ),
        WittyOnePhaseEnergy(
            active_import_energy=values[16] / 1000,
            active_export_energy=values[17] / 1000,
            reactive_import_energy=values[18] / 1000,
            reactive_export_energy=values[19] / 1000,
            apparent_energy=values[20] / 1000,
        ),
    ]


async def _read_phases_state(client: BleakClient) -> list[WittyOnePhaseState]:
    tmp = await client.read_gatt_char(ELECTRIC_STATE_UUID)
    values = _unpack("<Hlllllllllllllllllllllllllllllll", tmp, "phases_state")
    return [
        WittyOnePhaseState(
            voltage=values[1] / 1000,
            current=values[2] / 1000,
            active_power=values[3] / 1000,
            apparent_power=values[4] / 1000,
            reactive_power=values[5] / 1000,
            power_factor=values[6] / 1000,
            cos_phi=values[7] / 1000,
            quadrant=values[8],
        ),
        WittyOnePhaseState(
            voltage=values[9] / 1000,
            current=values[10] / 1000,
            active_power=values[11] / 1000,
            apparent_power=values[12] / 1000,
            reactive_power=values[13] / 1000,
            power_factor=values[14] / 1000,
            cos_phi=values[15] / 1000,
            quadrant=values[16],
        ),
        WittyOnePhaseState(
            voltage=values[17] / 1000,
            current=values[18] / 1000,
            active_power=values[19] / 1000,
            apparent_power=values[20] / 1000,
            reactive_power=values[21] / 1000,
            power_factor=values[22] / 1000,
            cos_phi=values[23] / 1000,
            quadrant=values[24],
        ),
        WittyOnePhaseState(
            active_power=values[25] / 1000,
            apparent_power=values[26] / 1000,
            reactive_power=values[27] / 1000,
            power_factor=values[28] / 1000,
            cos_phi=values[29] / 1000,
            quadrant=values[30],
            frequency=values[31] / 1000,
        ),
    ]


async def _current_session(client: BleakClient) -> WittyCurrentSession:
    tmp = await client.read_gatt_char(SESSION_STATE_UUID)
    values = _unpack_from("<HL7sLQB7s", tmp, "current_session")
    return WittyCurrentSession(
        start=values[1],
        unk1=values[2],
        duration=values[3],
        energy=values[4] / 1000,
        unk3=values[5],
        badge=values[6],
    )


async def _read_general_state(client: BleakClient) -> WittyOneGeneralState:
    tmp = await client.read_gatt_char(STATE_UUID)
    values = _unpack_from("<HI", tmp, "general_state")
    return WittyOneGeneralState(mainstate=values[1] >> 8, substate=values[1] & 0xFF)


async def _read_uint8(client: BleakClient, uuid: str | UUID, property_name: str) -> int:
    tmp = await client.read_gatt_char(uuid)
    (_, value) = _unpack_from("<HB", tmp, property_name)
    return value


async def _read_uint16(
    client: BleakClient, uuid: str | UUID, property_name: str
) -> int:
    tmp = await client.read_gatt_char(uuid)
    (_, value) = _unpack_from("<HH", tmp, property_name)
    return value


async def _read_configuration(client: BleakClient) -> WittyOneConfiguration:
    return WittyOneConfiguration(
        charge_mode=await _read_uint8(client, CHARGE_MODE_UUID, "charge_mode"),
        cable_lock=await _read_uint8(client, CONFIG_CABLE_LOCK_UUID, "cable_lock"),
        access_control_mode=await _read_uint8(
            client, ACCESS_CONTROL_MODE_UUID, "access_control_mode"
        ),
        max_current=await _read_uint16(client, MAX_CURRENT_UUID, "max_current"),
        reduce_current=await _read_uint16(
            client, REDUCE_CURRENT_UUID, "reduce_current"
        ),
        fallback_current=await _read_uint16(
            client, FALLBACK_CURRENT_UUID, "fallback_current"
        ),
        default_charge_state=await _read_uint8(
            client, DEFAULT_CHARGE_STATE_UUID, "default_charge_state"
        ),
    )


async def _ambient_temp(client: BleakClient) -> float:
    tmp = await client.read_gatt_char(AMBIENT_TEMP_UUID)
    (_, value, _min_value, _max_value) = _unpack("<Hhhh", tmp, "ambient_temp")
    return value / 100


async def _relay_temp(client: BleakClient) -> float:
    tmp = await client.read_gatt_char(RELAY_TEMP_UUID)
    (_, value, _min_value, _max_value) = _unpack("<Hhhh", tmp, "relay_temp")
    return value / 100


async def _read_uint32(
    client: BleakClient, uuid: str | UUID, property_name: str
) -> int:
    tmp = await client.read_gatt_char(uuid)
    (_, value) = _unpack_from("<HI", tmp, property_name)
    return value


async def _read_uint64(
    client: BleakClient, uuid: str | UUID, property_name: str
) -> int:
    tmp = await client.read_gatt_char(uuid)
    (_, value) = _unpack_from("<HQ", tmp, property_name)
    return value


async def _read_durations(client: BleakClient) -> tuple[int, int, int, int]:
    tmp = await client.read_gatt_char(DURATIONS_UUID)
    values = _unpack_from("<HIIII", tmp, "durations")
    return (values[1], values[2], values[3], values[4])


async def _read_commutations(client: BleakClient) -> tuple[int, int]:
    tmp = await client.read_gatt_char(COMMUTATION_UUID)
    values = _unpack_from("<HQQQQ", tmp, "commutations")
    return (values[1], values[2])


async def _read_diagnostics(client: BleakClient) -> WittyOneDiagnostics:
    ambient_temperature = await _ambient_temp(client)
    relay_temperature = await _relay_temp(client)
    startup_counter = await _read_uint32(client, STARTUP_COUNT_UUID, "startup_counter")
    vehicle_detection_number = await _read_uint64(
        client, CAR_DETECT_UUID, "vehicle_detection_number"
    )
    charging_session_number = await _read_uint64(
        client, CHARGING_NUMBER_UUID, "charging_session_number"
    )
    durations = await _read_durations(client)
    commutations = await _read_commutations(client)
    return WittyOneDiagnostics(
        ambient_temperature=ambient_temperature,
        relay_temperature=relay_temperature,
        startup_counter=startup_counter,
        vehicle_detection_number=vehicle_detection_number,
        charging_session_number=charging_session_number,
        duration_wait_charging=durations[0],
        duration_no_ev_plug=durations[1],
        duration_effective_load=durations[2],
        duration_error=durations[3],
        relay4c_commutations=commutations[0],
        relay_out1_commutations=commutations[1],
    )


STATIC_INFO_HINT = (
    "Fail to read static info, GATT cache cleared;"
    ' try to add CONFIG_BT_GATTC_MAX_CACHE_CHAR: "80"'
    " to sdkconfig_options if you use esphome"
)


class WittyOneUpdateError(Exception):
    """A BLE exchange failed at a given phase."""

    def __init__(
        self,
        phase: UpdatePhase,
        cause: Exception,
        partial: WittyOneDevice | None = None,
    ) -> None:
        """Keep the failing phase and the values read before the failure."""
        detail = f": {cause}" if str(cause) else ""
        super().__init__(f"{phase}: {type(cause).__name__}{detail}")
        self.phase = phase
        self.partial = partial


class WittyOneDeviceData:
    """
    BLE session with a Witty One device.

    A single lock serializes polls and commands, so only one GATT session
    (and one proxy slot) is used at a time.
    """

    def __init__(
        self,
        logger: Logger,
    ) -> None:
        """Initialize the WittyOneDeviceData with a logger."""
        super().__init__()
        self.logger = logger
        self.static_properties: WittyOneStaticProperties | None = None
        self.last_mtu: int | None = None
        self.last_connection_path: str | None = None
        self._lock = asyncio.Lock()

    def _log_phase(
        self, ble_device: BLEDevice, phase: UpdatePhase, start: float
    ) -> None:
        self.logger.debug(
            "%s: %s done in %.2fs", ble_device.address, phase, time.monotonic() - start
        )

    async def _connect(
        self,
        ble_device: BLEDevice,
        ble_device_callback: Callable[[], BLEDevice] | None,
    ) -> BleakClient:
        start = time.monotonic()
        try:
            # Under the session lock: never closes a link still used by us.
            await close_stale_connections_by_address(ble_device.address)
            client = await establish_connection(
                BleakClient,
                ble_device,
                ble_device.address,
                ble_device_callback=ble_device_callback,
            )
        except Exception as err:
            raise WittyOneUpdateError(UpdatePhase.CONNECT, err) from err
        self.last_mtu = client.mtu_size
        # Home Assistant picks the scanner itself; it is only exposed privately.
        scanner = getattr(client, "_connected_scanner", None)
        self.last_connection_path = getattr(scanner, "name", None)
        self.logger.debug(
            "%s: connected via %s, reported mtu %s",
            ble_device.address,
            self.last_connection_path,
            self.last_mtu,
        )
        self._log_phase(ble_device, UpdatePhase.CONNECT, start)
        return client

    async def _disconnect(self, client: BleakClient) -> None:
        try:
            await client.disconnect()
        except Exception:  # must not hide the original error
            self.logger.debug("Error while disconnecting", exc_info=True)

    async def _clear_cache(self, client: BleakClient) -> None:
        if not callable(getattr(client, "clear_cache", None)):
            return
        try:
            await client.clear_cache()  # pyright: ignore[reportAttributeAccessIssue]
        except Exception:  # must not hide the original error
            self.logger.debug("Error while clearing the GATT cache", exc_info=True)

    async def _read_unprotected(
        self, client: BleakClient, ble_device: BLEDevice
    ) -> WittyOneDevice:
        """Read values the station serves without encryption."""
        start = time.monotonic()
        if self.static_properties is None:
            self.static_properties = await _read_static_properties(client)
        device = WittyOneDevice(
            static_information=self.static_properties,
            general=await _read_general_state(client),
        )
        self._log_phase(ble_device, UpdatePhase.READ_UNPROTECTED, start)
        return device

    async def _failure(
        self,
        client: BleakClient,
        phase: UpdatePhase,
        err: Exception,
        partial: WittyOneDevice | None,
    ) -> WittyOneUpdateError:
        if self.static_properties is None:
            self.logger.warning(STATIC_INFO_HINT)
            await self._clear_cache(client)
        elif isinstance(err, ParseError):
            self.logger.warning("Fail to read dynamic info, cache cleared: %s", err)
            await self._clear_cache(client)
        if isinstance(err, ParseError) and phase == UpdatePhase.READ_PROTECTED:
            phase = UpdatePhase.DECODE
        return WittyOneUpdateError(phase, err, partial)

    async def update_device(
        self,
        ble_device: BLEDevice,
        ble_device_callback: Callable[[], BLEDevice] | None = None,
    ) -> WittyOneDevice:
        """
        Read every value.

        Unprotected values are read before the encryption request, so a pairing
        failure still returns them in WittyOneUpdateError.partial.
        """
        async with self._lock:
            client = await self._connect(ble_device, ble_device_callback)
            phase = UpdatePhase.READ_UNPROTECTED
            partial: WittyOneDevice | None = None
            try:
                partial = await self._read_unprotected(client, ble_device)

                phase = UpdatePhase.PAIR
                start = time.monotonic()
                await client.pair()
                self._log_phase(ble_device, phase, start)

                phase = UpdatePhase.READ_PROTECTED
                start = time.monotonic()
                device = await _read_protected(client, partial)
                self._log_phase(ble_device, phase, start)
            except Exception as err:
                raise await self._failure(client, phase, err, partial) from err
            finally:
                await self._disconnect(client)

        return device

    async def read_unprotected(
        self,
        ble_device: BLEDevice,
        ble_device_callback: Callable[[], BLEDevice] | None = None,
    ) -> WittyOneDevice:
        """Read only values available without encryption, without pairing."""
        async with self._lock:
            client = await self._connect(ble_device, ble_device_callback)
            try:
                return await self._read_unprotected(client, ble_device)
            except Exception as err:
                raise await self._failure(
                    client, UpdatePhase.READ_UNPROTECTED, err, None
                ) from err
            finally:
                await self._disconnect(client)

    async def write_charge_mode(
        self,
        ble_device: BLEDevice,
        mode: int,
        ble_device_callback: Callable[[], BLEDevice] | None = None,
    ) -> None:
        """Write the charge mode to the device."""
        async with self._lock:
            client = await self._connect(ble_device, ble_device_callback)
            phase = UpdatePhase.PAIR
            try:
                await client.pair()
                phase = UpdatePhase.WRITE
                await client.write_gatt_char(
                    CHARGE_MODE_UUID, struct.pack("<HB", 1, mode), response=True
                )
            except Exception as err:
                raise WittyOneUpdateError(phase, err) from err
            finally:
                await self._disconnect(client)


async def _read_protected(
    client: BleakClient, partial: WittyOneDevice
) -> WittyOneDevice:
    return dataclasses.replace(
        partial,
        energies=await _read_energy(client),
        phases_states=await _read_phases_state(client),
        current_session=await _current_session(client),
        configuration=await _read_configuration(client),
        diagnostics=await _read_diagnostics(client),
    )


def model_id_to_name(model_id: str) -> str:
    """Convert model id to a string."""
    match model_id:
        case "XVR111STI":
            return "Witty one 1x11kW 3P"
        case "XVR107STP":
            return "Witty one 1x7kW 1P"
        case "XVR107STI":
            return "Witty one 1x7kW 1P"
        case _:
            return "Witty unknown"
