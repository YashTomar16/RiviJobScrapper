from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from rivi.config import Settings, get_settings
from rivi.insights.groq_client import GroqError, call_groq
from rivi.models import Company, JobPosting

logger = logging.getLogger("rivi.deep_dive")


def build_company_pack(session: Session, company_name: str) -> dict[str, Any]:
    company = session.scalar(select(Company).where(Company.name == company_name))
    if company is None:
        # case-insensitive contains
        company = session.scalar(
            select(Company).where(Company.name.ilike(f"%{company_name}%")).limit(1)
        )
    if company is None:
        raise LookupError(f"Company not found: {company_name}")

    jobs = list(
        session.scalars(
            select(JobPosting)
            .where(
                JobPosting.company_id == company.id,
                JobPosting.in_scope.is_(True),
            )
            .order_by(JobPosting.status, JobPosting.seniority_band, JobPosting.title)
        )
    )
    open_jobs = [
        {
            "company": company.name,
            "title": j.title,
            "location": j.location,
            "function": j.function,
            "seniority_band": j.seniority_band,
            "job_url": j.job_url,
            "first_seen_week": j.first_seen_week,
            "last_seen_week": j.last_seen_week,
            "status": j.status,
        }
        for j in jobs
        if j.status == "open"
    ]
    removed = [
        {
            "company": company.name,
            "title": j.title,
            "seniority_band": j.seniority_band,
            "last_seen_week": j.last_seen_week,
            "status": "removed",
        }
        for j in jobs
        if j.status == "removed"
    ]
    return {
        "summary": {
            "week_id": "company-deep-dive",
            "company": company.name,
            "category": company.category,
            "career_page": company.career_page,
            "open_in_scope": len(open_jobs),
            "removed_in_scope": len(removed),
            "companies_ok": 1,
            "run_status": "success",
            "new_count": len(open_jobs),
            "baseline_week": False,
        },
        "hottest_companies": [{"company": company.name, "new_roles": len(open_jobs)}],
        "new_openings": open_jobs,
        "leadership_pulse": [
            j
            for j in open_jobs
            if j["seniority_band"]
            in {"Head", "Director", "Senior Director", "VP", "SVP", "C-level"}
        ],
        "removals": removed,
        "function_mix": {},
        "seniority_mix": {},
        "coverage_gaps": {"scrape_failures": [], "missing_career_page_total": 0, "eligible": 1},
    }


def company_deep_dive(
    session: Session,
    company_name: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """On-demand Groq deep-dive for one company using stored in-scope jobs."""
    settings = settings or get_settings()
    pack = build_company_pack(session, company_name)
    company = pack["summary"]["company"]

    # Reuse Groq client with a tighter user framing via pack truncation_note
    pack["truncation_note"] = (
        f"Company deep-dive for {company}. Focus outreach angles and leadership signal "
        "only for this company. Cite only titles/URLs in the pack."
    )

    try:
        grounded, meta = call_groq(pack, settings)
    except GroqError as e:
        logger.warning("Deep-dive Groq failed for %s: %s", company, e)
        return {
            "company": company,
            "llm_status": "failed",
            "error": str(e),
            "pack": pack,
            "groq": None,
        }

    raw_path = settings.reports_dir / f"deep_dive_{company.replace(' ', '_')[:40]}.json"
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(
        json.dumps(
            {
                "company": company,
                "groq": grounded.model_dump(),
                "raw": meta.get("raw_response", ""),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "company": company,
        "llm_status": "success",
        "pack_summary": pack["summary"],
        "groq": grounded.model_dump(),
        "raw_ref": str(raw_path),
    }
