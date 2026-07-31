from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from rivi.config import Settings, get_settings


def setup_logging(settings: Settings | None = None) -> logging.Logger:
    """Configure root logging to stderr + logs/rivi.log."""
    settings = settings or get_settings()
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.runs_dir.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger = logging.getLogger("rivi")
    logger.setLevel(level)
    logger.handlers.clear()
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(level)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(settings.logs_dir / "rivi.log", encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


def new_run_log_path(command: str, settings: Settings | None = None) -> Path:
    """Return a timestamped path under logs/runs/ for structured run output."""
    settings = settings or get_settings()
    settings.runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in command)
    return settings.runs_dir / f"{stamp}_{safe}.json"
