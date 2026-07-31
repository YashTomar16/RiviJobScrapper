from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RawJob:
    title: str
    location: str = ""
    job_url: str = ""
    external_id: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class FetchResult:
    jobs: list[RawJob]
    parser: str
    http_status: str = "200"
    error: str = ""
    success: bool = True
