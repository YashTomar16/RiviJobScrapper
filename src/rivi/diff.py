from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from rivi.ingest.engine import canonicalize_url
from rivi.models import CompanyRun, JobDelta, JobPosting, JobSnapshot, ScrapeRun, utcnow

logger = logging.getLogger("rivi.diff")

LEADERSHIP_BANDS = frozenset(
    {"Head", "Director", "Senior Director", "VP", "SVP", "C-level"}
)


@dataclass
class DiffStats:
    new: int = 0
    updated: int = 0
    removed: int = 0
    unchanged: int = 0

    def as_dict(self) -> dict:
        return {
            "new_roles": self.new,
            "updated_roles": self.updated,
            "removed_roles": self.removed,
            "unchanged_roles": self.unchanged,
        }


def metadata_changed(existing: JobPosting, title: str, location: str, job_url: str) -> bool:
    if title and title.strip() != (existing.title or "").strip():
        return True
    if location is not None and location.strip() != (existing.location or "").strip():
        return True
    if job_url and canonicalize_url(job_url) != canonicalize_url(existing.job_url or ""):
        return True
    return False


def compute_diffs(
    session: Session,
    scrape_run_id: int,
    marks: dict[int, str] | None = None,
) -> DiffStats:
    """Write JobDelta rows for a scrape run.

    ``marks`` maps job_posting_id → change_type from upsert
    (``new`` | ``updated`` | ``unchanged`` | ``reopened``).

    Removals are only inferred for companies with a successful CompanyRun
    (never on soft-fail). Idempotent for the same scrape_run_id.
    """
    run = session.get(ScrapeRun, scrape_run_id)
    if run is None:
        raise LookupError(f"ScrapeRun not found: {scrape_run_id}")

    session.execute(delete(JobDelta).where(JobDelta.scrape_run_id == scrape_run_id))
    session.flush()

    marks = marks or {}
    stats = DiffStats()

    for job_id, change in marks.items():
        normalized = "new" if change == "reopened" else change
        if normalized == "unchanged":
            stats.unchanged += 1
            continue
        if normalized == "new":
            stats.new += 1
        elif normalized == "updated":
            stats.updated += 1
        else:
            continue
        session.add(
            JobDelta(
                scrape_run_id=scrape_run_id,
                job_posting_id=job_id,
                change_type=normalized,
                created_at=utcnow(),
            )
        )

    company_runs = list(
        session.scalars(
            select(CompanyRun).where(
                CompanyRun.scrape_run_id == scrape_run_id,
                CompanyRun.status == "success",
            )
        )
    )
    for cr in company_runs:
        seen_ids = set(
            session.scalars(
                select(JobSnapshot.job_posting_id)
                .join(JobPosting, JobPosting.id == JobSnapshot.job_posting_id)
                .where(
                    JobSnapshot.scrape_run_id == scrape_run_id,
                    JobPosting.company_id == cr.company_id,
                )
            ).all()
        )
        open_jobs = list(
            session.scalars(
                select(JobPosting).where(
                    JobPosting.company_id == cr.company_id,
                    JobPosting.status == "open",
                )
            )
        )
        for job in open_jobs:
            if job.id in seen_ids:
                continue
            job.status = "removed"
            job.updated_at = utcnow()
            session.add(
                JobDelta(
                    scrape_run_id=scrape_run_id,
                    job_posting_id=job.id,
                    change_type="removed",
                    created_at=utcnow(),
                )
            )
            stats.removed += 1

    session.flush()
    logger.info(
        "Diffs for run %s: new=%s updated=%s removed=%s unchanged=%s",
        scrape_run_id,
        stats.new,
        stats.updated,
        stats.removed,
        stats.unchanged,
    )
    return stats
