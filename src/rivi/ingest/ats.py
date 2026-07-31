from __future__ import annotations

import re
import time
from urllib.parse import urlparse

import httpx

from rivi.ingest.types import FetchResult, RawJob

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _client(timeout: float) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/html,*/*"},
        timeout=timeout,
        follow_redirects=True,
    )


def fetch_greenhouse(board_token: str, timeout: float) -> FetchResult:
    from rivi.ingest.rate_limit import get_pacer

    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    get_pacer().wait(url)
    with _client(timeout) as client:
        resp = client.get(url)
        if resp.status_code == 429:
            time.sleep(2.0)
            get_pacer().wait(url)
            resp = client.get(url)
        if resp.status_code >= 400:
            return FetchResult([], "greenhouse", str(resp.status_code), resp.text[:300], False)
        data = resp.json()
        jobs: list[RawJob] = []
        for j in data.get("jobs", []):
            loc = ""
            if isinstance(j.get("location"), dict):
                loc = j["location"].get("name") or ""
            jobs.append(
                RawJob(
                    title=j.get("title") or "",
                    location=loc,
                    job_url=j.get("absolute_url") or "",
                    external_id=str(j.get("id") or ""),
                    raw=j,
                )
            )
        return FetchResult(jobs, "greenhouse", str(resp.status_code))


def fetch_lever(company: str, timeout: float) -> FetchResult:
    from rivi.ingest.rate_limit import get_pacer

    url = f"https://api.lever.co/v0/postings/{company}?mode=json"
    get_pacer().wait(url)
    with _client(timeout) as client:
        resp = client.get(url)
        if resp.status_code == 429:
            time.sleep(2.0)
            get_pacer().wait(url)
            resp = client.get(url)
        if resp.status_code >= 400:
            return FetchResult([], "lever", str(resp.status_code), resp.text[:300], False)
        data = resp.json()
        jobs: list[RawJob] = []
        for j in data:
            cats = j.get("categories") or {}
            loc = cats.get("location") or ""
            jobs.append(
                RawJob(
                    title=j.get("text") or "",
                    location=loc,
                    job_url=j.get("hostedUrl") or j.get("applyUrl") or "",
                    external_id=str(j.get("id") or ""),
                    raw=j,
                )
            )
        return FetchResult(jobs, "lever", str(resp.status_code))


def fetch_ashby(org: str, timeout: float) -> FetchResult:
    from rivi.ingest.rate_limit import get_pacer

    url = f"https://api.ashbyhq.com/posting-api/job-board/{org}"
    get_pacer().wait(url)
    with _client(timeout) as client:
        resp = client.get(url)
        if resp.status_code == 429:
            time.sleep(2.0)
            get_pacer().wait(url)
            resp = client.get(url)
        if resp.status_code >= 400:
            return FetchResult([], "ashby", str(resp.status_code), resp.text[:300], False)
        data = resp.json()
        jobs: list[RawJob] = []
        for j in data.get("jobs", []):
            jobs.append(
                RawJob(
                    title=j.get("title") or "",
                    location=j.get("location") or "",
                    job_url=j.get("jobUrl") or "",
                    external_id=str(j.get("id") or ""),
                    raw=j,
                )
            )
        return FetchResult(jobs, "ashby", str(resp.status_code))


def fetch_workday(career_url: str, timeout: float) -> FetchResult:
    """Fetch Workday CXS job listings from a myworkdayjobs.com career URL."""
    from rivi.ingest.rate_limit import get_pacer

    parsed = urlparse(career_url)
    host = parsed.netloc
    # e.g. ntrs.wd1.myworkdayjobs.com /northerntrust
    m = re.match(r"^(?P<tenant>[^.]+)\.(?P<wd>wd\d+)\.myworkdayjobs\.com$", host, re.I)
    if not m:
        return FetchResult([], "workday", "", "unrecognized_workday_host", False)
    tenant = m.group("tenant")
    path = parsed.path.strip("/")
    site = path.split("/")[0] if path else ""
    if not site:
        return FetchResult([], "workday", "", "missing_workday_site", False)

    board_url = f"https://{host}/{site}"
    api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    payload = {"limit": 50, "offset": 0}
    jobs: list[RawJob] = []

    get_pacer().wait(board_url)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        # Warm session cookies (CSRF / PLAY_SESSION) — required by many Workday boards
        warm = client.get(
            board_url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )
        if warm.status_code >= 400:
            return FetchResult([], "workday", str(warm.status_code), "board_warmup_failed", False)

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": board_url,
        }
        # Note: do not send X-CALYPSO-CSRF-TOKEN — it causes HTTP 400 on some tenants.

        offset = 0
        http_status = "200"
        while offset < 500:
            payload["offset"] = offset
            get_pacer().wait(api)
            resp = client.post(api, json=payload, headers=headers)
            http_status = str(resp.status_code)
            if resp.status_code == 429:
                time.sleep(2.5)
                continue
            if resp.status_code >= 400:
                if offset == 0:
                    return FetchResult([], "workday", http_status, resp.text[:300], False)
                break
            try:
                data = resp.json()
            except Exception as e:  # noqa: BLE001
                if offset == 0:
                    return FetchResult([], "workday", http_status, f"json_error:{e}", False)
                break
            postings = data.get("jobPostings") or []
            if not postings:
                break
            for j in postings:
                title = j.get("title") or ""
                loc = j.get("locationsText") or ""
                bullets = j.get("bulletFields") or []
                ext = str(bullets[0]) if bullets else ""
                path_url = j.get("externalPath") or ""
                job_url = urljoin_workday(career_url, path_url)
                jobs.append(
                    RawJob(
                        title=title,
                        location=loc,
                        job_url=job_url,
                        external_id=ext or path_url,
                        raw=j,
                    )
                )
            total = int(data.get("total") or 0)
            offset += len(postings)
            if offset >= total or len(postings) < payload["limit"]:
                break
            # Polite pacing — Workday rate-limits aggressive pagination
            time.sleep(0.35)
        return FetchResult(jobs, "workday", http_status)


def urljoin_workday(career_url: str, external_path: str) -> str:
    if not external_path:
        return career_url
    if external_path.startswith("http"):
        return external_path
    parsed = urlparse(career_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    # career_url like .../northerntrust — job path often /job/...
    site = parsed.path.strip("/").split("/")[0]
    if external_path.startswith("/"):
        return f"{base}/{site}{external_path}"
    return f"{base}/{site}/{external_path}"


def detect_and_fetch_ats(career_url: str, timeout: float) -> FetchResult | None:
    low = career_url.lower()
    parsed = urlparse(career_url)

    if "myworkdayjobs.com" in low:
        return fetch_workday(career_url, timeout)

    gh = re.search(r"boards\.greenhouse\.io/([^/?#]+)", low)
    if gh:
        return fetch_greenhouse(gh.group(1), timeout)
    gh2 = re.search(r"job-boards\.greenhouse\.io/([^/?#]+)", low)
    if gh2:
        return fetch_greenhouse(gh2.group(1), timeout)
    # Embedded Greenhouse board token in query (?for=token) or path fragments
    gh3 = re.search(r"[?&]for=([a-z0-9_-]+)", low)
    if gh3 and "greenhouse" in low:
        return fetch_greenhouse(gh3.group(1), timeout)

    lever = re.search(r"jobs\.lever\.co/([^/?#]+)", low)
    if lever:
        return fetch_lever(lever.group(1), timeout)

    ashby = re.search(r"jobs\.ashbyhq\.com/([^/?#]+)", low)
    if ashby:
        return fetch_ashby(ashby.group(1), timeout)

    # SmartRecruiters company board
    sr = re.search(r"jobs\.smartrecruiters\.com/([^/?#]+)", low)
    if sr:
        return fetch_smartrecruiters(sr.group(1), timeout)

    # Workday alternate hosts (wdN.myworkdaysite.com rare) — leave to HTML
    _ = parsed
    return None


def fetch_smartrecruiters(company: str, timeout: float) -> FetchResult:
    from rivi.ingest.rate_limit import get_pacer

    url = f"https://api.smartrecruiters.com/v1/companies/{company}/postings"
    jobs: list[RawJob] = []
    with _client(timeout) as client:
        offset = 0
        http_status = "200"
        while offset < 500:
            get_pacer().wait(url)
            resp = client.get(url, params={"offset": offset, "limit": 100})
            http_status = str(resp.status_code)
            if resp.status_code == 429:
                time.sleep(2.0)
                continue
            if resp.status_code >= 400:
                if offset == 0:
                    return FetchResult([], "smartrecruiters", http_status, resp.text[:300], False)
                break
            data = resp.json()
            content = data.get("content") or []
            if not content:
                break
            for j in content:
                loc = ""
                loc_obj = j.get("location") or {}
                if isinstance(loc_obj, dict):
                    loc = loc_obj.get("city") or loc_obj.get("region") or ""
                ref = j.get("ref") or j.get("id") or ""
                jobs.append(
                    RawJob(
                        title=j.get("name") or "",
                        location=str(loc),
                        job_url=j.get("postingUrl") or f"https://jobs.smartrecruiters.com/{company}/{ref}",
                        external_id=str(ref),
                        raw=j,
                    )
                )
            offset += len(content)
            if offset >= (data.get("totalFound") or 0):
                break
            time.sleep(0.25)
        return FetchResult(jobs, "smartrecruiters", http_status)
