from __future__ import annotations

import json
import re
from html import unescape
from urllib.parse import urljoin

import httpx

from rivi.ingest.types import FetchResult, RawJob

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

JOB_HREF_RE = re.compile(
    r'href=["\']([^"\']*(?:job|career|position|opening|vacanc)[^"\']*)["\']',
    re.I,
)
ANCHOR_RE = re.compile(
    r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    re.I | re.S,
)
JSON_LD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)

NAV_TITLES = {
    "careers",
    "jobs",
    "view all",
    "see all jobs",
    "search",
    "apply",
    "apply now",
    "benefits",
    "feedback",
    "skip to main content",
    "learn more",
    "view our open positions",
    "see full offerings",
    "home",
    "about",
    "contact",
}

TITLE_ROLE_HINT = re.compile(
    r"\b(engineer|developer|manager|director|analyst|scientist|architect|"
    r"officer|vp|head|intern|specialist|lead|principal|staff|product|"
    r"designer|researcher|technician|administrator|consultant)\b",
    re.I,
)


def _clean_text(html_fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html_fragment)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _looks_like_job_title(title: str) -> bool:
    t = title.strip()
    if not t or len(t) < 5 or len(t) > 160:
        return False
    if "<" in t or ">" in t or "Icon" in t:
        return False
    if t.lower() in NAV_TITLES:
        return False
    if t.lower().startswith(("see ", "learn ", "explore ", "find ", "view ", "search ")):
        return False
    return bool(TITLE_ROLE_HINT.search(t))


def parse_html_jobs(html: str, base_url: str) -> list[RawJob]:
    jobs: list[RawJob] = []
    seen: set[str] = set()

    for match in JSON_LD_RE.finditer(html):
        raw = match.group(1).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            candidates = graph if isinstance(graph, list) else [item]
            for node in candidates:
                if not isinstance(node, dict):
                    continue
                if node.get("@type") != "JobPosting":
                    continue
                title = node.get("title") or ""
                url = node.get("url") or base_url
                loc = ""
                jl = node.get("jobLocation")
                if isinstance(jl, dict):
                    addr = jl.get("address") or {}
                    if isinstance(addr, dict):
                        loc = addr.get("addressLocality") or addr.get("name") or ""
                if title:
                    key = (title + "|" + str(url)).lower()
                    if key not in seen:
                        seen.add(key)
                        jobs.append(
                            RawJob(title=title, location=str(loc), job_url=str(url), raw=node)
                        )

    for href, inner in ANCHOR_RE.findall(html):
        full = urljoin(base_url, href.split("#")[0])
        title = _clean_text(inner)
        if not _looks_like_job_title(title):
            continue
        low = full.lower()
        path_ok = any(
            k in low for k in ("/job", "jobs/", "career", "position", "opening", "requisition")
        )
        if not path_ok:
            continue
        key = (title + "|" + full).lower()
        if key in seen:
            continue
        seen.add(key)
        jobs.append(RawJob(title=title, job_url=full))

    return jobs


def fetch_html_jobs(career_url: str, timeout: float) -> FetchResult:
    with httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        try:
            resp = client.get(career_url)
        except httpx.HTTPError as e:
            return FetchResult([], "html", type(e).__name__, str(e), False)

        if resp.status_code >= 400:
            return FetchResult([], "html", str(resp.status_code), resp.text[:300], False)

        html = resp.text
        jobs = parse_html_jobs(html, str(resp.url))

        if not jobs:
            from rivi.ingest.ats import detect_and_fetch_ats

            for href in JOB_HREF_RE.findall(html)[:20]:
                full = urljoin(str(resp.url), href)
                ats = detect_and_fetch_ats(full, timeout)
                if ats and ats.success and ats.jobs:
                    return ats

        if not jobs and (
            "workday" in html.lower()
            or "greenhouse" in html.lower()
            or "__NEXT_DATA__" in html
            or "myworkdayjobs" in html.lower()
        ):
            return FetchResult(
                [],
                "html",
                str(resp.status_code),
                "js_required_or_empty",
                success=True,
            )

        return FetchResult(jobs, "html", str(resp.status_code), success=True)


def peek_html_for_ats(career_url: str, timeout: float = 15.0) -> str:
    """Return raw HTML for ATS token discovery (best-effort)."""
    try:
        with httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            resp = client.get(career_url)
            if resp.status_code >= 400:
                return ""
            return resp.text[:200_000]
    except httpx.HTTPError:
        return ""

