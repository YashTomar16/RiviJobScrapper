from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def format_hiring_summary(
    *,
    ic_count: int,
    non_ic_count: int,
    functions: list[str],
) -> str:
    """Human-readable hiring pulse for one company.

    Example: "Hiring for 5 non-IC and 30 IC roles across Engineering, AI, Product"
    """
    parts: list[str] = []
    if non_ic_count and ic_count:
        parts.append(f"Hiring for {non_ic_count} non-IC and {ic_count} IC roles")
    elif non_ic_count:
        parts.append(f"Hiring for {non_ic_count} non-IC roles")
    elif ic_count:
        parts.append(f"Hiring for {ic_count} IC roles")
    else:
        return "No in-scope open roles"

    if functions:
        parts.append(f"across {', '.join(functions)}")
    return " ".join(parts)


def company_hiring_summaries(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate open in-scope jobs into per-company hiring counts.

    Expects job dicts with at least ``company``, ``seniority`` or ``seniority_band``,
    and ``function``.
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
            band = (j.get("seniority_band") or j.get("seniority") or "").strip() or "IC"
            if band == "IC":
                ic += 1
            else:
                non_ic += 1
            fn = (j.get("function") or "").strip()
            if fn:
                fn_counts[fn] += 1

        # Prefer higher volume functions first, then alpha for ties
        functions = [f for f, _ in sorted(fn_counts.items(), key=lambda kv: (-kv[1], kv[0]))]
        total = ic + non_ic
        rows.append(
            {
                "company": company,
                "category": categories.get(company, ""),
                "total": total,
                "ic_count": ic,
                "non_ic_count": non_ic,
                "functions": functions,
                "functions_label": ", ".join(functions) if functions else "—",
                "hiring_summary": format_hiring_summary(
                    ic_count=ic,
                    non_ic_count=non_ic,
                    functions=functions,
                ),
            }
        )

    rows.sort(key=lambda r: (-r["total"], -r["non_ic_count"], r["company"].lower()))
    return rows
