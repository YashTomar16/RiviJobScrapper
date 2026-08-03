from __future__ import annotations

import logging
import threading
import time
from urllib.parse import urlparse

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


# robots.txt URL -> Allow/Disallow rules for UA *, or None when missing/unreadable
_robots_cache: dict[str, list[tuple[str, bool]] | None] = {}
_robots_lock = threading.Lock()


def _parse_robots_rules(text: str) -> list[tuple[str, bool]]:
    """Parse Allow/Disallow rules for User-agent: * (longest-match ready).

    Returns list of (path_prefix, is_allowed). Google-style longest match is
    applied by callers — Python's RobotFileParser uses first-match and treats
    ``Disallow: /`` as blocking every later ``Allow`` (breaks Eightfold/HSBC).
    """
    rules: list[tuple[str, bool]] = []
    in_star = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            if in_star and rules:
                # Blank line ends a group — keep collecting * only
                pass
            continue
        lower = line.lower()
        if lower.startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip()
            in_star = agent == "*"
            continue
        if not in_star:
            continue
        if lower.startswith("allow:"):
            path = line.split(":", 1)[1].strip() or "/"
            # Strip end-anchor marker used by some boards (Allow: /$)
            if path.endswith("$"):
                path = path[:-1] or "/"
            rules.append((path, True))
        elif lower.startswith("disallow:"):
            path = line.split(":", 1)[1].strip()
            if path == "":
                # Empty Disallow means allow all for this UA group
                continue
            rules.append((path, False))
    return rules


def _longest_match_allows(path: str, rules: list[tuple[str, bool]]) -> bool:
    """Google/Bing longest-prefix match over Allow/Disallow rules."""
    if not rules:
        return True
    best_len = -1
    allowed = True
    for prefix, is_allowed in rules:
        if path.startswith(prefix) and len(prefix) > best_len:
            best_len = len(prefix)
            allowed = is_allowed
    return allowed


def robots_allows(url: str, *, timeout: float = 5.0, user_agent: str = USER_AGENT) -> bool:
    """Return False if robots.txt explicitly disallows the path for our UA.

    On fetch failure, allow (soft) — do not block the whole run on robots outage.
    Uses longest-match Allow/Disallow (not urllib's first-match) so boards like
    Eightfold (``Disallow: /`` + ``Allow: /careers``) are handled correctly.
    """
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return True
    base = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = f"{base}/robots.txt"
    path = parsed.path or "/"

    with _robots_lock:
        if robots_url in _robots_cache:
            cached = _robots_cache[robots_url]
        else:
            cached = None
            try:
                with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                    resp = client.get(
                        robots_url,
                        headers={"User-Agent": user_agent},
                    )
                    if resp.status_code >= 400:
                        _robots_cache[robots_url] = None
                        return True
                    cached = _parse_robots_rules(resp.text)
                    _robots_cache[robots_url] = cached
            except Exception as e:  # noqa: BLE001
                logger.debug("robots.txt fetch failed for %s: %s", robots_url, e)
                _robots_cache[robots_url] = None
                return True
            cached = _robots_cache[robots_url]

    if cached is None:
        return True
    try:
        return _longest_match_allows(path, cached)
    except Exception:  # noqa: BLE001
        return True


# Shared pacer instance (configured by callers via reset)
_default_pacer = DomainPacer(0.5)


def get_pacer(min_interval: float | None = None) -> DomainPacer:
    global _default_pacer
    if min_interval is not None and abs(_default_pacer.min_interval - min_interval) > 1e-6:
        _default_pacer = DomainPacer(min_interval)
    return _default_pacer
