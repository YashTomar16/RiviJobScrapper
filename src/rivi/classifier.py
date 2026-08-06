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
    "IT",
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


def _strip_executive_org_units(t: str) -> str:
    """Remove 'CIO Office' / 'Office of the CTO' style org units.

    These mention an executive's office without meaning the person is C-level.
    Example: 'Quantitative Analyst - CIO Office' must not classify as C-level.
    """
    t = re.sub(
        r"\boffice\s+of\s+the\s+"
        r"(?:chief\s+(?:technology|product|data|information|ai)\s+officer|cio|cto|cpo|cdo)\b",
        " ",
        t,
        flags=re.I,
    )
    t = re.sub(r"\b(?:cio|cto|cpo|cdo)\s+office\b", " ", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


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
    (r"\b(data scientist|data science|data engineer|data engineering|analytics engineer|business intelligence|bi engineer|data analyst|quantitative analyst|quant analyst)\b", "Data"),
    (r"\b(software engineer|software engineering|swe\b|backend|front[- ]?end|full[- ]?stack|site reliability|sre\b|devops|platform engineer|platform management|infrastructure engineer|security engineer|cloud engineer|mobile engineer|ios|android|qa engineer|test engineer|quality engineer|systems engineer|desktop engineering|application support|quantitative developer|quant developer)\b", "Engineering"),
    (r"\b(engineering manager|director of engineering|vp engineering|head of engineering|cto|chief technology)\b", "Engineering"),
    (r"\b(product manager|product owner|product lead|product management|head of product|director of product|vp product|chief product|cpo|group product design|product design manager)\b", "Product"),
    # IT before broader Technology so "IT Manager" / "CIO" land in IT.
    (r"\b(\bit\b|information technology|it architect|it manager|it director|it operations|it support|it infrastructure|chief information|\bcio\b|crm technology)\b", "IT"),
    (r"\b(technologist|technology|solutions architect|solutions architecture|enterprise architect|technical architect)\b", "Technology"),
    (r"\b(engineer|developer|programmer|architect)\b", "Engineering"),
    (r"\b(research scientist|applied scientist)\b", "AI"),
]

# Titles that look eng-ish but are sales — exclude if matched after function
SALES_ENGINEER_RE = re.compile(r"\b(sales engineer|pre[- ]?sales|solutions consultant|customer engineer)\b", re.I)

SENIORITY_PATTERNS: list[tuple[str, str]] = [
    (r"\b(chief technology officer|chief product officer|chief ai officer|chief data officer|chief information officer)\b", "C-level"),
    # Standalone CxO titles only — not "CIO Office" / "Office of the CIO" (stripped above).
    (r"(?:^|[,/\s])(cto|cpo|cdo|cio)(?:$|[,/\s])", "C-level"),
    (r"\b(senior vice president|\bsvp\b)\b", "SVP"),
    (r"\b(vice president|\bvp\b|svp)\b", "VP"),
    (r"\b(senior director|sr\.?\s*director)\b", "Senior Director"),
    (r"\b(\bdirector\b)\b", "Director"),
    (r"\b(\bhead of\b|\bhead,\b)\b", "Head"),
    (r"\b(senior manager|sr\.?\s*manager)\b", "Senior Manager"),
    (r"\b(\bmanager\b|engineering manager|product manager)\b", "Manager"),
]


# Clear non-USA/EU geo signals — used when location text is present.
_OUTSIDE_USA_EU_RE = re.compile(
    r"\b("
    r"india|mumbai|bangalore|bengaluru|hyderabad|chennai|pune|delhi|gurgaon|gurugram|"
    r"singapore|hong\s*kong|japan|tokyo|osaka|korea|seoul|china|shanghai|beijing|"
    r"taiwan|taipei|philippines|manila|indonesia|jakarta|malaysia|kuala\s*lumpur|"
    r"thailand|bangkok|vietnam|australia|sydney|melbourne|new\s*zealand|"
    r"brazil|sao\s*paulo|mexico|canada|toronto|vancouver|montreal|"
    r"israel|tel\s*aviv|uae|dubai|saudi|africa|nigeria|south\s*africa|"
    r"argentina|chile|colombia|peru"
    r")\b",
    re.I,
)

_USA_EU_RE = re.compile(
    r"\b("
    r"united\s*states|\busa\b|\bu\.s\.a\.?\b|\bu\.s\.?\b|"
    r"new\s*york|nyc|boston|chicago|san\s*francisco|sf\b|seattle|austin|"
    r"dallas|houston|los\s*angeles|\bla\b|miami|atlanta|denver|philadelphia|"
    r"washington|dc\b|virginia|connecticut|hartford|new\s*jersey|massachusetts|"
    r"california|texas|florida|illinois|colorado|north\s*carolina|charlotte|"
    r"remote\s*[-–—]?\s*us|us\s*remote|united\s*kingdom|\buk\b|london|england|"
    r"scotland|wales|ireland|dublin|europe|\beu\b|"
    r"germany|berlin|frankfurt|munich|france|paris|netherlands|amsterdam|"
    r"switzerland|zurich|geneva|spain|madrid|italy|milan|rome|"
    r"sweden|stockholm|norway|oslo|denmark|copenhagen|finland|helsinki|"
    r"belgium|brussels|austria|vienna|portugal|lisbon|poland|warsaw|"
    r"luxembourg|czech|prague|hungary|budapest|romania|greece|athens"
    r")\b",
    re.I,
)


def location_in_usa_or_eu(location: str | None) -> bool:
    """Return True if location is USA/EU, unknown/empty, or remote without APAC signal.

    Explicit non-USA/EU locations (India, Singapore, etc.) return False.
    Empty location is kept (boards often omit geo).
    """
    loc = (location or "").strip()
    if not loc:
        return True
    low = loc.lower()
    if re.search(r"\b(worldwide|global|multiple\s+locations|various)\b", low):
        # Prefer keep when USA/EU also mentioned; else drop vague global-only
        if _USA_EU_RE.search(low):
            return True
        if _OUTSIDE_USA_EU_RE.search(low):
            return False
        return True
    has_us_eu = bool(_USA_EU_RE.search(low))
    has_outside = bool(_OUTSIDE_USA_EU_RE.search(low))
    if has_us_eu:
        return True
    if has_outside:
        return False
    # Unrecognized location text — keep (don't over-filter)
    return True


def classify_title(title: str, location: str | None = None) -> Classification:
    raw = title or ""
    t = _strip_executive_org_units(_norm(raw))
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

    if not location_in_usa_or_eu(location):
        evidence.append("exclude:geo_outside_usa_eu")
        return Classification(
            function=function,
            seniority_band=seniority,
            in_scope=False,
            match_evidence=";".join(evidence),
        )

    return Classification(
        function=function,
        seniority_band=seniority,
        in_scope=True,
        match_evidence=";".join(evidence) if evidence else "matched",
    )
