from __future__ import annotations

import logging
import threading
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger("rivi.rate_limit")

USER_AGENT = (
    "Mozilla/5.0 (compatible; RiviBot/0.1; +https://github.com/riviera/rivi; research)"
)


class DomainPacer:
    """Per-domain minimum delay between requests (thread-safe)."""

    def __init__(self, min_interval_seconds: float = 0.5):
        self.min_interval = max(0.0, float(min_interval_seconds))
        self._lock = threading.Lock()
        self._last: dict[str, float] = {}

    def wait(self, url_or_host: str) -> None:
        host = url_or_host
        if "://" in url_or_host:
            host = urlparse(url_or_host).netloc.lower()
        host = host.lower()
        if not host or self.min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            last = self._last.get(host, 0.0)
            delay = self.min_interval - (now - last)
            if delay > 0:
                time.sleep(delay)
            self._last[host] = time.monotonic()


_robots_cache: dict[str, RobotFileParser | None] = {}
_robots_lock = threading.Lock()


def robots_allows(url: str, *, timeout: float = 5.0, user_agent: str = USER_AGENT) -> bool:
    """Return False if robots.txt explicitly disallows the path for our UA.

    On fetch failure, allow (soft) — do not block the whole run on robots outage.
    """
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return True
    base = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = f"{base}/robots.txt"

    with _robots_lock:
        if robots_url in _robots_cache:
            rp = _robots_cache[robots_url]
        else:
            rp = RobotFileParser()
            try:
                with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                    resp = client.get(
                        robots_url,
                        headers={"User-Agent": user_agent},
                    )
                    if resp.status_code >= 400:
                        _robots_cache[robots_url] = None
                        return True
                    rp.parse(resp.text.splitlines())
                    _robots_cache[robots_url] = rp
            except Exception as e:  # noqa: BLE001
                logger.debug("robots.txt fetch failed for %s: %s", robots_url, e)
                _robots_cache[robots_url] = None
                return True
            rp = _robots_cache[robots_url]

    if rp is None:
        return True
    try:
        return bool(rp.can_fetch(user_agent, url))
    except Exception:  # noqa: BLE001
        return True


# Shared pacer instance (configured by callers via reset)
_default_pacer = DomainPacer(0.5)


def get_pacer(min_interval: float | None = None) -> DomainPacer:
    global _default_pacer
    if min_interval is not None and abs(_default_pacer.min_interval - min_interval) > 1e-6:
        _default_pacer = DomainPacer(min_interval)
    return _default_pacer
