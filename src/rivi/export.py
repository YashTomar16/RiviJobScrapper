from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from rivi.aggregates import build_aggregates, latest_scrape_run_for_week
from rivi.config import Settings, get_settings
from rivi.insights.generate import get_insight_payload


def build_week_pack(
    session: Session,
    week_id: str,
    *,
    scrape_run_id: int | None = None,
) -> dict[str, Any]:
    """CRM/BD-ready week pack: summary + jobs + optional LLM brief."""
    if scrape_run_id is None:
        run = latest_scrape_run_for_week(session, week_id)
        if run is None:
            raise LookupError(f"No scrape run for week {week_id}")
        scrape_run_id = run.id

    aggregates = build_aggregates(session, scrape_run_id=scrape_run_id)
    insight = get_insight_payload(session, week_id)

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "week_id": week_id,
        "scrape_run_id": scrape_run_id,
        "summary": aggregates.get("summary", {}),
        "new_openings": aggregates.get("new_openings", []),
        "leadership_pulse": aggregates.get("leadership_pulse", []),
        "hottest_companies": aggregates.get("hottest_companies", []),
        "function_mix": aggregates.get("function_mix", {}),
        "seniority_mix": aggregates.get("seniority_mix", {}),
        "removals": aggregates.get("removals", []),
        "coverage_gaps": aggregates.get("coverage_gaps", {}),
        "llm": {
            "status": (insight or {}).get("llm_status", ""),
            "brief": (insight or {}).get("llm_brief", ""),
            "priorities": (insight or {}).get("llm_priorities", {}),
        }
        if insight
        else None,
    }


def export_week_pack(
    session: Session,
    week_id: str,
    out_dir: Path | None = None,
    *,
    settings: Settings | None = None,
) -> tuple[Path, Path]:
    """Write week pack JSON + flattened jobs CSV. Returns (json_path, csv_path)."""
    settings = settings or get_settings()
    out_dir = out_dir or settings.reports_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    pack = build_week_pack(session, week_id)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = out_dir / f"week_pack_{week_id.replace('-', '_')}_{stamp}"
    json_path = Path(str(base) + ".json")
    csv_path = Path(str(base) + ".csv")

    json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

    rows: list[dict[str, Any]] = []
    for section, change in (
        ("new_openings", "new"),
        ("leadership_pulse", "leadership"),
        ("removals", "removed"),
    ):
        for j in pack.get(section) or []:
            rows.append(
                {
                    "week_id": week_id,
                    "section": section,
                    "change_type": j.get("change_type") or change,
                    "company": j.get("company", ""),
                    "title": j.get("title", ""),
                    "function": j.get("function", ""),
                    "seniority_band": j.get("seniority_band", ""),
                    "location": j.get("location", ""),
                    "job_url": j.get("job_url", ""),
                    "first_seen_week": j.get("first_seen_week", ""),
                }
            )

    fieldnames = [
        "week_id",
        "section",
        "change_type",
        "company",
        "title",
        "function",
        "seniority_band",
        "location",
        "job_url",
        "first_seen_week",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return json_path, csv_path
