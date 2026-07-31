from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def current_week_id(timezone_name: str = "UTC") -> str:
    """ISO week id, e.g. 2026-W31."""
    now = datetime.now(ZoneInfo(timezone_name))
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"
