"""Framework-free transaction helper shared by the REST API and the NiceGUI pages."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.core.exceptions import CivicLensError


def run_in_uow(container: Any, fn: Callable[[Any], Any], *, commit_on_error: bool = False) -> Any:
    """Run ``fn(uow)`` in one transaction. ``commit_on_error`` persists audit/throttle rows written before a
    domain error (used by login and other security paths), then re-raises."""
    with container.uow_factory() as uow:
        try:
            result = fn(uow)
        except CivicLensError:
            if commit_on_error:
                uow.commit()
            raise
        uow.commit()
        return result
