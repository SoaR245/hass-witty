"""Tests for the BLE session handling of the Witty One parser."""

import asyncio
import logging
import struct
from types import SimpleNamespace
from typing import Any

import pytest
from witty_one import const, parser
from witty_one.health import UpdatePhase
from witty_one.parser import WittyOneDeviceData, WittyOneUpdateError

UNPROTECTED = {const.NAME_UUID, const.MODEL_UUID, const.STATE_UUID}


def _string(value: str) -> bytes:
    return struct.pack("<H", len(value)) + value.encode()


VALUES: dict[str, bytes] = {
    const.NAME_UUID: _string("Witty-test"),
    const.MODEL_UUID: _string("XVR111STI"),
    const.STATE_UUID: struct.pack("<HI", 4, 0x0600),
    const.ENERGY_UUID: struct.pack("<H20Q", 160, *range(1000, 21000, 1000)),
    const.ELECTRIC_STATE_UUID: struct.pack("<H31l", 124, *range(31)),
    const.SESSION_STATE_UUID: struct.pack(
        "<HL7sLQB7s", 32, 1, b"\0" * 7, 60, 2000, 0, b"\0" * 7
    ),
    const.CHARGE_MODE_UUID: struct.pack("<HB", 1, 2),
    const.CONFIG_CABLE_LOCK_UUID: struct.pack("<HB", 1, 1),
    const.ACCESS_CONTROL_MODE_UUID: struct.pack("<HB", 1, 0),
    const.MAX_CURRENT_UUID: struct.pack("<HH", 2, 16),
    const.REDUCE_CURRENT_UUID: struct.pack("<HH", 2, 8),
    const.FALLBACK_CURRENT_UUID: struct.pack("<HH", 2, 6),
    const.DEFAULT_CHARGE_STATE_UUID: struct.pack("<HB", 1, 0),
    const.AMBIENT_TEMP_UUID: struct.pack("<Hhhh", 6, 2000, 0, 0),
    const.RELAY_TEMP_UUID: struct.pack("<Hhhh", 6, 2500, 0, 0),
    const.STARTUP_COUNT_UUID: struct.pack("<HI", 4, 3),
    const.CAR_DETECT_UUID: struct.pack("<HQ", 8, 4),
    const.CHARGING_NUMBER_UUID: struct.pack("<HQ", 8, 5),
    const.DURATIONS_UUID: struct.pack("<HIIII", 16, 1, 2, 3, 4),
    const.COMMUTATION_UUID: struct.pack("<HQQQQ", 32, 1, 2, 3, 4),
}


class Radio:
    """Fake BLE stack recording sessions and GATT operations."""

    def __init__(
        self,
        *,
        pair_error: Exception | None = None,
        values: dict[str, bytes] | None = None,
    ) -> None:
        self.pair_error = pair_error
        self.clear_cache_error: Exception | None = None
        self.values = values or VALUES
        self.events: list[Any] = []
        self.sessions = 0
        self.max_sessions = 0
        self.inflight = 0
        self.max_inflight = 0

    async def close_stale_connections_by_address(self, _address: str) -> None:
        # A stale close while a session is open would drop our own link.
        assert self.sessions == 0
        self.events.append("close_stale")

    async def establish_connection(
        self, _cls: type, _device: Any, _name: str, **_kwargs: Any
    ) -> FakeClient:
        self.sessions += 1
        self.max_sessions = max(self.max_sessions, self.sessions)
        await asyncio.sleep(0)
        self.events.append("connect")
        return FakeClient(self)


class FakeClient:
    """Fake BleakClient."""

    mtu_size = 23

    def __init__(self, radio: Radio) -> None:
        self.radio = radio

    async def _op(self, event: Any) -> None:
        self.radio.inflight += 1
        self.radio.max_inflight = max(self.radio.max_inflight, self.radio.inflight)
        await asyncio.sleep(0)
        self.radio.inflight -= 1
        self.radio.events.append(event)

    async def pair(self) -> bool:
        await self._op("pair")
        if self.radio.pair_error:
            raise self.radio.pair_error
        return True

    async def read_gatt_char(self, uuid: str) -> bytearray:
        await self._op(("read", uuid))
        return bytearray(self.radio.values[uuid])

    async def write_gatt_char(self, uuid: str, data: bytes, **_kwargs: Any) -> None:
        await self._op(("write", uuid, data))

    async def clear_cache(self) -> bool:
        self.radio.events.append("clear_cache")
        if self.radio.clear_cache_error:
            raise self.radio.clear_cache_error
        return True

    async def disconnect(self) -> None:
        self.radio.sessions -= 1
        self.radio.events.append("disconnect")


DEVICE = SimpleNamespace(address="34:CD:B0:00:00:01")


@pytest.fixture
def radio(monkeypatch: pytest.MonkeyPatch) -> Radio:
    fake = Radio()
    monkeypatch.setattr(parser, "establish_connection", fake.establish_connection)
    monkeypatch.setattr(
        parser,
        "close_stale_connections_by_address",
        fake.close_stale_connections_by_address,
    )
    return fake


def _reads(radio: Radio) -> list[str]:
    return [event[1] for event in radio.events if event[0] == "read"]


def test_update_reads_unprotected_values_before_encryption(radio: Radio) -> None:
    device = asyncio.run(WittyOneDeviceData(logging.getLogger()).update_device(DEVICE))

    pair_index = radio.events.index("pair")
    before_pair = {e[1] for e in radio.events[:pair_index] if e[0] == "read"}
    assert before_pair == UNPROTECTED
    assert set(_reads(radio)) == set(VALUES)
    assert radio.max_inflight == 1
    assert radio.events[-1] == "disconnect"
    assert device.general.mainstate == 6
    assert device.energies[3].active_import_energy == 16
    assert device.configuration.fallback_current == 6


def test_pairing_failure_keeps_unprotected_values(radio: Radio) -> None:
    radio.pair_error = TimeoutError()

    with pytest.raises(WittyOneUpdateError) as excinfo:
        asyncio.run(WittyOneDeviceData(logging.getLogger()).update_device(DEVICE))

    assert excinfo.value.phase == UpdatePhase.PAIR
    assert str(excinfo.value) == "pair: TimeoutError"
    assert excinfo.value.partial is not None
    assert excinfo.value.partial.general.mainstate == 6
    assert excinfo.value.partial.static_information.name == "Witty-test"
    assert set(_reads(radio)) == UNPROTECTED
    assert "clear_cache" not in radio.events
    assert radio.events[-1] == "disconnect"


def test_read_unprotected_never_requests_encryption(radio: Radio) -> None:
    device = asyncio.run(
        WittyOneDeviceData(logging.getLogger()).read_unprotected(DEVICE)
    )

    assert "pair" not in radio.events
    assert set(_reads(radio)) == UNPROTECTED
    assert device.general.mainstate == 6
    assert radio.events[-1] == "disconnect"


def test_decode_error_is_reported_and_clears_cache(radio: Radio) -> None:
    radio.values = {**VALUES, const.ENERGY_UUID: b"\x00\x00\x01"}

    with pytest.raises(WittyOneUpdateError) as excinfo:
        asyncio.run(WittyOneDeviceData(logging.getLogger()).update_device(DEVICE))

    assert excinfo.value.phase == UpdatePhase.DECODE
    assert "clear_cache" in radio.events
    assert radio.events[-1] == "disconnect"


def test_poll_and_command_never_share_the_link(radio: Radio) -> None:
    witty = WittyOneDeviceData(logging.getLogger())

    async def run() -> None:
        await asyncio.gather(
            witty.update_device(DEVICE),
            witty.write_charge_mode(DEVICE, 2),
            witty.read_unprotected(DEVICE),
        )

    asyncio.run(run())

    assert radio.max_sessions == 1
    assert radio.max_inflight == 1
    assert radio.events.count("connect") == 3
    assert radio.events.count("close_stale") == 3
    assert radio.sessions == 0


def test_cache_clear_failure_keeps_the_typed_error(radio: Radio) -> None:
    radio.values = {**VALUES, const.NAME_UUID: b"\x00"}
    radio.clear_cache_error = RuntimeError("link lost")

    with pytest.raises(WittyOneUpdateError) as excinfo:
        asyncio.run(WittyOneDeviceData(logging.getLogger()).update_device(DEVICE))

    assert excinfo.value.phase == UpdatePhase.READ_UNPROTECTED
    assert "clear_cache" in radio.events
    assert "pair" not in radio.events
    assert radio.events[-1] == "disconnect"


def test_session_buffer_is_not_dumped_in_errors(radio: Radio) -> None:
    radio.values = {**VALUES, const.SESSION_STATE_UUID: b"\x20\x00\xab\xcd"}

    with pytest.raises(WittyOneUpdateError) as excinfo:
        asyncio.run(WittyOneDeviceData(logging.getLogger()).update_device(DEVICE))

    assert excinfo.value.phase == UpdatePhase.DECODE
    assert "abcd" not in str(excinfo.value)
