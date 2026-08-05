from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from rivi.models import Company

logger = logging.getLogger("rivi.resolver")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Ordered by likelihood; keep short for speed.
CAREER_PATHS = [
    "/careers",
    "/jobs",
    "/career",
    "/en/careers",
    "/about/careers",
    "/about-us/careers",
    "/company/careers",
    "/join-us",
    "/work-with-us",
]

ATS_HOST_HINTS = (
    "myworkdayjobs.com",
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.ashbyhq.com",
    "ashbyhq.com",
    "jobs.smartrecruiters.com",
    "smartrecruiters.com",
    "icims.com",
    "jobvite.com",
    "apply.workable.com",
    "bamboohr.com",
    "successfactors.com",
    "taleo.net",
    "oraclecloud.com",
    "recruiting.adp.com",
    "eightfold.ai",
    "careers.bankofamerica.com",
)

CAREER_KEYWORDS = (
    "career",
    "job",
    "join-us",
    "joinus",
    "opportunity",
    "recruit",
    "talent",
    "work-with",
    "vacancies",
    "positions",
    "myworkdayjobs",
    "greenhouse",
    "lever.co",
    "ashbyhq",
    "smartrecruiters",
)


@dataclass
class ResolveResult:
    company_name: str
    career_page: str
    career_page_status: str
    changed: bool


def looks_like_career(url: str) -> bool:
    u = url.lower()
    return any(k in u for k in CAREER_KEYWORDS) or any(h in u for h in ATS_HOST_HINTS)


def _root_domain(host: str) -> str:
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def candidate_urls(website: str) -> list[str]:
    if not website:
        return []
    parsed = urlparse(website if "://" in website else f"https://{website}")
    if not parsed.netloc:
        return []
    base = f"{parsed.scheme or 'https'}://{parsed.netloc}"
    root = _root_domain(parsed.netloc)

    candidates: list[str] = [
        f"https://careers.{root}",
        f"https://jobs.{root}",
    ]
    for path in CAREER_PATHS:
        candidates.append(urljoin(base + "/", path.lstrip("/")))

    seen: set[str] = set()
    ordered: list[str] = []
    for u in candidates:
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    return ordered


def _extract_ats_links(html: str, base_url: str) -> list[str]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    found: list[str] = []
    for href in hrefs:
        full = urljoin(base_url, href).split("#")[0]
        low = full.lower()
        if any(h in low for h in ATS_HOST_HINTS):
            found.append(full)
        elif looks_like_career(full) and ("career" in low or "job" in low):
            found.append(full)

    found.sort(key=lambda u: (0 if any(h in u.lower() for h in ATS_HOST_HINTS) else 1, len(u)))
    dedup: list[str] = []
    seen: set[str] = set()
    for u in found:
        if u not in seen:
            seen.add(u)
            dedup.append(u)
    return dedup[:8]


def probe_url(client: httpx.Client, url: str, *, fetch_body: bool = False) -> tuple[str, int | str, bool, str]:
    try:
        resp = client.get(url, follow_redirects=True)
        status = resp.status_code
        final_url = str(resp.url)
        ok = 200 <= status < 400
        body = ""
        if ok and fetch_body:
            body = resp.text[:150_000]
        return final_url, status, ok, body
    except httpx.TimeoutException:
        return url, "TimeoutError", False, ""
    except httpx.InvalidURL:
        return url, "InvalidURL", False, ""
    except httpx.HTTPError as e:
        return url, type(e).__name__, False, ""
    except Exception as e:  # noqa: BLE001
        return url, type(e).__name__, False, ""


def resolve_website(client: httpx.Client, website: str) -> tuple[str, str]:
    if not website:
        return "", "no_website"

    best: tuple[str, int] | None = None
    last_status = "not_found"

    for url in candidate_urls(website):
        final_url, status, ok, _ = probe_url(client, url, fetch_body=False)
        if ok and isinstance(status, int):
            if looks_like_career(final_url) or looks_like_career(url):
                return final_url, f"ok:{status}"
            if best is None:
                best = (final_url, status)
        else:
            last_status = f"fail:{status}"

    # Homepage mine for ATS / careers links
    home = website if "://" in website else f"https://{website}"
    final_url, status, ok, body = probe_url(client, home, fetch_body=True)
    if ok and body:
        for link in _extract_ats_links(body, final_url):
            f2, s2, ok2, _ = probe_url(client, link, fetch_body=False)
            if ok2 and looks_like_career(f2):
                return f2, f"ok:{s2}"

    if best:
        return best[0], f"ok_redirect:{best[1]}"
    return "", last_status


def _should_resolve(row: Company, *, missing_only: bool, force: bool) -> bool:
    if row.skip:
        return False
    if not row.website:
        return False
    if row.career_page_source == "manual" and not force:
        return False
    if force:
        return True
    if missing_only:
        return not bool(row.career_page)
    return True


def resolve_one(row: Company, *, timeout: float) -> ResolveResult:
    if not row.website:
        return ResolveResult(row.name, "", "no_website", changed=row.career_page_status != "no_website")

    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    with httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"},
        timeout=httpx.Timeout(timeout, connect=min(5.0, timeout)),
        follow_redirects=True,
        limits=limits,
    ) as client:
        career_page, status = resolve_website(client, row.website)

    changed = career_page != (row.career_page or "") or status != (row.career_page_status or "")
    return ResolveResult(row.name, career_page, status, changed=changed)


def resolve_careers(
    session: Session,
    *,
    company_name: str | None = None,
    category: str | None = None,
    missing_only: bool = True,
    force: bool = False,
    concurrency: int = 8,
    timeout: float = 8.0,
) -> dict:
    q = select(Company).order_by(Company.category, Company.name)
    if company_name:
        q = q.where(Company.name == company_name)
    if category:
        q = q.where(Company.category == category)
    rows = list(session.scalars(q))
    if company_name and not rows:
        raise LookupError(f"Company not found: {company_name}")
    if category and not rows:
        raise LookupError(f"No companies found for category: {category}")

    # Mark no-website rows
    now = datetime.now(timezone.utc)
    for row in rows:
        if not row.website and not row.career_page and row.career_page_source != "manual":
            if row.career_page_status != "no_website":
                row.career_page_status = "no_website"
                row.updated_at = now

    targets = [r for r in rows if _should_resolve(r, missing_only=missing_only, force=force)]
    logger.info(
        "Resolving careers for %s companies (missing_only=%s force=%s timeout=%s)",
        len(targets),
        missing_only,
        force,
        timeout,
    )

    results: list[ResolveResult] = []
    by_name = {r.name: r for r in targets}
    done = 0

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {pool.submit(resolve_one, row, timeout=timeout): row.name for row in targets}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                result = fut.result()
            except Exception as e:  # noqa: BLE001
                logger.exception("Resolve failed for %s", name)
                result = ResolveResult(name, "", f"fail:{type(e).__name__}", changed=True)
            results.append(result)
            done += 1
            if done % 10 == 0 or done == len(targets):
                found_so_far = sum(1 for r in results if r.career_page)
                logger.info("Resolve progress %s/%s (found %s)", done, len(targets), found_so_far)

    found = 0
    updated = 0
    now = datetime.now(timezone.utc)
    for result in results:
        row = by_name[result.company_name]
        if result.career_page:
            found += 1
        if result.changed or not row.career_page_status:
            row.career_page = result.career_page
            row.career_page_status = result.career_page_status
            if result.career_page and row.career_page_source != "manual":
                row.career_page_source = "auto"
            row.updated_at = now
            updated += 1

    session.commit()
    return {
        "targeted": len(targets),
        "updated": updated,
        "found": found,
        "still_missing": sum(1 for r in results if not r.career_page),
        "results": [
            {
                "company_name": r.company_name,
                "career_page": r.career_page,
                "career_page_status": r.career_page_status,
                "changed": r.changed,
            }
            for r in sorted(results, key=lambda x: x.company_name)
        ],
    }
