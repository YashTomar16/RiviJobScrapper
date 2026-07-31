from __future__ import annotations

import hashlib
import logging
import re
from urllib.parse import urlparse, urlunparse

from rivi.classifier import classify_title
from rivi.ingest.ats import detect_and_fetch_ats
from rivi.ingest.html_parser import fetch_html_jobs
from rivi.ingest.types import FetchResult, RawJob

logger = logging.getLogger("rivi.ingest")

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gh_src",
    "van",
}


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        p = urlparse(url.strip())
        query_parts = []
        if p.query:
            for part in p.query.split("&"):
                if not part:
                    continue
                key = part.split("=", 1)[0].lower()
                if key in TRACKING_PARAMS:
                    continue
                query_parts.append(part)
        clean = p._replace(query="&".join(query_parts), fragment="")
        return urlunparse(clean).rstrip("/")
    except Exception:  # noqa: BLE001
        return url.strip()


def identity_key(company_id: int, job: RawJob) -> str:
    if job.external_id:
        return f"ext:{job.external_id}"
    url = canonicalize_url(job.job_url)
    if url:
        return f"url:{url}"
    title = re.sub(r"\s+", " ", (job.title or "").strip().lower())
    loc = re.sub(r"\s+", " ", (job.location or "").strip().lower())
    digest = hashlib.sha1(f"{company_id}|{title}|{loc}".encode()).hexdigest()[:16]
    return f"fallback:{digest}"


def dedupe_jobs(jobs: list[RawJob]) -> list[RawJob]:
    seen: set[str] = set()
    out: list[RawJob] = []
    for job in jobs:
        key = (canonicalize_url(job.job_url) or "") + "|" + (job.external_id or "") + "|" + (job.title or "").lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(job)
    return out


def split_career_urls(career_page: str) -> list[str]:
    """Split a career_page value into one or more scrape targets.

    Multiple boards may be stored pipe- or newline-separated
    (e.g. Wells Fargo Engineering + Product search URLs).
    """
    if not career_page or not career_page.strip():
        return []
    parts: list[str] = []
    for chunk in career_page.replace("\n", "|").split("|"):
        url = chunk.strip()
        if url and url not in parts:
            parts.append(url)
    return parts


def scrape_single_career_url(
    career_url: str,
    timeout: float,
    *,
    use_playwright: bool = False,
    respect_robots: bool = True,
    domain_delay: float = 0.5,
) -> FetchResult:
    if not career_url:
        return FetchResult([], "none", "", "no_career_url", False)

    from rivi.ingest.rate_limit import get_pacer, robots_allows

    get_pacer(domain_delay)

    if respect_robots and not robots_allows(career_url, timeout=min(timeout, 5.0)):
        logger.info("robots.txt disallows %s — skipping", career_url)
        return FetchResult([], "robots", "", "robots_blocked", False)

    ats = detect_and_fetch_ats(career_url, timeout)
    if ats is not None:
        if ats.success:
            ats.jobs = dedupe_jobs(ats.jobs)
            return ats
        logger.info("ATS fetch failed for %s (%s); falling back to HTML", career_url, ats.error)

    # HTML path: try to discover Greenhouse board token in page markup
    html = fetch_html_jobs(career_url, timeout)
    if not html.jobs and html.success:
        embed = _greenhouse_token_from_html_error_or_url(career_url, html)
        if embed:
            gh = detect_and_fetch_ats(
                f"https://boards.greenhouse.io/{embed}", timeout
            )
            if gh and gh.success and gh.jobs:
                gh.jobs = dedupe_jobs(gh.jobs)
                return gh

    html.jobs = dedupe_jobs(html.jobs)

    # Playwright for empty HTML, hard bot walls (403/Cloudflare), or soft HTML failures
    need_pw = use_playwright and (
        (not html.jobs and html.success)
        or (not html.jobs and not html.success)
        or (html.http_status in {"403", "429", "503"})
    )
    if need_pw:
        try:
            from rivi.ingest.playwright_fetch import fetch_with_playwright

            pw = fetch_with_playwright(career_url, timeout)
            if pw.jobs:
                pw.jobs = dedupe_jobs(pw.jobs)
                return pw
            if not html.jobs:
                return pw
        except ImportError:
            html.error = (html.error + "; playwright_not_installed").strip("; ")
        except Exception as e:  # noqa: BLE001
            html.error = (html.error + f"; playwright_error:{type(e).__name__}").strip("; ")

    return html


def scrape_career_page(
    career_url: str,
    timeout: float,
    *,
    use_playwright: bool = False,
    respect_robots: bool = True,
    domain_delay: float = 0.5,
) -> FetchResult:
    urls = split_career_urls(career_url)
    if not urls:
        return FetchResult([], "none", "", "no_career_url", False)
    if len(urls) == 1:
        return scrape_single_career_url(
            urls[0],
            timeout,
            use_playwright=use_playwright,
            respect_robots=respect_robots,
            domain_delay=domain_delay,
        )

    all_jobs: list[RawJob] = []
    parsers: list[str] = []
    errors: list[str] = []
    statuses: list[str] = []
    any_success = False
    for url in urls:
        result = scrape_single_career_url(
            url,
            timeout,
            use_playwright=use_playwright,
            respect_robots=respect_robots,
            domain_delay=domain_delay,
        )
        all_jobs.extend(result.jobs)
        if result.parser:
            parsers.append(result.parser)
        if result.http_status:
            statuses.append(result.http_status)
        if result.error:
            errors.append(f"{url}: {result.error}")
        if result.success or result.jobs:
            any_success = True

    jobs = dedupe_jobs(all_jobs)
    parser = "+".join(dict.fromkeys(parsers)) or "multi"
    status = statuses[0] if statuses else ""
    error = "; ".join(errors) if errors and not jobs else ("; ".join(errors) if not any_success else "")
    return FetchResult(jobs, parser, status, error, any_success or bool(jobs))


def _greenhouse_token_from_html_error_or_url(career_url: str, html_result: FetchResult) -> str:
    """Best-effort extract Greenhouse board token from career page HTML payload."""
    # html_parser may stash raw in error/jobs; try fetching lightly via raw attribute if present
    raw = ""
    try:
        from rivi.ingest.html_parser import peek_html_for_ats

        raw = peek_html_for_ats(career_url) or ""
    except Exception:  # noqa: BLE001
        raw = ""
    if not raw:
        return ""
    m = re.search(
        r"boards(?:-api)?\.greenhouse\.io/(?:v1/boards/)?([a-zA-Z0-9_-]+)",
        raw,
        re.I,
    )
    if m:
        return m.group(1)
    m2 = re.search(r'grnhse_app[^>]+board_token["\s:=]+["\']?([a-zA-Z0-9_-]+)', raw, re.I)
    if m2:
        return m2.group(1)
    m3 = re.search(r'["\']boardToken["\']\s*:\s*["\']([a-zA-Z0-9_-]+)["\']', raw, re.I)
    if m3:
        return m3.group(1)
    _ = html_result
    return ""


def classify_jobs(jobs: list[RawJob]) -> list[tuple[RawJob, object]]:
    return [(job, classify_title(job.title)) for job in jobs]
