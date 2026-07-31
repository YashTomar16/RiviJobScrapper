from __future__ import annotations

import json
import logging
import re
from typing import Any

from rivi.config import Settings, get_settings
from rivi.insights.prompts import SYSTEM_PROMPT, user_prompt
from rivi.insights.schema import (
    PROMPT_VERSION,
    GroqInsightsResponse,
    ground_insights,
    response_json_schema,
)

logger = logging.getLogger("rivi.groq")


class GroqError(Exception):
    pass


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def call_groq(
    pack: dict[str, Any],
    settings: Settings | None = None,
) -> tuple[GroqInsightsResponse, dict[str, Any]]:
    """Call Groq and return (grounded response, meta).

    Raises GroqError on API / parse failure after one retry.
    """
    settings = settings or get_settings()
    if not settings.groq_api_key:
        raise GroqError("GROQ_API_KEY is not set")

    try:
        from groq import Groq
    except ImportError as e:
        raise GroqError("groq package not installed") from e

    client = Groq(api_key=settings.groq_api_key)
    pack_json = json.dumps(pack, separators=(",", ":"))
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt(pack_json)},
    ]

    # Groq TPM counts prompt + max_tokens; keep completion budget modest on free tier
    max_out = min(int(settings.groq_max_tokens or 4096), 2048)

    last_err: Exception | None = None
    raw_text = ""
    for attempt in range(2):
        try:
            completion = client.chat.completions.create(
                model=settings.groq_model,
                messages=messages,
                temperature=settings.groq_temperature,
                max_tokens=max_out,
                response_format={"type": "json_object"},
            )
            raw_text = completion.choices[0].message.content or ""
            data = _extract_json(raw_text)
            parsed = GroqInsightsResponse.model_validate(data)
            grounded, drops = ground_insights(parsed, pack)
            meta = {
                "model": settings.groq_model,
                "prompt_version": PROMPT_VERSION,
                "raw_response": raw_text,
                "drops": drops,
                "schema": response_json_schema(),
            }
            return grounded, meta
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning("Groq attempt %s failed: %s", attempt + 1, e)

    raise GroqError(f"Groq failed after retry: {last_err}")
