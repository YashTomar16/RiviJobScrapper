from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


PROMPT_VERSION = "v1"


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        # Split on newlines or semicolons when model returns a blob
        if "\n" in text:
            return [ln.strip(" -•\t") for ln in text.splitlines() if ln.strip()]
        return [text]
    return [str(value)]


class PriorityCompany(BaseModel):
    company: str
    rationale: str
    cited_titles: list[str] = Field(default_factory=list)
    cited_urls: list[str] = Field(default_factory=list)

    @field_validator("cited_titles", "cited_urls", mode="before")
    @classmethod
    def _coerce_str_lists(cls, v: Any) -> list[str]:
        return _as_str_list(v)


class RoleCallout(BaseModel):
    company: str
    title: str
    job_url: str = ""
    why_it_matters: str = ""


class OutreachAngle(BaseModel):
    company: str
    angle: str = ""
    related_titles: list[str] = Field(default_factory=list)

    @field_validator("related_titles", mode="before")
    @classmethod
    def _coerce_related(cls, v: Any) -> list[str]:
        return _as_str_list(v)

    @model_validator(mode="before")
    @classmethod
    def _normalize_angle_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if not (out.get("angle") or "").strip():
            parts: list[str] = []
            for key in ("talking_points", "talking_point", "outreach", "rationale", "message"):
                if out.get(key):
                    parts.append(str(out[key]))
            if out.get("timing"):
                parts.append(f"Timing: {out['timing']}")
            if parts:
                out["angle"] = " — ".join(parts)
        return out



class GroqInsightsResponse(BaseModel):
    executive_brief: str = ""
    priority_companies: list[PriorityCompany] = Field(default_factory=list)
    role_callouts: list[RoleCallout] = Field(default_factory=list)
    outreach_angles: list[OutreachAngle] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)

    @field_validator("risk_notes", mode="before")
    @classmethod
    def _coerce_risk_notes(cls, v: Any) -> list[str]:
        return _as_str_list(v)

    @field_validator("priority_companies", "role_callouts", "outreach_angles", mode="before")
    @classmethod
    def _coerce_empty_lists(cls, v: Any) -> Any:
        if v is None:
            return []
        return v


def response_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "executive_brief": {"type": "string"},
            "priority_companies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "company": {"type": "string"},
                        "rationale": {"type": "string"},
                        "cited_titles": {"type": "array", "items": {"type": "string"}},
                        "cited_urls": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["company", "rationale"],
                },
            },
            "role_callouts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "company": {"type": "string"},
                        "title": {"type": "string"},
                        "job_url": {"type": "string"},
                        "why_it_matters": {"type": "string"},
                    },
                    "required": ["company", "title"],
                },
            },
            "outreach_angles": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "company": {"type": "string"},
                        "angle": {"type": "string"},
                        "related_titles": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["company", "angle"],
                },
            },
            "risk_notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "executive_brief",
            "priority_companies",
            "role_callouts",
            "outreach_angles",
            "risk_notes",
        ],
    }


def _known_pairs(pack: dict[str, Any]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for key in (
        "new_openings",
        "leadership_pulse",
        "removals",
        "updated_openings",
        "open_roles",
    ):
        for row in pack.get(key, []) or []:
            company = (row.get("company") or "").strip().lower()
            title = (row.get("title") or "").strip().lower()
            if company and title:
                pairs.add((company, title))
    return pairs


def _known_companies(pack: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for row in pack.get("hottest_companies", []) or []:
        if row.get("company"):
            names.add(row["company"].strip().lower())
    for key in ("new_openings", "leadership_pulse", "removals", "open_roles"):
        for row in pack.get(key, []) or []:
            if row.get("company"):
                names.add(row["company"].strip().lower())
    return names


def ground_insights(
    parsed: GroqInsightsResponse,
    pack: dict[str, Any],
) -> tuple[GroqInsightsResponse, list[str]]:
    """Drop ungrounded callouts/priorities. Returns (cleaned, drop_notes)."""
    pairs = _known_pairs(pack)
    companies = _known_companies(pack)
    drops: list[str] = []

    grounded_priorities: list[PriorityCompany] = []
    for p in parsed.priority_companies:
        if p.company.strip().lower() not in companies and companies:
            drops.append(f"Dropped priority company not in pack: {p.company}")
            continue
        # Keep titles that match; strip invented ones
        cited = [
            t
            for t in p.cited_titles
            if (p.company.strip().lower(), t.strip().lower()) in pairs or not pairs
        ]
        if p.cited_titles and not cited and pairs:
            drops.append(f"Dropped ungrounded citations for {p.company}")
        grounded_priorities.append(
            p.model_copy(update={"cited_titles": cited or p.cited_titles[:0]})
        )

    grounded_callouts: list[RoleCallout] = []
    for c in parsed.role_callouts:
        key = (c.company.strip().lower(), c.title.strip().lower())
        if pairs and key not in pairs:
            drops.append(f"Dropped ungrounded callout: {c.company} / {c.title}")
            continue
        grounded_callouts.append(c)

    grounded_angles: list[OutreachAngle] = []
    for a in parsed.outreach_angles:
        if companies and a.company.strip().lower() not in companies:
            drops.append(f"Dropped outreach angle for unknown company: {a.company}")
            continue
        grounded_angles.append(a)

    risk = list(parsed.risk_notes)
    if drops:
        risk.append(f"Grounding filter removed {len(drops)} ungrounded item(s).")

    cleaned = GroqInsightsResponse(
        executive_brief=parsed.executive_brief,
        priority_companies=grounded_priorities,
        role_callouts=grounded_callouts,
        outreach_angles=grounded_angles,
        risk_notes=risk,
    )
    return cleaned, drops
