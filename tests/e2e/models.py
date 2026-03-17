"""Shared data models for the Peregrine E2E test harness."""
from __future__ import annotations
import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any


@dataclass(frozen=True)
class ErrorRecord:
    type: str       # "exception" | "alert"
    message: str
    element_html: str

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ErrorRecord):
            return NotImplemented
        return (self.type, self.message) == (other.type, other.message)

    def __hash__(self) -> int:
        return hash((self.type, self.message))


def diff_errors(before: list[ErrorRecord], after: list[ErrorRecord]) -> list[ErrorRecord]:
    """Return errors in `after` that were not present in `before`."""
    before_set = set(before)
    return [e for e in after if e not in before_set]


@dataclass
class ModeConfig:
    name: str
    base_url: str
    auth_setup: Callable[[Any], None]
    expected_failures: list[str]        # fnmatch glob patterns against element labels
    results_dir: Path | None
    settings_tabs: list[str]            # tabs expected per mode

    def matches_expected_failure(self, label: str) -> bool:
        """Return True if label matches any expected_failure pattern (fnmatch)."""
        return any(fnmatch.fnmatch(label, pattern) for pattern in self.expected_failures)
