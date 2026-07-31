from __future__ import annotations

"""Optional Playwright fetch for JS-rendered career boards."""

from rivi.ingest.html_parser import parse_html_jobs
from rivi.ingest.types import FetchResult


def fetch_with_playwright(career_url: str, timeout: float) -> FetchResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise ImportError(
            "Playwright is not installed. pip install playwright && playwright install chromium"
        ) from e

    ms = max(int(timeout * 1000), 45_000)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        page = context.new_page()
        page.set_default_timeout(ms)
        try:
            page.goto(career_url, wait_until="domcontentloaded")
            # Phenom / JS boards often hydrate after first paint
            page.wait_for_timeout(3500)
            try:
                page.wait_for_load_state("networkidle", timeout=min(ms, 20_000))
            except Exception:  # noqa: BLE001
                pass
            # Dismiss common cookie banners when present
            for sel in (
                "button:has-text('Accept')",
                "button:has-text('Accept All')",
                "#onetrust-accept-btn-handler",
            ):
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=800):
                        btn.click(timeout=1500)
                        page.wait_for_timeout(500)
                        break
                except Exception:  # noqa: BLE001
                    continue
            html = page.content()
            final_url = page.url
            title = page.title() or ""
        finally:
            browser.close()

    if "just a moment" in title.lower() or "cf-browser-verification" in html.lower():
        return FetchResult(
            [],
            "playwright",
            "403",
            "cloudflare_challenge",
            False,
        )

    jobs = parse_html_jobs(html, final_url)
    return FetchResult(jobs, "playwright", "200", success=True)
