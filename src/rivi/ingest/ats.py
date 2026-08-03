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


def _workday_site_from_path(path: str) -> str:
    """Extract Workday site slug from path.

    Handles both `/northerntrust` and localized `/en-US/001` boards.
    """
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts:
        return ""
    if len(parts) >= 2 and re.match(r"^[a-z]{2}(?:-[A-Z]{2})?$", parts[0]):
        return parts[1]
    return parts[0]


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
    site = _workday_site_from_path(parsed.path)
    if not site:
        return FetchResult([], "workday", "", "missing_workday_site", False)

    # Prefer the original path (keeps locale segment) for warmup/referer.
    path_prefix = parsed.path.strip("/") or site
    board_url = f"https://{host}/{path_prefix}"
    api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    jobs: list[RawJob] = []

    get_pacer().wait(board_url)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        # Warm session cookies (CSRF / PLAY_SESSION) — required by many Workday boards
        warm = client.get(
            board_url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )
        if warm.status_code >= 400:
            # Retry without locale prefix (e.g. /001 instead of /en-US/001)
            alt = f"https://{host}/{site}"
            if alt != board_url:
                warm = client.get(
                    alt,
                    headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
                )
                board_url = alt
        if warm.status_code >= 400:
            return FetchResult([], "workday", str(warm.status_code), "board_warmup_failed", False)

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": board_url,
        }
        # Note: do not send X-CALYPSO-CSRF-TOKEN — it causes HTTP 400 on some tenants.
        # Some tenants (Fidelity) reject limit>20; keep page size conservative.
        page_limit = 20
        payload_templates = [
            {"limit": page_limit, "offset": 0},
            {"appliedFacets": {}, "limit": page_limit, "offset": 0, "searchText": ""},
        ]
        chosen: dict | None = None
        probe_error = ""
        http_status = ""
        for template in payload_templates:
            get_pacer().wait(api)
            probe = client.post(api, json={**template, "offset": 0}, headers=headers)
            if probe.status_code == 200:
                chosen = template
                break
            probe_error = probe.text[:300]
            http_status = str(probe.status_code)
        if chosen is None:
            return FetchResult([], "workday", http_status or "400", probe_error, False)

        offset = 0
        http_status = "200"
        while offset < 500:
            payload = {**chosen, "offset": offset}
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
                path_url = j.get("externalPath") or ""
                # Prefer requisition id from path (..._J12345) or numeric bullet;
                # ignore "Posting Date: ..." noise in bulletFields.
                ext = ""
                m_id = re.search(r"_(J?\d{4,})(?:-|$)", path_url or "")
                if m_id:
                    ext = m_id.group(1)
                if not ext:
                    for b in bullets:
                        bs = str(b).strip()
                        if re.match(r"^J?\d{4,}$", bs):
                            ext = bs
                            break
                # Location often buried in path (/job/New-York/...) or first bullet
                if not loc and path_url:
                    mloc = re.match(r"^/job/([^/]+)/", path_url)
                    if mloc:
                        loc = mloc.group(1).replace("-", " ")
                if not loc and bullets:
                    cand = str(bullets[0])
                    if not cand.lower().startswith("posting date"):
                        loc = cand
                job_url = urljoin_workday(f"https://{host}/{site}", path_url)
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
            if offset >= total or len(postings) < page_limit:
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


def fetch_oracle_cloud_hcm(career_url: str, timeout: float) -> FetchResult:
    """Fetch Oracle Cloud HCM Candidate Experience requisitions."""
    from rivi.ingest.rate_limit import get_pacer

    parsed = urlparse(career_url)
    host = parsed.netloc
    # .../sites/BNY-Careers/jobs or ?siteNumber=
    site = ""
    m = re.search(r"/sites/([^/?#]+)", parsed.path, re.I)
    if m:
        site = m.group(1)
    if not site:
        m2 = re.search(r"[?&]siteNumber=([^&]+)", career_url, re.I)
        if m2:
            site = m2.group(1)
    # Many Oracle CE boards use CX_1 as the API site number even when the
    # marketing path uses a brand slug (BNY-Careers). Prefer CX_1 (full board).
    site_candidates: list[str] = ["CX_1"]
    if site and site not in site_candidates:
        site_candidates.append(site)

    base = f"{parsed.scheme}://{host}"
    jobs: list[RawJob] = []
    http_status = "200"
    used_site = site_candidates[0]

    get_pacer().wait(career_url)
    with _client(timeout) as client:
        # Warm CE session
        client.get(career_url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})

        for candidate in site_candidates:
            used_site = candidate
            jobs = []
            offset = 0
            while offset < 2000:
                api = (
                    f"{base}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
                    f"?onlyData=true&expand=requisitionList.secondaryLocations"
                    f"&finder=findReqs;siteNumber={candidate},limit=50,offset={offset}"
                )
                get_pacer().wait(api)
                resp = client.get(api)
                http_status = str(resp.status_code)
                if resp.status_code == 429:
                    time.sleep(2.0)
                    continue
                if resp.status_code >= 400:
                    break
                try:
                    data = resp.json()
                except Exception as e:  # noqa: BLE001
                    if offset == 0 and candidate == site_candidates[-1]:
                        return FetchResult([], "oracle_hcm", http_status, f"json_error:{e}", False)
                    break
                items = data.get("items") or []
                if not items:
                    break
                reqs = items[0].get("requisitionList") or []
                if not reqs:
                    break
                for j in reqs:
                    title = j.get("Title") or ""
                    loc = j.get("PrimaryLocation") or ""
                    rid = str(j.get("Id") or "")
                    job_url = (
                        f"{base}/hcmUI/CandidateExperience/en/sites/{site or candidate}"
                        f"/job/{rid}"
                        if rid
                        else career_url
                    )
                    jobs.append(
                        RawJob(
                            title=title,
                            location=loc,
                            job_url=job_url,
                            external_id=rid,
                            raw=j,
                        )
                    )
                total = int(items[0].get("TotalJobsCount") or 0)
                offset += len(reqs)
                if offset >= total or len(reqs) < 50:
                    break
                time.sleep(0.25)
            if jobs:
                break

    if not jobs:
        return FetchResult([], "oracle_hcm", http_status, "no_requisitions", False)
    return FetchResult(jobs, "oracle_hcm", http_status)


def _eightfold_domain_from_url(career_url: str, host: str) -> str:
    """Infer Eightfold tenant domain from query or hostname."""
    from urllib.parse import parse_qs

    qs = parse_qs(urlparse(career_url).query)
    if qs.get("domain"):
        return qs["domain"][0]
    # morganstanley.eightfold.ai → morganstanley.com
    # portal.careers.hsbc.com → hsbc.com
    host = host.lower()
    if host.endswith(".eightfold.ai"):
        tenant = host[: -len(".eightfold.ai")]
        if tenant and "." not in tenant:
            return f"{tenant}.com"
    parts = host.split(".")
    if len(parts) >= 2:
        # portal.careers.hsbc.com → hsbc.com
        return ".".join(parts[-2:])
    return host


def fetch_eightfold(career_url: str, timeout: float) -> FetchResult:
    """Fetch Eightfold PCS careers boards (HSBC portal, Morgan Stanley, etc.)."""
    from rivi.ingest.rate_limit import get_pacer
    from urllib.parse import parse_qs

    parsed = urlparse(career_url)
    host = parsed.netloc
    domain = _eightfold_domain_from_url(career_url, host)
    qs = parse_qs(parsed.query)
    location = (qs.get("location") or [""])[0]
    base = f"{parsed.scheme}://{host}"
    jobs: list[RawJob] = []
    http_status = "200"

    get_pacer().wait(career_url)
    with _client(timeout) as client:
        # Warm careers page for session cookies (required by some tenants)
        client.get(
            career_url if "/careers" in parsed.path else f"{base}/careers",
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        )

        # Prefer apply/v2 (HSBC); fall back to pcsx/search (Morgan Stanley)
        endpoints = [
            ("apply", f"{base}/api/apply/v2/jobs"),
            ("pcsx", f"{base}/api/pcsx/search"),
        ]
        chosen: str | None = None
        for kind, api in endpoints:
            params = {"domain": domain, "start": 0, "num": 1}
            if location:
                params["location"] = location
            get_pacer().wait(api)
            probe = client.get(
                api,
                params=params,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "Referer": career_url,
                },
            )
            if probe.status_code == 200:
                try:
                    pdata = probe.json()
                except Exception:  # noqa: BLE001
                    continue
                if kind == "apply" and isinstance(pdata.get("positions"), list):
                    chosen = kind
                    break
                if kind == "pcsx" and isinstance((pdata.get("data") or {}).get("positions"), list):
                    chosen = kind
                    break
            http_status = str(probe.status_code)

        if chosen is None:
            return FetchResult([], "eightfold", http_status, "no_eightfold_endpoint", False)

        # apply/v2 often caps num at 10; pcsx accepts larger pages
        page_size = 10 if chosen == "apply" else 50
        start = 0
        while start < 3000:
            params = {"domain": domain, "start": start, "num": page_size}
            if location:
                params["location"] = location
            api = f"{base}/api/apply/v2/jobs" if chosen == "apply" else f"{base}/api/pcsx/search"
            get_pacer().wait(api)
            resp = client.get(
                api,
                params=params,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "Referer": career_url,
                },
            )
            http_status = str(resp.status_code)
            if resp.status_code == 429:
                time.sleep(2.0)
                continue
            if resp.status_code >= 400:
                if start == 0:
                    return FetchResult([], "eightfold", http_status, resp.text[:300], False)
                break
            try:
                data = resp.json()
            except Exception as e:  # noqa: BLE001
                if start == 0:
                    return FetchResult([], "eightfold", http_status, f"json_error:{e}", False)
                break

            if chosen == "apply":
                positions = data.get("positions") or []
                total = int(data.get("count") or 0)
            else:
                payload = data.get("data") or {}
                positions = payload.get("positions") or []
                total = int(payload.get("count") or 0)

            if not positions:
                break
            for j in positions:
                title = j.get("name") or j.get("posting_name") or ""
                locs = j.get("locations") or []
                loc = ""
                if isinstance(locs, list) and locs:
                    loc = locs[0] if isinstance(locs[0], str) else str(locs[0])
                loc = loc or (j.get("location") or "")
                pid = str(j.get("id") or j.get("ats_job_id") or j.get("atsJobId") or "")
                job_url = (
                    j.get("canonicalPositionUrl")
                    or j.get("positionUrl")
                    or (f"{base}/careers/job/{pid}" if pid else career_url)
                )
                if job_url.startswith("/"):
                    job_url = f"{base}{job_url}"
                jobs.append(
                    RawJob(
                        title=title,
                        location=str(loc),
                        job_url=job_url,
                        external_id=pid,
                        raw=j,
                    )
                )
            start += len(positions)
            if not positions or (total and start >= total):
                break
            time.sleep(0.25)

    if not jobs:
        return FetchResult([], "eightfold", http_status, "no_positions", False)
    return FetchResult(jobs, "eightfold", http_status)


def fetch_bank_of_america(career_url: str, timeout: float) -> FetchResult:
    """Fetch Bank of America careers via jobssearchservlet.

    Note: ``rows`` is an exclusive end index (not page size). Page 2 is
    ``start=10&rows=20``, not ``start=10&rows=10``.
    """
    from rivi.ingest.rate_limit import get_pacer

    parsed = urlparse(career_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    api = f"{base}/services/jobssearchservlet"
    page_size = 50
    jobs: list[RawJob] = []
    http_status = "200"
    seen: set[str] = set()

    get_pacer().wait(career_url)
    with _client(timeout) as client:
        client.get(career_url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        start = 0
        total = 0
        while start < 5000:
            end = start + page_size
            get_pacer().wait(api)
            resp = client.get(
                api,
                params={"start": start, "rows": end, "search": "getAllJobs"},
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "Referer": career_url,
                },
            )
            http_status = str(resp.status_code)
            if resp.status_code == 429:
                time.sleep(2.0)
                continue
            if resp.status_code >= 400:
                if start == 0:
                    return FetchResult([], "bofa", http_status, resp.text[:300], False)
                break
            try:
                data = resp.json()
            except Exception as e:  # noqa: BLE001
                if start == 0:
                    return FetchResult([], "bofa", http_status, f"json_error:{e}", False)
                break
            batch = data.get("jobsList") or []
            total = int(data.get("totalMatches") or total or 0)
            if not batch:
                break
            new_count = 0
            for j in batch:
                title = j.get("postingTitle") or ""
                city = j.get("city") or ""
                country = j.get("country") or ""
                loc = ", ".join(p for p in (city, country) if p)
                rid = str(j.get("jobRequisitionId") or "")
                if rid and rid in seen:
                    continue
                if rid:
                    seen.add(rid)
                new_count += 1
                path = j.get("jcrURL") or ""
                job_url = f"{base}{path}" if path.startswith("/") else (path or career_url)
                jobs.append(
                    RawJob(
                        title=title,
                        location=loc,
                        job_url=job_url,
                        external_id=rid,
                        raw=j,
                    )
                )
            start = end
            if not new_count or (total and start >= total):
                break
            time.sleep(0.25)

    if not jobs:
        return FetchResult([], "bofa", http_status, "no_jobs", False)
    return FetchResult(jobs, "bofa", http_status)


def detect_and_fetch_ats(career_url: str, timeout: float) -> FetchResult | None:
    low = career_url.lower()
    parsed = urlparse(career_url)

    if "myworkdayjobs.com" in low:
        return fetch_workday(career_url, timeout)

    if "oraclecloud.com" in low and ("hcmUI/CandidateExperience" in career_url or "recruitingCE" in low):
        return fetch_oracle_cloud_hcm(career_url, timeout)

    if "eightfold.ai" in low or "portal.careers.hsbc.com" in low:
        return fetch_eightfold(career_url, timeout)

    if "careers.bankofamerica.com" in low:
        return fetch_bank_of_america(career_url, timeout)

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
