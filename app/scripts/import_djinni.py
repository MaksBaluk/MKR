"""Import public Djinni vacancies into fixtures/vacancies_real.json (REAL_IMPORTED, with source URL and retrieval date).

Only with the explicit --confirm-permission flag (the project forbids scraping without the site's permission; the
operator states they have it). Polite: robots.txt is checked, one request per --delay seconds, stop on HTTP 403/429.
Only structured fields and short verbatim requirement excerpts are stored (no full posting text, no contacts).
Run from app/:  uv run python scripts/import_djinni.py --confirm-permission --track python --limit 30"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.domain.vacancy_import import IMPORT_VERSION, build_record, compose_texts, validate_record  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
UA = "CompetenceMatchResearchImport/1.0 (permission-based, low rate)"
BASE = "https://djinni.co"
KEYWORDS = {"python": ["Python"], "marketing": ["Marketing"], "design": ["Design", "UI/UX Design"]}


class Stop(Exception):
    pass


def get(url: str, delay: float) -> str:
    time.sleep(delay)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise Stop(f"HTTP {exc.code} from {url}: stopping, the site asks to slow down or refuses") from exc
        raise


def posting_of(html: str) -> dict | None:
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    try:
        d = json.loads(m.group(1)) if m else None
    except json.JSONDecodeError:
        return None
    return d if isinstance(d, dict) and d.get("@type") == "JobPosting" else None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--confirm-permission", action="store_true", help="operator confirms Djinni permitted this collection")
    p.add_argument("--track", choices=sorted(KEYWORDS), required=True)
    p.add_argument("--limit", type=int, default=30, help="accepted records to collect for the track")
    p.add_argument("--max-pages", type=int, default=6)
    p.add_argument("--delay", type=float, default=2.0)
    p.add_argument("--out", type=Path, default=FIXTURES / "vacancies_real.json")
    a = p.parse_args(argv)
    if not a.confirm_permission:
        print("error: refusing to fetch without --confirm-permission (project rule: no scraping without permission)", file=sys.stderr)
        return 2
    rp = urllib.robotparser.RobotFileParser(BASE + "/robots.txt")
    rp.parse(get(BASE + "/robots.txt", 0).splitlines())
    comps = [c["id"] for c in json.loads((FIXTURES / "competencies.json").read_text("utf-8")) if c["track"] == a.track]
    names = {c["id"]: c["label_uk"] for c in json.loads((FIXTURES / "competencies.json").read_text("utf-8"))}
    existing = json.loads(a.out.read_text("utf-8")) if a.out.exists() else []
    have = {r["id"] for r in existing}
    today = date.today().isoformat()
    report = {"import_version": IMPORT_VERSION, "track": a.track, "date": today, "listed": 0, "fetched": 0, "accepted": 0,
              "duplicates": 0, "rejected": {}, "http_errors": 0}
    new: list[dict] = []
    urls: list[str] = []
    try:
        for kw in KEYWORDS[a.track]:
            for page in range(1, a.max_pages + 1):
                if len(urls) >= a.limit * 3:
                    break
                lst = f"{BASE}/jobs/?primary_keyword={urllib.parse.quote(kw)}&page={page}"
                if not rp.can_fetch(UA, lst):
                    print("robots.txt disallows", lst); break
                found = list(dict.fromkeys(re.findall(r'href="(/jobs/\d[^"]*)"', get(lst, a.delay))))
                report["listed"] += len(found)
                urls += [BASE + f for f in found if BASE + f not in urls]
                if not found:
                    break
        for url in urls:
            if len([r for r in new if r["track"] == a.track]) >= a.limit:
                break
            if not rp.can_fetch(UA, url):
                continue
            try:
                post = posting_of(get(url, a.delay))
            except (urllib.error.URLError, TimeoutError):
                report["http_errors"] += 1
                continue
            report["fetched"] += 1
            rec = build_record(post, a.track, comps, today) if post else None
            if rec is None:
                report["rejected"]["not a usable JobPosting"] = report["rejected"].get("not a usable JobPosting", 0) + 1
                continue
            if rec["id"] in have or any(r["id"] == rec["id"] for r in new):
                report["duplicates"] += 1
                continue
            errs = validate_record(rec, comps)
            if errs:
                for e in errs:
                    report["rejected"][e] = report["rejected"].get(e, 0) + 1
                continue
            rec["summary"], rec["description"] = compose_texts(rec, names)
            new.append(rec)
            report["accepted"] += 1
    except Stop as exc:
        print("STOP:", exc, file=sys.stderr)
        report["stopped"] = str(exc)
    a.out.write_text(json.dumps(existing + new, ensure_ascii=False, indent=2) + "\n", "utf-8")
    rep_path = FIXTURES / "vacancies_real_import_report.json"
    reports = json.loads(rep_path.read_text("utf-8")) if rep_path.exists() else []
    rep_path.write_text(json.dumps(reports + [report], ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 1 if "stopped" in report else 0


if __name__ == "__main__":
    raise SystemExit(main())
