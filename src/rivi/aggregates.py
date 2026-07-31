from __future__ import annotations

import json
from collections import Counter
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rivi.coverage import build_coverage_report
from rivi.diff import LEADERSHIP_BANDS
from rivi.models import Company, CompanyRun, JobDelta, JobPosting, ScrapeRun


def _job_row(job: JobPosting, company_name: str, change_type: str = "") -> dict[str, Any]:
    return {
        "job_id": job.id,
        "company": company_name,
        "company_id": job.company_id,
        "title": job.title,
        "location": job.location,
        "function": job.function,
        "seniority_band": job.seniority_band,
        "job_url": job.job_url,
        "first_seen_week": job.first_seen_week,
        "last_seen_week": job.last_seen_week,
        "change_type": change_type,
        "in_scope": job.in_scope,
    }


def latest_scrape_run_for_week(session: Session, week_id: str) -> ScrapeRun | None:
    """Prefer successful/partial runs; fall back to any finished run."""
    run = session.scalar(
        select(ScrapeRun)
        .where(ScrapeRun.week_id == week_id)
        .where(ScrapeRun.status.in_(("success", "partial")))
        .order_by(ScrapeRun.id.desc())
        .limit(1)
    )
    if run is not None:
        return run
    return session.scalar(
        select(ScrapeRun)
        .where(ScrapeRun.week_id == week_id)
        .where(ScrapeRun.status != "running")
        .order_by(ScrapeRun.id.desc())
        .limit(1)
    )


def build_aggregates(
    session: Session,
    *,
    scrape_run_id: int | None = None,
    week_id: str | None = None,
) -> dict[str, Any]:
    """Build structured Key Insights aggregates for a scrape run / week."""
    run: ScrapeRun | None = None
    if scrape_run_id is not None:
        run = session.get(ScrapeRun, scrape_run_id)
    elif week_id:
        run = latest_scrape_run_for_week(session, week_id)
    if run is None:
        raise LookupError("No scrape run found for aggregates")

    week_id = run.week_id
    run_stats = json.loads(run.stats_json or "{}")
    company_names = {c.id: c.name for c in session.scalars(select(Company)).all()}

    deltas = list(
        session.scalars(select(JobDelta).where(JobDelta.scrape_run_id == run.id))
    )
    delta_by_job: dict[int, str] = {d.job_posting_id: d.change_type for d in deltas}

    job_ids = list(delta_by_job.keys())
    jobs: dict[int, JobPosting] = {}
    if job_ids:
        jobs = {
            j.id: j
            for j in session.scalars(select(JobPosting).where(JobPosting.id.in_(job_ids)))
        }

    new_openings: list[dict] = []
    updated_openings: list[dict] = []
    removals: list[dict] = []
    leadership: list[dict] = []

    for job_id, change in delta_by_job.items():
        job = jobs.get(job_id)
        if job is None or not job.in_scope:
            continue
        name = company_names.get(job.company_id, "")
        row = _job_row(job, name, change)
        if change == "new":
            new_openings.append(row)
            if job.seniority_band in LEADERSHIP_BANDS:
                leadership.append(row)
        elif change == "updated":
            updated_openings.append(row)
            if job.seniority_band in LEADERSHIP_BANDS:
                leadership.append(row)
        elif change == "removed":
            removals.append(row)

    new_openings.sort(key=lambda r: (r["company"], r["title"]))
    updated_openings.sort(key=lambda r: (r["company"], r["title"]))
    removals.sort(key=lambda r: (r["company"], r["title"]))
    leadership.sort(
        key=lambda r: (
            0 if r["seniority_band"] == "C-level" else 1,
            r["company"],
            r["title"],
        )
    )

    company_new_counts: Counter[str] = Counter()
    for row in new_openings:
        company_new_counts[row["company"]] += 1
    hottest = [
        {"company": name, "new_roles": count}
        for name, count in sorted(
            company_new_counts.items(), key=lambda x: (-x[1], x[0])
        )[:15]
    ]

    function_mix = dict(Counter(r["function"] for r in new_openings if r["function"]))
    seniority_mix = dict(
        Counter(r["seniority_band"] for r in new_openings if r["seniority_band"])
    )

    # Coverage gaps: missing career pages + this run's failures
    coverage = build_coverage_report(session)
    failed_runs = list(
        session.scalars(
            select(CompanyRun).where(
                CompanyRun.scrape_run_id == run.id,
                CompanyRun.status == "failed",
            )
        )
    )
    scrape_failures = []
    for cr in failed_runs:
        scrape_failures.append(
            {
                "company": company_names.get(cr.company_id, ""),
                "error": cr.error,
                "http_status": cr.http_status,
            }
        )

    missing_career = [
        {"company": c["company_name"], "category": c["category"], "reason": c["career_page_status"]}
        for c in coverage.unresolved[:50]
    ]

    open_in_scope_count = (
        session.scalar(
            select(func.count())
            .select_from(JobPosting)
            .where(JobPosting.in_scope.is_(True), JobPosting.status == "open")
        )
        or 0
    )

    # Current open in-scope inventory (for LLM when weekly deltas are thin)
    open_jobs = list(
        session.scalars(
            select(JobPosting)
            .where(JobPosting.in_scope.is_(True), JobPosting.status == "open")
            .order_by(JobPosting.seniority_band, JobPosting.company_id, JobPosting.title)
            .limit(80)
        )
    )
    open_roles = [
        _job_row(j, company_names.get(j.company_id, ""), "open") for j in open_jobs
    ]
    open_leadership = [
        r for r in open_roles if r["seniority_band"] in LEADERSHIP_BANDS
    ]

    # If this week's deltas are empty, still surface open inventory for insights UI
    if not new_openings and open_roles:
        # Prefer leadership in "pulse" when no delta leadership
        if not leadership:
            leadership = open_leadership
        if not hottest:
            from collections import Counter as _C

            cnt = _C(r["company"] for r in open_roles)
            hottest = [
                {"company": name, "new_roles": count}
                for name, count in sorted(cnt.items(), key=lambda x: (-x[1], x[0]))[:15]
            ]
        if not function_mix:
            function_mix = dict(Counter(r["function"] for r in open_roles if r["function"]))
        if not seniority_mix:
            seniority_mix = dict(
                Counter(r["seniority_band"] for r in open_roles if r["seniority_band"])
            )

    summary = {
        "week_id": week_id,
        "scrape_run_id": run.id,
        "run_status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else "",
        "finished_at": run.finished_at.isoformat() if run.finished_at else "",
        "companies_targeted": run_stats.get("companies_targeted", 0),
        "companies_ok": run_stats.get("companies_ok", 0),
        "companies_failed": run_stats.get("companies_failed", 0),
        "roles_found": run_stats.get("roles_found", 0),
        "roles_in_scope": run_stats.get("roles_in_scope", 0),
        "open_in_scope_total": open_in_scope_count,
        "new_count": len(new_openings),
        "updated_count": len(updated_openings),
        "removed_count": len(removals),
        "leadership_count": len(leadership),
        "thin_delta_week": len(new_openings) == 0 and open_in_scope_count > 0,
        "baseline_week": len(new_openings) > 0
        and len(updated_openings) == 0
        and run_stats.get("unchanged_roles", 0) == 0,
    }

    return {
        "summary": summary,
        "new_openings": new_openings,
        "updated_openings": updated_openings,
        "leadership_pulse": leadership,
        "hottest_companies": hottest,
        "function_mix": function_mix,
        "seniority_mix": seniority_mix,
        "removals": removals,
        "open_roles": open_roles,
        "coverage_gaps": {
            "missing_career_pages": missing_career,
            "scrape_failures": scrape_failures,
            "eligible": coverage.eligible,
            "missing_career_page_total": coverage.missing_career_page,
            "skipped": coverage.skipped,
        },
    }


def _slim_job(row: dict[str, Any]) -> dict[str, Any]:
    """Drop heavy fields from job rows before sending to Groq."""
    return {
        "company": row.get("company", ""),
        "title": row.get("title", ""),
        "function": row.get("function", ""),
        "seniority_band": row.get("seniority_band", ""),
        "job_url": row.get("job_url", ""),
    }


def compact_context_pack(
    aggregates: dict[str, Any],
    *,
    max_new: int = 18,
    max_leadership: int = 12,
    max_removals: int = 8,
    max_hottest: int = 8,
    max_open: int = 12,
) -> dict[str, Any]:
    """Token-budget aware pack for Groq — leadership first, then new / open roles.

    Sized for Groq on_demand TPM (~12k including completion). Prefer leadership +
    hottest companies; avoid duplicating full open inventory when new_openings exist.
    """
    new_raw = aggregates["new_openings"][:max_new]
    open_raw = (aggregates.get("open_roles") or [])[:max_open]
    # If no weekly "new" signal, feed current open inventory so Groq still has substance
    if not new_raw and open_raw:
        new_raw = open_raw[:max_new]
        open_raw = []
    elif new_raw:
        # Avoid near-duplicate token cost when the week already has new openings
        open_raw = []

    new_openings = [_slim_job(r) for r in new_raw]
    open_roles = [_slim_job(r) for r in open_raw]
    leadership = [_slim_job(r) for r in aggregates["leadership_pulse"][:max_leadership]]
    removals = [_slim_job(r) for r in aggregates["removals"][:max_removals]]

    # Keep summary numeric only — drop bulky timestamps from the LLM pack
    summary = {
        k: v
        for k, v in (aggregates.get("summary") or {}).items()
        if k
        not in {
            "started_at",
            "finished_at",
        }
    }

    failures = aggregates["coverage_gaps"].get("scrape_failures") or []
    slim_failures = [
        {"company": f.get("company", ""), "reason": (f.get("reason") or "")[:80]}
        for f in failures[:8]
    ]

    return {
        "summary": summary,
        "hottest_companies": aggregates["hottest_companies"][:max_hottest],
        "function_mix": aggregates["function_mix"],
        "seniority_mix": aggregates["seniority_mix"],
        "leadership_pulse": leadership,
        "new_openings": new_openings,
        "open_roles": open_roles,
        "removals": removals,
        "coverage_gaps": {
            "scrape_failures": slim_failures,
            "missing_career_page_total": aggregates["coverage_gaps"][
                "missing_career_page_total"
            ],
            "eligible": aggregates["coverage_gaps"]["eligible"],
        },
        "truncation_note": (
            f"Pack truncated to {max_new} openings, {max_leadership} leadership, "
            f"{max_removals} removals for token budget. "
            "If summary.thin_delta_week is true, new_openings may reflect current open "
            "inventory rather than net-new this week — say so in risk_notes."
        ),
    }
