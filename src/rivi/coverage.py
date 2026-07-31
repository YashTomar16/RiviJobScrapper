from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from rivi.models import Company


@dataclass
class CoverageReport:
    generated_at: str
    total: int
    eligible: int
    with_website: int
    with_career_page: int
    missing_website: int
    missing_career_page: int
    skipped: int
    by_category: dict[str, dict[str, int]]
    by_status: dict[str, int]
    unresolved: list[dict]
    eligible_companies: list[dict]


def _status_bucket(status: str) -> str:
    if not status:
        return "empty"
    if status.startswith("ok") or status.startswith("manual"):
        return status.split(":")[0] if ":" in status else status
    if status.startswith("fail:"):
        return status
    return status


def build_coverage_report(session: Session) -> CoverageReport:
    rows = list(session.scalars(select(Company).order_by(Company.category, Company.name)))
    by_category: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "eligible": 0, "missing_career": 0, "skipped": 0, "no_website": 0}
    )
    by_status: Counter[str] = Counter()
    unresolved: list[dict] = []
    eligible_companies: list[dict] = []

    with_website = 0
    with_career = 0
    skipped = 0

    for r in rows:
        cat = r.category or "unknown"
        by_category[cat]["total"] += 1
        by_status[_status_bucket(r.career_page_status)] += 1

        if r.website:
            with_website += 1
        else:
            by_category[cat]["no_website"] += 1

        if r.skip:
            skipped += 1
            by_category[cat]["skipped"] += 1

        if r.career_page:
            with_career += 1
        else:
            by_category[cat]["missing_career"] += 1
            unresolved.append(
                {
                    "company_name": r.name,
                    "category": r.category,
                    "website": r.website,
                    "career_page_status": r.career_page_status,
                    "skip": r.skip,
                    "skip_reason": r.skip_reason,
                }
            )

        if r.is_eligible:
            by_category[cat]["eligible"] += 1
            eligible_companies.append(
                {
                    "company_name": r.name,
                    "category": r.category,
                    "website": r.website,
                    "career_page": r.career_page,
                    "career_page_status": r.career_page_status,
                    "career_page_source": r.career_page_source,
                }
            )

    return CoverageReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        total=len(rows),
        eligible=len(eligible_companies),
        with_website=with_website,
        with_career_page=with_career,
        missing_website=len(rows) - with_website,
        missing_career_page=len(rows) - with_career,
        skipped=skipped,
        by_category={k: dict(v) for k, v in sorted(by_category.items())},
        by_status=dict(by_status.most_common()),
        unresolved=unresolved,
        eligible_companies=eligible_companies,
    )


def coverage_to_dict(report: CoverageReport) -> dict:
    return {
        "generated_at": report.generated_at,
        "total": report.total,
        "eligible": report.eligible,
        "with_website": report.with_website,
        "with_career_page": report.with_career_page,
        "missing_website": report.missing_website,
        "missing_career_page": report.missing_career_page,
        "skipped": report.skipped,
        "by_category": report.by_category,
        "by_status": report.by_status,
        "unresolved_count": len(report.unresolved),
        "unresolved": report.unresolved,
        "eligible_companies": report.eligible_companies,
    }


def write_coverage_json(report: CoverageReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(coverage_to_dict(report), indent=2), encoding="utf-8")


def write_coverage_markdown(report: CoverageReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "# Coverage health",
        "",
        f"Generated at: `{report.generated_at}`",
        "",
        "## Summary",
        "",
        f"| Metric | Count |",
        f"|--------|------:|",
        f"| Total companies | {report.total} |",
        f"| Eligible for ingest | {report.eligible} |",
        f"| With website | {report.with_website} |",
        f"| With career page | {report.with_career_page} |",
        f"| Missing website | {report.missing_website} |",
        f"| Missing career page | {report.missing_career_page} |",
        f"| Skipped | {report.skipped} |",
        "",
        "## By category",
        "",
        "| Category | Total | Eligible | Missing career | No website | Skipped |",
        "|----------|------:|---------:|---------------:|-----------:|--------:|",
    ]
    for cat, stats in report.by_category.items():
        lines.append(
            f"| {cat} | {stats['total']} | {stats['eligible']} | "
            f"{stats['missing_career']} | {stats['no_website']} | {stats['skipped']} |"
        )

    lines.extend(
        [
            "",
            "## Status breakdown",
            "",
            "| Status | Count |",
            "|--------|------:|",
        ]
    )
    for status, count in report.by_status.items():
        lines.append(f"| `{status}` | {count} |")

    lines.extend(
        [
            "",
            "## How to fix unresolved companies",
            "",
            "1. Find the public careers / jobs URL in a browser.",
            "2. Set a manual override:",
            "",
            "```bash",
            'rivi set-career-page --company "AllianceBernstein" --url "https://..."',
            "```",
            "",
            "3. Or mark the company skipped if it should not be ingested:",
            "",
            "```bash",
            'rivi skip-company --company "Some Co" --reason "No public careers board"',
            "```",
            "",
            "4. Re-run coverage:",
            "",
            "```bash",
            "rivi coverage-report",
            "```",
            "",
            "## Unresolved companies",
            "",
            "| Company | Category | Website | Status | Skip |",
            "|---------|----------|---------|--------|------|",
        ]
    )
    for u in report.unresolved:
        lines.append(
            f"| {u['company_name']} | {u['category']} | {u['website'] or '—'} | "
            f"`{u['career_page_status'] or 'empty'}` | {u['skip']} |"
        )

    lines.extend(
        [
            "",
            "## Eligible companies (ingest-ready)",
            "",
            f"Total: **{report.eligible}**",
            "",
            "| Company | Category | Career page | Source |",
            "|---------|----------|-------------|--------|",
        ]
    )
    for e in report.eligible_companies:
        lines.append(
            f"| {e['company_name']} | {e['category']} | {e['career_page']} | "
            f"{e['career_page_source'] or '—'} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
