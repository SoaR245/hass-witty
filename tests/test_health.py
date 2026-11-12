"""Tests for the connection health and pairing backoff."""

from datetime import UTC, datetime, timedelta

from witty_one.health import ConnectionHealth, UpdatePhase

NOW = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)


def test_pairing_backoff_grows_and_is_capped() -> None:
    health = ConnectionHealth()
    delays = []
    for _ in range(5):
        health.record_failure(NOW, UpdatePhase.PAIR, "timeout")
        assert health.next_pairing_attempt is not None
        delays.append(health.next_pairing_attempt - NOW)

    assert delays == [timedelta(minutes=m) for m in (1, 5, 15, 30, 30)]
    assert not health.pairing_allowed(NOW + timedelta(minutes=29))
    assert health.pairing_allowed(NOW + timedelta(minutes=30))


def test_pairing_issue_raised_after_repeated_failures_and_cleared_on_success() -> None:
    health = ConnectionHealth()
    health.record_failure(NOW, UpdatePhase.PAIR, "timeout")
    assert not health.pairing_issue
    health.record_failure(NOW, UpdatePhase.PAIR, "timeout")
    assert health.pairing_issue
    assert health.stale

    health.record_success(NOW)

    assert not health.pairing_issue
    assert not health.stale
    assert health.pairing_allowed(NOW)
    assert health.last_success == NOW


def test_failure_after_encryption_clears_backoff_but_stays_stale() -> None:
    health = ConnectionHealth()
    health.record_failure(NOW, UpdatePhase.PAIR, "timeout")
    health.record_failure(NOW, UpdatePhase.READ_PROTECTED, "read timeout")

    assert health.pairing_allowed(NOW)
    assert health.pairing_failures == 0
    assert health.consecutive_errors == 2
    assert health.last_error_phase == UpdatePhase.READ_PROTECTED


def test_other_failures_do_not_touch_pairing_backoff() -> None:
    health = ConnectionHealth()
    health.record_failure(NOW, UpdatePhase.PAIR, "timeout")
    deadline = health.next_pairing_attempt

    health.record_failure(NOW, UpdatePhase.CONNECT, "no slot")
    health.record_deferred()

    assert health.next_pairing_attempt == deadline
    assert health.consecutive_errors == 3
