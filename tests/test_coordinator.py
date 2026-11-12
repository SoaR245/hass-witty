"""Tests for the poll policy of the Witty One coordinator."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.witty_one import coordinator as coordinator_module
from custom_components.witty_one.witty_one.health import UpdatePhase
from custom_components.witty_one.witty_one.parser import (
    WittyOneDevice,
    WittyOneGeneralState,
    WittyOnePhaseEnergy,
    WittyOneStaticProperties,
    WittyOneUpdateError,
)

STATIC = WittyOneStaticProperties(name="Witty-test", model="XVR111STI")


def _device(mainstate: int, energy: float = 0.0) -> WittyOneDevice:
    return WittyOneDevice(
        static_information=STATIC,
        general=WittyOneGeneralState(mainstate=mainstate),
        energies=[WittyOnePhaseEnergy(active_import_energy=energy)] * 4,
    )


def _pair_error(partial: WittyOneDevice | None = None) -> WittyOneUpdateError:
    return WittyOneUpdateError(UpdatePhase.PAIR, TimeoutError(), partial)


class FakeWitty:
    """Scripted BLE session recording which operation the coordinator used."""

    last_connection_path = None

    def __init__(self) -> None:
        self.results: list[Any] = []
        self.calls: list[str] = []

    async def _next(self, name: str) -> Any:
        self.calls.append(name)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def update_device(self, *_args: Any) -> WittyOneDevice:
        return await self._next("update_device")

    async def read_unprotected(self, *_args: Any) -> WittyOneDevice:
        return await self._next("read_unprotected")

    async def write_charge_mode(self, *_args: Any) -> None:
        return await self._next("write_charge_mode")


class Env:
    """Coordinator wired to fake Home Assistant services."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)
        self.issues: set[str] = set()
        entry = SimpleNamespace(
            unique_id="34:CD:B0:00:00:01",
            entry_id="entry",
            title="Witty",
            pref_disable_polling=True,
            async_on_unload=lambda _cb: None,
        )
        monkeypatch.setattr(
            coordinator_module,
            "bluetooth",
            SimpleNamespace(
                async_ble_device_from_address=lambda *_a, **_k: SimpleNamespace(
                    address=entry.unique_id
                ),
                async_last_service_info=lambda *_a, **_k: None,
            ),
        )
        monkeypatch.setattr(
            coordinator_module,
            "ir",
            SimpleNamespace(
                IssueSeverity=SimpleNamespace(WARNING="warning"),
                async_create_issue=lambda _h, _d, issue_id, **_k: self.issues.add(
                    issue_id
                ),
                async_delete_issue=lambda _h, _d, issue_id: self.issues.discard(
                    issue_id
                ),
            ),
        )
        monkeypatch.setattr(
            coordinator_module, "dt_util", SimpleNamespace(utcnow=lambda: self.now)
        )
        self.coordinator = coordinator_module.WittyOneDataUpdateCoordinator(
            SimpleNamespace(), entry
        )
        self.witty = FakeWitty()
        self.coordinator.witty = self.witty
        self.refreshes = 0

        async def refresh() -> None:
            self.refreshes += 1

        self.coordinator.async_request_refresh = refresh

    def poll(self, *results: Any, minutes: int = 1) -> WittyOneDevice:
        self.witty.results.extend(results)
        self.now += timedelta(minutes=minutes)
        data = asyncio.run(self.coordinator._async_update_data())  # noqa: SLF001
        self.coordinator.data = data
        return data


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Env:
    logging.getLogger(coordinator_module.LOGGER.name).setLevel(logging.ERROR)
    return Env(monkeypatch)


def test_first_pairing_failure_serves_unprotected_values_only(env: Env) -> None:
    data = env.poll(_pair_error(_device(6)))

    assert data.general.mainstate == 6
    assert not env.coordinator.protected_data_available


def test_failed_polls_keep_previous_values_until_tolerance(env: Env) -> None:
    env.poll(_device(6, energy=42))
    for _ in range(3):
        error = WittyOneUpdateError(UpdatePhase.CONNECT, TimeoutError())
        assert env.poll(error).energies[0].active_import_energy == 42
        assert env.coordinator.protected_data_available

    with pytest.raises(UpdateFailed):
        env.poll(WittyOneUpdateError(UpdatePhase.CONNECT, TimeoutError()))
    assert not env.coordinator.protected_data_available


def test_backoff_reads_only_unprotected_values(env: Env) -> None:
    env.poll(_device(6, energy=42))
    env.poll(_pair_error(_device(2)))
    env.witty.calls.clear()

    data = env.poll(_device(3), minutes=0)

    assert env.witty.calls == ["read_unprotected"]
    assert data.general.mainstate == 3
    assert data.energies[0].active_import_energy == 42

    env.poll(_device(6, energy=43), minutes=1)
    assert env.witty.calls[-1] == "update_device"


def test_repair_issue_follows_pairing_failures(env: Env) -> None:
    issue = env.coordinator.pairing_issue_id
    env.poll(_pair_error(_device(6)))
    assert issue not in env.issues

    env.poll(_pair_error(_device(6)), minutes=1)
    assert issue in env.issues

    env.poll(_device(6), minutes=5)
    assert issue not in env.issues
    assert env.coordinator.protected_data_available


def test_charge_mode_pairing_failure_is_not_retried(env: Env) -> None:
    notified: list[bool] = []
    env.coordinator.async_add_listener(lambda: notified.append(True))
    env.witty.results.append(_pair_error())

    with pytest.raises(HomeAssistantError):
        asyncio.run(env.coordinator.async_set_charge_mode(2))

    assert env.witty.calls == ["write_charge_mode"]
    assert env.coordinator.health.next_pairing_attempt is not None
    assert notified
    assert env.refreshes == 0
