from __future__ import annotations

import re
from dataclasses import dataclass


SENIORITY_ORDER = [
    "C-level",
    "SVP",
    "VP",
    "Senior Director",
    "Director",
    "Head",
    "Senior Manager",
    "Manager",
    "IC",
]

IN_SCOPE_FUNCTIONS = (
    "Technology",
    "Product",
    "Engineering",
    "Data",
    "AI",
    "Machine Learning",
)


@dataclass
class Classification:
    function: str
    seniority_band: str
    in_scope: bool
    match_evidence: str


def _norm(title: str) -> str:
    t = title.lower()
    t = t.replace("&", " and ")
    t = re.sub(r"[^a-z0-9+.#/\s-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


# Hard exclusions — checked before inclusions
EXCLUDE_PATTERNS: list[tuple[str, str]] = [
    (r"\b(sales|account executive|business development|bdm|sdr|ae)\b", "Sales"),
    (r"\b(marketing|brand|communications|pr |public relations|growth marketing)\b", "Marketing"),
    (r"\b(product marketing)\b", "Marketing"),
    (r"\b(human resources|\bhr\b|recruiter|recruiting|people partner|talent acquisition)\b", "HR"),
    (r"\b(legal|counsel|attorney|compliance officer|paralegal)\b", "Legal"),
    (r"\b(office manager|facilities|administrative assistant|executive assistant)\b", "Operations"),
    (r"\b(operations manager|chief operating|coo)\b", "Operations"),
    (r"\b(director of operations|head of operations|vp of operations|vp operations)\b", "Operations"),
    (r"\b(chief financial|cfo|controller|accountant|accounts payable|bookkeeper)\b", "Finance"),
    (r"\b(ceo|chief executive|chro|chief people|chief legal|clo|chief marketing|cmo)\b", "OutOfScopeCLevel"),
]

# Inclusion signals (function)
FUNCTION_PATTERNS: list[tuple[str, str]] = [
    (r"\b(machine learning|ml engineer|ml scientist|deep learning)\b", "Machine Learning"),
    (r"\b(\bai\b|artificial intelligence|genai|generative ai|llm)\b", "AI"),
    (r"\b(data scientist|data science|data engineer|data engineering|analytics engineer|business intelligence|bi engineer|data analyst)\b", "Data"),
    (r"\b(software engineer|swe\b|backend|front[- ]?end|full[- ]?stack|site reliability|sre\b|devops|platform engineer|infrastructure engineer|security engineer|cloud engineer|mobile engineer|ios|android|qa engineer|test engineer|quality engineer)\b", "Engineering"),
    (r"\b(engineering manager|director of engineering|vp engineering|head of engineering|cto|chief technology)\b", "Engineering"),
    (r"\b(product manager|product owner|product lead|head of product|director of product|vp product|chief product|cpo)\b", "Product"),
    (r"\b(technologist|technology|\bit\b|information technology|it architect|it manager|it director|solutions architect|enterprise architect|technical architect|chief information|cio)\b", "Technology"),
    (r"\b(engineer|developer|programmer|architect)\b", "Engineering"),
    (r"\b(research scientist|applied scientist)\b", "AI"),
]

# Titles that look eng-ish but are sales — exclude if matched after function
SALES_ENGINEER_RE = re.compile(r"\b(sales engineer|pre[- ]?sales|solutions consultant|customer engineer)\b", re.I)

SENIORITY_PATTERNS: list[tuple[str, str]] = [
    (r"\b(chief technology officer|\bcto\b|chief product officer|\bcpo\b|chief ai officer|chief data officer|\bcdo\b|chief information officer|\bcio\b)\b", "C-level"),
    (r"\b(senior vice president|\bsvp\b)\b", "SVP"),
    (r"\b(vice president|\bvp\b|svp)\b", "VP"),
    (r"\b(senior director|sr\.?\s*director)\b", "Senior Director"),
    (r"\b(\bdirector\b)\b", "Director"),
    (r"\b(\bhead of\b|\bhead,\b)\b", "Head"),
    (r"\b(senior manager|sr\.?\s*manager)\b", "Senior Manager"),
    (r"\b(\bmanager\b|engineering manager|product manager)\b", "Manager"),
]


def classify_title(title: str) -> Classification:
    raw = title or ""
    t = _norm(raw)
    evidence: list[str] = []

    if not t:
        return Classification("", "", False, "empty_title")

    if SALES_ENGINEER_RE.search(t):
        return Classification("", "", False, "exclude:SalesEngineer")

    for pattern, label in EXCLUDE_PATTERNS:
        if re.search(pattern, t, flags=re.I):
            # Allow quant/tech finance engineering through later if strong eng signal —
            # but hard-exclude clear non-tech ops/hr/legal/sales/marketing.
            if label == "Finance" and re.search(
                r"\b(software|engineer|developer|data scientist|machine learning|ml |ai )\b", t
            ):
                evidence.append(f"finance_override_candidate:{label}")
                break
            return Classification("", "", False, f"exclude:{label}")

    function = ""
    for pattern, label in FUNCTION_PATTERNS:
        if re.search(pattern, t, flags=re.I):
            function = label
            evidence.append(f"function:{label}")
            break

    if not function:
        return Classification("", "", False, "no_function_match")

    seniority = "IC"
    for pattern, band in SENIORITY_PATTERNS:
        if re.search(pattern, t, flags=re.I):
            # Product Manager should stay Manager band, not get overridden oddly
            seniority = band
            evidence.append(f"seniority:{band}")
            break

    # IC refinement: principal/staff/distinguished stay IC
    if re.search(r"\b(principal|staff|distinguished|fellow|senior|sr\.?)\b", t) and seniority == "IC":
        evidence.append("seniority:IC_senior")

    # "Product Manager" matched Manager — correct
    # "Engineering Manager" matched Manager — correct
    # Avoid classifying "manager" in "account manager" — already excluded via Sales

    return Classification(
        function=function,
        seniority_band=seniority,
        in_scope=True,
        match_evidence=";".join(evidence) if evidence else "matched",
    )
