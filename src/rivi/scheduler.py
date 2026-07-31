from __future__ import annotations

import logging
from typing import Callable

from rivi.config import Settings, get_settings
from rivi.db import session_scope
from rivi.weekly import run_weekly

logger = logging.getLogger("rivi.scheduler")


def parse_cron(expr: str) -> dict:
    """Parse a 5-field cron into APScheduler kwargs: minute hour day month day_of_week."""
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"WEEKLY_CRON must have 5 fields, got: {expr!r}")
    minute, hour, day, month, day_of_week = parts
    return {
        "minute": minute,
        "hour": hour,
        "day": day,
        "month": month,
        "day_of_week": day_of_week,
    }


def scheduled_weekly_job(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    logger.info("APScheduler fired weekly job")
    try:
        with session_scope(settings) as session:
            run_weekly(session, settings=settings, trigger="scheduler")
    except Exception:  # noqa: BLE001
        logger.exception("Scheduled weekly run failed")


def start_scheduler(
    settings: Settings | None = None,
    *,
    job_func: Callable[[], None] | None = None,
):
    """Start a BackgroundScheduler with the configured weekly cron. Returns the scheduler."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as e:
        raise RuntimeError(
            "APScheduler is required for scheduling. pip install apscheduler"
        ) from e

    settings = settings or get_settings()
    cron_kwargs = parse_cron(settings.weekly_cron)
    trigger = CronTrigger(timezone=settings.weekly_timezone, **cron_kwargs)

    scheduler = BackgroundScheduler(timezone=settings.weekly_timezone)
    func = job_func or (lambda: scheduled_weekly_job(settings))
    scheduler.add_job(func, trigger=trigger, id="rivi_weekly", replace_existing=True)
    scheduler.start()
    logger.info(
        "Scheduler started: cron=%s tz=%s",
        settings.weekly_cron,
        settings.weekly_timezone,
    )
    return scheduler
