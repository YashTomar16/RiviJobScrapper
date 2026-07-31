from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from rivi.aggregates import build_aggregates, compact_context_pack, latest_scrape_run_for_week
from rivi.config import Settings, get_settings
from rivi.insights.groq_client import GroqError, call_groq
from rivi.insights.schema import PROMPT_VERSION, GroqInsightsResponse
from rivi.models import WeeklyInsight, utcnow
from rivi.week import current_week_id

logger = logging.getLogger("rivi.insights")


def _upsert_insight(
    session: Session,
    *,
    week_id: str,
    scrape_run_id: int | None,
    summary: dict[str, Any],
    llm_status: str,
    brief: str = "",
    priorities: list | dict | None = None,
    groq_model: str = "",
    prompt_version: str = "",
    raw_ref: str = "",
) -> WeeklyInsight:
    row = session.scalar(
        select(WeeklyInsight)
        .where(WeeklyInsight.week_id == week_id)
        .order_by(WeeklyInsight.id.desc())
        .limit(1)
    )
    payload_priorities = priorities if priorities is not None else []
    if row is None:
        row = WeeklyInsight(week_id=week_id)
        session.add(row)

    row.scrape_run_id = scrape_run_id
    row.summary_json = json.dumps(summary)
    row.llm_status = llm_status
    row.llm_brief = brief
    row.llm_priorities_json = json.dumps(payload_priorities)
    row.groq_model = groq_model
    row.groq_prompt_version = prompt_version
    row.llm_raw_response_ref = raw_ref
    row.generated_at = utcnow()
    session.flush()
    return row


def persist_structured_only(
    session: Session,
    aggregates: dict[str, Any],
    *,
    llm_status: str = "skipped",
    error: str = "",
) -> WeeklyInsight:
    summary = {
        "structured": aggregates,
        "llm_error": error,
    }
    return _upsert_insight(
        session,
        week_id=aggregates["summary"]["week_id"],
        scrape_run_id=aggregates["summary"]["scrape_run_id"],
        summary=summary,
        llm_status=llm_status,
        brief="",
        priorities=[],
        prompt_version=PROMPT_VERSION,
    )


def generate_insights(
    session: Session,
    *,
    week_id: str | None = None,
    scrape_run_id: int | None = None,
    settings: Settings | None = None,
    call_llm: bool = True,
) -> dict[str, Any]:
    """Build aggregates and optionally call Groq. Upserts WeeklyInsight."""
    settings = settings or get_settings()
    week_id = week_id or current_week_id(settings.weekly_timezone)

    aggregates = build_aggregates(
        session, scrape_run_id=scrape_run_id, week_id=week_id if scrape_run_id is None else None
    )
    pack = compact_context_pack(aggregates)

    run_status = aggregates["summary"]["run_status"]
    companies_ok = aggregates["summary"]["companies_ok"]

    # S6: all failed — skip Groq or only risk notes
    if call_llm and (run_status == "failed" or companies_ok == 0):
        insight = persist_structured_only(
            session,
            aggregates,
            llm_status="skipped",
            error="No successful company scrapes; skipped Groq",
        )
        session.commit()
        return {
            "week_id": week_id,
            "insight_id": insight.id,
            "llm_status": insight.llm_status,
            "aggregates": aggregates,
        }

    if not call_llm:
        insight = persist_structured_only(session, aggregates, llm_status="skipped")
        session.commit()
        return {
            "week_id": week_id,
            "insight_id": insight.id,
            "llm_status": insight.llm_status,
            "aggregates": aggregates,
        }

    try:
        grounded, meta = call_groq(pack, settings)
        raw_path = _write_raw_response(settings, week_id, meta["raw_response"])
        priorities_payload = {
            "priority_companies": [p.model_dump() for p in grounded.priority_companies],
            "role_callouts": [c.model_dump() for c in grounded.role_callouts],
            "outreach_angles": [a.model_dump() for a in grounded.outreach_angles],
            "risk_notes": grounded.risk_notes,
        }
        insight = _upsert_insight(
            session,
            week_id=aggregates["summary"]["week_id"],
            scrape_run_id=aggregates["summary"]["scrape_run_id"],
            summary={"structured": aggregates, "context_pack": pack},
            llm_status="success",
            brief=grounded.executive_brief,
            priorities=priorities_payload,
            groq_model=meta["model"],
            prompt_version=meta["prompt_version"],
            raw_ref=str(raw_path),
        )
        session.commit()
        return {
            "week_id": week_id,
            "insight_id": insight.id,
            "llm_status": "success",
            "aggregates": aggregates,
            "groq": grounded.model_dump(),
        }
    except GroqError as e:
        logger.warning("Groq failed; publishing structured insights only: %s", e)
        insight = persist_structured_only(
            session, aggregates, llm_status="failed", error=str(e)
        )
        session.commit()
        return {
            "week_id": week_id,
            "insight_id": insight.id,
            "llm_status": "failed",
            "error": str(e),
            "aggregates": aggregates,
        }


def regenerate_llm_only(
    session: Session,
    week_id: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Re-call Groq for an existing week without re-scraping (G11)."""
    settings = settings or get_settings()
    run = latest_scrape_run_for_week(session, week_id)
    if run is None:
        raise LookupError(f"No scrape run for week {week_id}")

    existing = session.scalar(
        select(WeeklyInsight)
        .where(WeeklyInsight.week_id == week_id)
        .order_by(WeeklyInsight.id.desc())
        .limit(1)
    )
    # Always rebuild aggregates so thin-delta weeks still include open inventory
    aggregates = build_aggregates(session, scrape_run_id=run.id)
    pack = compact_context_pack(aggregates)

    try:
        grounded, meta = call_groq(pack, settings)
        raw_path = _write_raw_response(settings, week_id, meta["raw_response"])
        priorities_payload = {
            "priority_companies": [p.model_dump() for p in grounded.priority_companies],
            "role_callouts": [c.model_dump() for c in grounded.role_callouts],
            "outreach_angles": [a.model_dump() for a in grounded.outreach_angles],
            "risk_notes": grounded.risk_notes,
        }
        insight = _upsert_insight(
            session,
            week_id=week_id,
            scrape_run_id=run.id,
            summary={"structured": aggregates, "context_pack": pack},
            llm_status="success",
            brief=grounded.executive_brief,
            priorities=priorities_payload,
            groq_model=meta["model"],
            prompt_version=meta["prompt_version"],
            raw_ref=str(raw_path),
        )
        session.commit()
        return {
            "week_id": week_id,
            "insight_id": insight.id,
            "llm_status": "success",
            "groq": grounded.model_dump(),
        }
    except GroqError as e:
        insight = _upsert_insight(
            session,
            week_id=week_id,
            scrape_run_id=run.id,
            summary={"structured": aggregates, "context_pack": pack, "llm_error": str(e)},
            llm_status="failed",
            brief=(existing.llm_brief if existing else ""),
            priorities=json.loads(existing.llm_priorities_json)
            if existing and existing.llm_priorities_json
            else [],
            groq_model=settings.groq_model,
            prompt_version=PROMPT_VERSION,
        )
        session.commit()
        return {
            "week_id": week_id,
            "insight_id": insight.id,
            "llm_status": "failed",
            "error": str(e),
        }


def get_insight_payload(session: Session, week_id: str | None = None) -> dict[str, Any] | None:
    """Load persisted insight for API/UI."""
    q = select(WeeklyInsight).order_by(WeeklyInsight.generated_at.desc())
    if week_id:
        q = q.where(WeeklyInsight.week_id == week_id)
    row = session.scalar(q.limit(1))
    if row is None:
        return None
    summary = json.loads(row.summary_json or "{}")
    priorities = json.loads(row.llm_priorities_json or "[]")
    if isinstance(priorities, list):
        priorities = {"priority_companies": priorities}
    return {
        "id": row.id,
        "week_id": row.week_id,
        "scrape_run_id": row.scrape_run_id,
        "llm_status": row.llm_status,
        "llm_brief": row.llm_brief,
        "llm_priorities": priorities,
        "groq_model": row.groq_model,
        "groq_prompt_version": row.groq_prompt_version,
        "generated_at": row.generated_at.isoformat() if row.generated_at else "",
        "structured": summary.get("structured") or summary,
    }


def list_week_ids(session: Session) -> list[str]:
    rows = session.scalars(
        select(WeeklyInsight.week_id).order_by(WeeklyInsight.week_id.desc())
    ).all()
    # unique preserve order
    seen: set[str] = set()
    out: list[str] = []
    for w in rows:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _write_raw_response(settings: Settings, week_id: str, raw: str) -> Path:
    path = settings.reports_dir / f"groq_{week_id.replace('-', '_')}.json"
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(raw, encoding="utf-8")
    return path


# Re-export for tests
__all__ = [
    "generate_insights",
    "regenerate_llm_only",
    "get_insight_payload",
    "list_week_ids",
    "persist_structured_only",
    "GroqInsightsResponse",
]
