from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from rivi.config import Settings, get_settings
from rivi.ingest.runner import has_active_scrape_run, run_scrape
from rivi.insights.generate import generate_insights
from rivi.week import current_week_id

logger = logging.getLogger("rivi.weekly")


def run_weekly(
    session: Session,
    *,
    settings: Settings | None = None,
    limit: int | None = None,
    use_playwright: bool = False,
    skip_groq: bool = False,
    skip_alerts: bool = False,
    trigger: str = "manual",
) -> dict[str, Any]:
    """Full weekly pipeline: scrape → diff → aggregates → Groq → alerts."""
    settings = settings or get_settings()
    week_id = current_week_id(settings.weekly_timezone)

    active = has_active_scrape_run(session)
    if active is not None:
        raise RuntimeError(
            f"ScrapeRun #{active.id} is already running (week {active.week_id})"
        )

    logger.info("Starting weekly run for %s (trigger=%s)", week_id, trigger)

    scrape_summary = run_scrape(
        session,
        all_eligible=limit is None,
        limit=limit,
        use_playwright=use_playwright,
        settings=settings,
        trigger=trigger,
        week_id=week_id,
        compute_job_diffs=True,
        allow_overlap=False,
    )

    insight_result = generate_insights(
        session,
        week_id=week_id,
        scrape_run_id=scrape_summary["scrape_run_id"],
        settings=settings,
        call_llm=not skip_groq,
    )

    alert_result: dict[str, Any] = {"skipped": True, "reason": "disabled"}
    if settings.alerts_enabled and not skip_alerts:
        from rivi.alerts import dispatch_seniority_alerts

        alert_result = dispatch_seniority_alerts(
            session,
            week_id=week_id,
            scrape_run_id=scrape_summary["scrape_run_id"],
            settings=settings,
        )

    result = {
        "week_id": week_id,
        "scrape": {
            "scrape_run_id": scrape_summary["scrape_run_id"],
            "status": scrape_summary["status"],
            "companies_ok": scrape_summary.get("companies_ok", 0),
            "companies_failed": scrape_summary.get("companies_failed", 0),
            "new_roles": scrape_summary.get("new_roles", 0),
            "updated_roles": scrape_summary.get("updated_roles", 0),
            "removed_roles": scrape_summary.get("removed_roles", 0),
            "roles_in_scope": scrape_summary.get("roles_in_scope", 0),
        },
        "insights": {
            "insight_id": insight_result.get("insight_id"),
            "llm_status": insight_result.get("llm_status"),
            "error": insight_result.get("error"),
        },
        "alerts": alert_result,
    }
    logger.info("Weekly run complete: %s", json.dumps(result))
    return result
