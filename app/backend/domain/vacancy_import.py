"""Pure parser: one public vacancy posting (schema.org JobPosting fields) -> a catalog record with requirement groups.

Deterministic and offline. Competency matching is a curated alias table (no ESCO, no model). Every requirement group keeps
the verbatim source line as `excerpt` and the record keeps `source_url`/`retrieved_at`. Levels and criterion subsets are
rule-derived working assumptions (`level_source`, `criteria_source`), never employer statements."""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

IMPORT_VERSION = "djinni-import-v1"
LEVEL_SOURCE = "SENIORITY_RULE_V1"  # postings state no per-skill level: base level from seniority, desired = base-1 (min 1)
SOURCE_TYPE = "REAL_IMPORTED"

A = {  # competency id -> alias regex (case-insensitive); curated, track-specific
    "python-core": r"\bpython\b", "fastapi": r"fast\s?api", "django": r"\bdjango\b|\bdrf\b",
    "postgresql": r"postgres(ql)?|\bpsql\b", "sql": r"\bsql\b|mysql", "sqlalchemy": r"sqlalchemy|alembic",
    "docker": r"docker|containeri[sz]", "aws": r"\baws\b|amazon web|\bec2\b|\bs3\b", "redis": r"\bredis\b",
    "celery": r"celery|rabbitmq|task queues?", "pytest": r"pytest|unit[ -]?tests?|integration tests?|unit and integration|\btdd\b",
    "git": r"\bgit\b|github|gitlab|bitbucket|version control", "ci-cd": r"ci\s?/\s?cd|\bci\b|continuous integration|jenkins|github actions|gitlab ci",
    "rest-api": r"\brest(ful)?\b|openapi|swagger", "async-python": r"asyncio|\basync\b|aiohttp|multithread|concurren",
    "linux": r"linux|unix|\bbash\b", "kubernetes": r"kubernetes|\bk8s\b|\bhelm\b", "app-security": r"security|owasp|oauth|\bjwt\b|vulnerab",
    "observability": r"observab|monitoring|prometheus|grafana|sentry|datadog|opentelemetry", "kafka": r"kafka|message brokers?|event[- ]driven",
    "ga4": r"google analytics|\bga4\b|web analytics", "google-ads": r"google ads|adwords|\bppc\b|\bsem\b", "meta-ads": r"meta ads|facebook ads|instagram ads|\bfb ads\b|paid social|tiktok ads",
    "seo": r"\bseo\b|search engine optim|keyword research|semrush|ahrefs", "content-strategy": r"content (strategy|plan|marketing|calendar)|editorial",
    "email-marketing": r"e-?mail marketing|e-?mail campaigns?|newsletters?|mailchimp|klaviyo", "crm": r"\bcrm\b|hubspot|salesforce|pipedrive",
    "segmentation": r"segmentation|\bpersonas?\b|audience", "cro": r"\bcro\b|conversion (rate )?optimi[sz]ation|landing pages?",
    "ab-testing": r"a\s?/\s?b[- ]test|split[- ]test|experimentation", "gtm": r"tag manager|\bgtm\b|\bpixels?\b",
    "looker-studio": r"looker|data studio|power bi|tableau|dashboards?", "excel": r"\bexcel\b|google sheets|spreadsheets?",
    "copywriting": r"copywrit|ad copy", "brand-strategy": r"brand (strategy|positioning|awareness)|positioning",
    "performance-marketing": r"performance marketing|paid (media|campaigns?|advertising|acquisition)|\broas\b|\bcac\b|user acquisition|media buying",
    "attribution": r"attribution|appsflyer|\bmmp\b|\butm\b", "marketing-automation": r"marketing automation|zapier|lifecycle",
    "social-media": r"social media|\bsmm\b|community management", "market-research": r"market research|competitor|competitive analysis|customer research",
    "figma": r"\bfigma\b|sketch app|adobe xd|invision", "ui-design": r"\bui\b|user interface|interface design",
    "ux-research": r"\bux research|user research|user interviews?|\bjtbd\b", "wireframing": r"wireframe|low-?fidelity|user flows?",
    "prototyping": r"prototyp", "design-systems": r"design systems?|ui kit|component librar|design tokens",
    "accessibility": r"accessib|\bwcag\b|\ba11y\b", "typography": r"typograph|typeface", "visual-design": r"visual design|graphic design|visual language",
    "illustrator": r"illustrator|vector graphics", "photoshop": r"photoshop|retouch", "usability-testing": r"usability|user testing",
    "interaction-design": r"interaction design|micro-?interactions?", "responsive-design": r"responsive|mobile[- ]first|adaptive design",
    "html-css": r"\bhtml\b|\bcss\b", "information-architecture": r"information architecture|taxonom", "stakeholder-communication": r"stakeholders?|cross-?functional",
    "motion-design": r"motion design|after effects|lottie|\bmotion\b", "branding": r"branding|brand identity|brand guidelines|\blogo\b",
    "product-analytics": r"product analytics|amplitude|mixpanel|hotjar|heatmaps?",
}
ALIAS = {k: re.compile(v, re.I) for k, v in A.items()}
DESIRED_RE = re.compile(r"nice[- ]to[- ]have|\bplus\b|bonus|desired|advantage|preferred|good to have|would be a", re.I)
REQUIRED_RE = re.compile(r"requirements?|skills|must[- ]have|qualifications|what we expect|we(?:'|’)?re looking for|we are looking for|your profile|you have|experience|matters|you bring|bring to|who you are|ideal candidate|you need|should have|required|your background|tech(?:nical)? stack|proficien|competenc|about you", re.I)
IGNORE_RE = re.compile(r"responsibilit|what you(?:'|’)?ll do|duties|tasks|we offer|benefits|perks|conditions|about|who we are|company|our team|why join|offer", re.I)
OR_RE = re.compile(r"\b(or|чи|або)\b|/", re.I)


def seniority_of(title: str, months: float | None) -> str:
    t = title.lower()
    for key, name in (("lead", "LEAD"), ("principal", "LEAD"), ("head", "LEAD"), ("senior", "SENIOR"), ("sr.", "SENIOR"),
                      ("middle", "MIDDLE"), ("mid-level", "MIDDLE"), ("junior", "JUNIOR"), ("trainee", "JUNIOR"), ("intern", "JUNIOR")):
        if key in t:
            return name
    y = (months or 0) / 12
    return "JUNIOR" if y < 2 else "MIDDLE" if y < 4 else "SENIOR"


def level_for(seniority: str, desired: bool) -> int:
    base = {"JUNIOR": 1, "MIDDLE": 2, "SENIOR": 3, "LEAD": 3}[seniority]
    return max(1, base - 1) if desired else base


def match(line: str, track_competencies: Sequence[str]) -> list[str]:
    return [c for c in track_competencies if ALIAS[c].search(line)]


def sections(description: str) -> list[tuple[str, str, bool]]:
    """(kind, line, desired) for every non-empty line; kind is REQ, IGNORE. A header line (short, ends with ':' or is a known
    heading) switches the mode; bullet text keeps the mode. Default mode before any header: IGNORE (company intro)."""
    mode, desired, out = "IGNORE", False, []
    for raw in description.replace("\xa0", " ").splitlines():
        line = raw.strip(" \t•·-–*►▪↳→✓✔●○■□◦‣⁃")
        if not line:
            continue
        header = len(line) <= 70 and (line.endswith(":") or line.isupper())
        if header:
            if DESIRED_RE.search(line):
                mode, desired = "REQ", True
            elif IGNORE_RE.search(line) and not REQUIRED_RE.search(line):
                mode, desired = "IGNORE", False
            elif REQUIRED_RE.search(line):
                mode, desired = "REQ", False
            continue
        out.append((mode, line, desired or bool(DESIRED_RE.search(line)) and mode == "REQ"))
    return out


def build_groups(description: str, track_competencies: Sequence[str], seniority: str) -> list[dict]:
    groups, seen = [], set()
    for mode, line, desired in sections(description):
        if mode != "REQ":
            continue
        found = match(line, track_competencies)
        if not found:
            continue
        excerpt = line[:300]
        units = [found] if len(found) > 1 and OR_RE.search(line) else [[c] for c in found]
        for alts in units:
            key = (tuple(alts), desired)
            if key in seen or any((tuple(alts), d) in seen for d in (False,)) and desired:
                continue
            seen.add(key)
            groups.append({"kind": "DESIRED" if desired else "MANDATORY", "excerpt": excerpt,
                           "alternatives": [{"competency_id": c, "required_level": level_for(seniority, desired),
                                             "normalization_status": "ACCEPTED_ALIAS_V1"} for c in alts]})
    return groups


def _num(x: Any) -> int | None:
    return int(x) if isinstance(x, (int, float)) else None


def build_record(posting: Mapping[str, Any], track: str, track_competencies: Sequence[str], retrieved_at: str) -> dict | None:
    """Catalog record or None when the posting is not usable. Raises nothing for malformed input: returns None."""
    try:
        url = str(posting["url"])
        title = str(posting["title"]).strip()
        company = str((posting.get("hiringOrganization") or {}).get("name") or "").strip()
        desc = str(posting.get("description") or "")
        pid = str(posting.get("identifier") or url.rstrip("/").split("/")[-1].split("-")[0])
    except (KeyError, TypeError, AttributeError):
        return None
    if not (url.startswith("https://djinni.co/jobs/") and title and company and desc):
        return None
    months = (posting.get("experienceRequirements") or {}).get("monthsOfExperience") if isinstance(posting.get("experienceRequirements"), dict) else None
    seniority = seniority_of(title, months)
    groups = build_groups(desc, track_competencies, seniority)
    sal = (posting.get("baseSalary") or {}).get("value") if isinstance(posting.get("baseSalary"), dict) else None
    sal = sal if isinstance(sal, dict) else {}
    remote = posting.get("jobLocationType") == "TELECOMMUTE"
    region = ((posting.get("applicantLocationRequirements") or {}).get("address") or {}) if isinstance(posting.get("applicantLocationRequirements"), dict) else {}
    years = int(round(months / 12)) if isinstance(months, (int, float)) else {"JUNIOR": 1, "MIDDLE": 3, "SENIOR": 5, "LEAD": 6}[seniority]
    stack = sorted({c for g in groups for a in g["alternatives"] for c in [a["competency_id"]]})
    return {
        "id": f"djinni-{track}-{pid}", "track": track, "title": title[:200], "company": company[:160], "seniority": seniority,
        "years_min": years, "years_max": None, "location": str(region.get("addressRegion") or region.get("addressLocality") or "Ukraine")[:90],
        "work_mode": "REMOTE" if remote else "OFFICE", "employment": "Full-time",
        "salary_min": _num(sal.get("minValue")), "salary_max": _num(sal.get("maxValue")), "currency": str((posting.get("baseSalary") or {}).get("currency") or "USD")[:6] if isinstance(posting.get("baseSalary"), dict) else "USD",
        "summary": " ".join(desc.split())[:280],
        "description": "Витяг вимог із джерела (не повний текст): " + " | ".join(dict.fromkeys(g["excerpt"] for g in groups))[:3000],
        "responsibilities": [], "benefits": [], "stack": stack,
        "source_type": SOURCE_TYPE, "source_url": url, "retrieved_at": retrieved_at, "date_posted": str(posting.get("datePosted") or "")[:10],
        "import_version": IMPORT_VERSION, "level_source": LEVEL_SOURCE, "fixture_version": "fixtures-real-v1",
        "groups": [{"id": f"djinni-{track}-{pid}-g{i + 1:02d}", "kind": g["kind"], "label": g["excerpt"][:200], "excerpt": g["excerpt"],
                    "alternatives": g["alternatives"]} for i, g in enumerate(groups)],
    }


MODE_UK = {"REMOTE": "віддалено", "OFFICE": "офіс або не вказано"}
SENIORITY_UK = {"JUNIOR": "Junior", "MIDDLE": "Middle", "SENIOR": "Senior", "LEAD": "Lead"}


def compose_texts(rec: Mapping[str, Any], names: Mapping[str, str]) -> tuple[str, str]:
    """(summary, description) in Ukrainian built only from the record's own fields and requirement excerpts: no invented
    facts. `names` maps competency id -> Ukrainian label. Verbatim source excerpts stay in the groups, not here."""
    def label(g):
        return " / ".join(names.get(a["competency_id"], a["competency_id"]) for a in g["alternatives"])
    must = list(dict.fromkeys(label(g) for g in rec["groups"] if g["kind"] == "MANDATORY"))
    nice = list(dict.fromkeys(label(g) for g in rec["groups"] if g["kind"] != "MANDATORY"))
    pay = ""
    if rec.get("salary_min") and rec.get("salary_max"):
        pay = f" Вилка зарплати в оголошенні: {rec['salary_min']}–{rec['salary_max']} {rec.get('currency') or 'USD'} на місяць."
    head = (f"{rec['title']} у компанії {rec['company']}. Рівень: {SENIORITY_UK.get(rec['seniority'], rec['seniority'])}, "
            f"формат: {MODE_UK.get(rec['work_mode'], rec['work_mode'])}, регіон: {rec['location']}. "
            f"Мінімальний досвід за оголошенням: {rec['years_min']} р.{pay}")
    lines = [head]
    if must:
        lines.append("Обов'язкові вимоги: " + "; ".join(must) + ".")
    if nice:
        lines.append("Буде перевагою: " + "; ".join(nice) + ".")
    lines.append(f"Джерело: публічне оголошення на Djinni ({rec['source_url']}), отримано {rec['retrieved_at']}. "
                 "Це короткий опис, складений із вимог оголошення; повний текст і актуальність дивіться на сторінці джерела.")
    summary = (head + (" Ключове: " + ", ".join(must[:4]) + "." if must else ""))[:280]
    return summary, "\n\n".join(lines)


def validate_record(rec: Mapping[str, Any], track_competencies: Sequence[str]) -> list[str]:
    """Reasons a record must not enter the catalog; empty = accepted."""
    errors = []
    gs = rec.get("groups") or []
    if len(gs) < 3:
        errors.append("fewer than 3 requirement groups")
    if sum(g["kind"] == "MANDATORY" for g in gs) < 2:
        errors.append("fewer than 2 mandatory groups")
    if len({a["competency_id"] for g in gs for a in g["alternatives"]}) < 3:
        errors.append("fewer than 3 distinct competencies")
    if any(a["competency_id"] not in track_competencies for g in gs for a in g["alternatives"]):
        errors.append("competency outside the track")
    if not all(g.get("excerpt") for g in gs):
        errors.append("group without source excerpt")
    for field in ("source_url", "retrieved_at", "title", "company"):
        if not rec.get(field):
            errors.append(f"missing {field}")
    return errors
