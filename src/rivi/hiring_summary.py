from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from rivi.classifier import SENIORITY_ORDER

# Lower index = more senior
_SENIORITY_RANK = {band: i for i, band in enumerate(SENIORITY_ORDER)}
_DEFAULT_RANK = len(SENIORITY_ORDER)


def _band(job: dict[str, Any]) -> str:
    return (job.get("seniority_band") or job.get("seniority") or "").strip() or "IC"


def _title(job: dict[str, Any]) -> str:
    return (job.get("title") or "").strip()


def seniority_rank(band: str) -> int:
    return _SENIORITY_RANK.get(band, _DEFAULT_RANK)


def top_senior_titles(jobs: list[dict[str, Any]], *, limit: int = 2) -> list[str]:
    """Return up to ``limit`` distinct job titles, most senior first.

    Prefers non-IC roles. Falls back to IC titles only when no non-IC roles exist.
    """
    non_ic = [j for j in jobs if _band(j) != "IC" and _title(j)]
    pool = non_ic or [j for j in jobs if _title(j)]
    # Sort by seniority (most senior first), then title for stability
    pool.sort(key=lambda j: (seniority_rank(_band(j)), _title(j).lower()))

    titles: list[str] = []
    seen: set[str] = set()
    for j in pool:
        t = _title(j)
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        titles.append(t)
        if len(titles) >= limit:
            break
    return titles


def format_hiring_summary(
    *,
    ic_count: int,
    non_ic_count: int,
    functions: list[str],
    top_titles: list[str] | None = None,
) -> str:
    """Human-readable hiring pulse for one company.

    Example:
    Hiring for Director of Product + VP Engineering + 5 non-IC and 30 IC roles
    across Engineering, AI, Product
    """
    if not ic_count and not non_ic_count:
        return "No in-scope open roles"

    headline_bits: list[str] = []
    for t in top_titles or []:
        if t:
            headline_bits.append(t)

    if non_ic_count and ic_count:
        counts = f"{non_ic_count} non-IC and {ic_count} IC roles"
    elif non_ic_count:
        counts = f"{non_ic_count} non-IC roles"
    else:
        counts = f"{ic_count} IC roles"

    if headline_bits:
        # Avoid repeating counts alone when titles already convey the lead roles
        lead = " + ".join(headline_bits)
        core = f"Hiring for {lead} + {counts}"
    else:
        core = f"Hiring for {counts}"

    if functions:
        return f"{core} across {', '.join(functions)}"
    return core


def company_hiring_summaries(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate open in-scope jobs into per-company hiring counts.

    Expects job dicts with at least ``company``, ``title``, ``seniority`` or
    ``seniority_band``, and ``function``.
    """
    by_company: dict[str, list[dict[str, Any]]] = defaultdict(list)
    categories: dict[str, str] = {}
    for j in jobs:
        company = (j.get("company") or "").strip()
        if not company:
            continue
        by_company[company].append(j)
        if company not in categories:
            categories[company] = (j.get("category") or "").strip()

    rows: list[dict[str, Any]] = []
    for company, roles in by_company.items():
        ic = 0
        non_ic = 0
        fn_counts: Counter[str] = Counter()
        for j in roles:
            band = _band(j)
            if band == "IC":
                ic += 1
            else:
                non_ic += 1
            fn = (j.get("function") or "").strip()
            if fn:
                fn_counts[fn] += 1

        functions = [f for f, _ in sorted(fn_counts.items(), key=lambda kv: (-kv[1], kv[0]))]
        titles = top_senior_titles(roles, limit=2)
        total = ic + non_ic
        rows.append(
            {
                "company": company,
                "category": categories.get(company, ""),
                "total": total,
                "ic_count": ic,
                "non_ic_count": non_ic,
                "top_titles": titles,
                "functions": functions,
                "functions_label": ", ".join(functions) if functions else "—",
                "hiring_summary": format_hiring_summary(
                    ic_count=ic,
                    non_ic_count=non_ic,
                    functions=functions,
                    top_titles=titles,
                ),
            }
        )

    rows.sort(key=lambda r: (-r["total"], -r["non_ic_count"], r["company"].lower()))
    return rows
