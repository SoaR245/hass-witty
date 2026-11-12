"""Connection health tracking for Witty One device."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta
from enum import StrEnum


class UpdatePhase(StrEnum):
    """Step of a BLE exchange, used to locate a failure."""

    DISCOVERY = "discovery"
    CONNECT = "connect"
    READ_UNPROTECTED = "read_unprotected"
    PAIR = "pair"
    READ_PROTECTED = "read_protected"
    DECODE = "decode"
    WRITE = "write"


# Delay before the next encryption request after consecutive pairing failures.
# The Witty only accepts a new pairing in its badge pairing window; retrying
# every poll only floods it with SMP requests.
PAIRING_BACKOFF: tuple[timedelta, ...] = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(minutes=30),
)
PAIRING_ISSUE_THRESHOLD = 2


@dataclasses.dataclass
class ConnectionHealth:
    """Freshness and failure state of the BLE link."""

    last_success: datetime | None = None
    consecutive_errors: int = 0
    last_error: str | None = None
    last_error_phase: UpdatePhase | None = None
    pairing_failures: int = 0
    next_pairing_attempt: datetime | None = None

    @property
    def stale(self) -> bool:
        """Return True when the last poll did not read all values."""
        return self.consecutive_errors > 0

    @property
    def pairing_issue(self) -> bool:
        """Return True when the user should put the station in pairing mode."""
        return self.pairing_failures >= PAIRING_ISSUE_THRESHOLD

    def pairing_allowed(self, now: datetime) -> bool:
        """Return True when an encryption request may be sent."""
        return self.next_pairing_attempt is None or now >= self.next_pairing_attempt

    def record_success(self, now: datetime) -> None:
        """Record a poll where every value was read."""
        self.last_success = now
        self.consecutive_errors = 0
        self.last_error = None
        self.last_error_phase = None
        self.record_pairing_success()

    def record_failure(self, now: datetime, phase: UpdatePhase, message: str) -> None:
        """Record a poll that did not read every value."""
        self.consecutive_errors += 1
        self.last_error = message
        self.last_error_phase = phase
        if phase == UpdatePhase.PAIR:
            self.record_pairing_failure(now)
        elif phase in (UpdatePhase.READ_PROTECTED, UpdatePhase.DECODE):
            # Both phases only happen after a successful encryption request.
            self.record_pairing_success()

    def record_deferred(self) -> None:
        """Record a poll where encryption was skipped because of the backoff."""
        self.consecutive_errors += 1

    def record_pairing_failure(self, now: datetime) -> None:
        """Schedule the next encryption request."""
        self.pairing_failures += 1
        delay = PAIRING_BACKOFF[min(self.pairing_failures, len(PAIRING_BACKOFF)) - 1]
        self.next_pairing_attempt = now + delay

    def record_pairing_success(self) -> None:
        """Clear the pairing backoff."""
        self.pairing_failures = 0
        self.next_pairing_attempt = None
