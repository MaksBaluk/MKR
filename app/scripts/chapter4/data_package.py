"""Chapter-4 data package (owner protocol v2, artifacts/chapter4/data/): vacancy dataset export + audit, 18 pilot
candidate profiles (inputs separate from hidden scenario definitions), null competency references, the response bank of
simulated answers, and empty annotation files with annotator inputs. Nothing here is annotated: references and
annotation rows stay empty until independent annotators fill them (LLM_ANNOTATOR_PILOT or human experts).

Run from app/ (after modes_experiment, because the response bank and the vacancy pools read its runs):
    uv run python -m scripts.chapter4.data_package
The fixed vacancy pool is frozen once any annotation row exists (it is then read back, never regenerated).
"""
from __future__ import annotations

import collections
import csv
import hashlib
import json
from pathlib import Path

from backend.domain.core_flow import TAU_BY_LEVEL, TAU_SOURCE_LEVEL_MAP
from backend.domain.seniority_policy import PRACTICE_CRITERIA
from scripts.chapter4.candidate_model import CRITERIA, PROFILES, TRACK_ACTIONS, oracle_level
from scripts.chapter4.common import APP, OUT, write_csv, write_json
from scripts.chapter4.modes_experiment import PER_Q, load_runs
from scripts.chapter4.research_planner import VERSION as RESEARCH_VERSION
from scripts.seniority_realistic import PHRASES, quant

DATA = OUT / "data"
FX = APP / "fixtures"
SOURCE_TYPE = {"REAL_IMPORTED": "REAL", "DEMO_CURATED": "CURATED", "SYNTHETIC_GENERATED": "SYNTHETIC"}
SIMULATOR = "scripts.seniority_realistic.Candidate via scripts.chapter4.candidate_model (template answers)"
ANNOTATION_FILES = {
    "expert_criterion_annotations.csv": ["candidate_id", "criterion_id", "question_id", "annotator_id", "score",
                                         "evidence_status", "rubric_version", "comment"],
    "expert_vacancy_relevance.csv": ["candidate_id", "vacancy_id", "annotator_id", "relevance", "rationale",
                                     "scale_version"],
    "expert_seniority.csv": ["candidate_id", "annotator_id", "level", "rationale", "evidence_refs"],
}
POOL_RANDOM = 10  # stratified random vacancies per candidate added to the pooled Top-10s


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _h(*parts) -> str:
    return hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()


def vacancies() -> tuple[list[dict], dict]:
    vac = json.loads((FX / "vacancies.json").read_text(encoding="utf-8"))
    real = json.loads((FX / "vacancies_real.json").read_text(encoding="utf-8"))
    sources = json.loads((FX / "vacancy_sources.json").read_text(encoding="utf-8"))
    dvga = json.loads((FX / "vacancy_criteria.json").read_text(encoding="utf-8"))
    return vac + real, {"sources": sources, "dvga": dvga}


def build_vacancies(version: str) -> dict:
    allv, extra = vacancies()
    labels, dvga = extra["sources"]["by_vacancy"], extra["dvga"]["requirements"]
    rows, reqs = [], []
    for v in allv:
        st = SOURCE_TYPE.get(v["source_type"], v["source_type"])
        groups = v["groups"]
        rows.append({
            "vacancy_id": v["id"], "profession": v["track"], "seniority_label": v["seniority"],
            "required_years": v["years_min"], "source_type": st,
            "source_reference": v.get("source_url") if st == "REAL" else
            f"repository fixture {v.get('fixture_version')} (no external source)",
            "repo_display_source_name": labels.get(v["id"], ""),
            "provenance_flag": "" if st == "REAL" else ("DISPLAY_LABEL_NAMES_A_SITE_ON_NON_REAL_FIXTURE"
                                                       if labels.get(v["id"]) else ""),
            "requirement_group_count": len(groups),
            "mandatory_group_count": sum(g["kind"] == "MANDATORY" for g in groups),
            "preferred_group_count": sum(g["kind"] == "DESIRED" for g in groups),
            "or_group_count": sum(len(g["alternatives"]) > 1 for g in groups),
            "retrieved_at": v.get("retrieved_at") or "", "dataset_version": version})
        for g in groups:
            for i, a in enumerate(g["alternatives"], 1):
                aid = f"{g['id']}-a{i}"
                ids = dvga.get(aid)
                tau = TAU_BY_LEVEL.get(a["required_level"])
                reqs.append({
                    "vacancy_id": v["id"], "group_id": g["id"], "alternative_id": aid,
                    "group_logic": "OR" if len(g["alternatives"]) > 1 else "SINGLE",
                    "between_groups": "AND", "importance": g["kind"], "competency_id": a["competency_id"],
                    "required_level": a["required_level"], "criterion_ids": ids,
                    "criterion_ids_source": extra["dvga"]["criteria_source"] if ids is not None else None,
                    "criterion_ids_status": "DERIVED_SYNTHETIC_RULE" if ids is not None else "MISSING",
                    "threshold_tau": tau, "threshold_status": TAU_SOURCE_LEVEL_MAP if tau is not None else "UNKNOWN",
                    "normalization_status": a["normalization_status"], "source_type": SOURCE_TYPE.get(v["source_type"]),
                    "source_excerpt": g["excerpt"], "dataset_version": version})
    write_csv(DATA / "vacancies.csv", list(rows[0]), rows)
    with open(DATA / "vacancy_requirements.jsonl", "w", encoding="utf-8") as f:
        for r in reqs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"rows": rows, "reqs": reqs, "allv": allv, "extra": extra}


def audit(pkg: dict, version: str, files: dict) -> str:
    rows, reqs, allv, extra = pkg["rows"], pkg["reqs"], pkg["allv"], pkg["extra"]
    rub = json.loads((FX / "rubrics.json").read_text(encoding="utf-8"))["rubrics"]
    rub_crit = {r["action_id"]: {c["criterion_id"] for c in r["criteria"]} for r in rub}
    comps = {c["id"] for c in json.loads((FX / "competencies.json").read_text(encoding="utf-8"))}
    ids = [r["vacancy_id"] for r in rows]
    dup_ids = [k for k, n in collections.Counter(ids).items() if n > 1]
    desc = collections.Counter(hashlib.sha256(v["description"].encode()).hexdigest() for v in allv)
    title_co = collections.Counter((v["title"], v["company"]) for v in allv)
    by = collections.Counter((r["profession"], r["source_type"]) for r in rows)
    unknown_comp = sorted({r["competency_id"] for r in reqs} - comps)
    no_rubric = sorted({r["competency_id"] for r in reqs} - set(rub_crit))
    bad_crit = [(r["alternative_id"], c) for r in reqs for c in (r["criterion_ids"] or [])
                if c not in rub_crit.get(r["competency_id"], set())]
    missing_dvga = [r["alternative_id"] for r in reqs if r["criterion_ids"] is None]
    dvga_real = sum(1 for r in reqs if r["source_type"] == "REAL" and r["criterion_ids"] is not None)
    flagged = [r for r in rows if r["provenance_flag"]]
    label_counts = collections.Counter(r["repo_display_source_name"] for r in flagged)
    empty_groups = [v["id"] for v in allv for g in v["groups"] if not g["alternatives"]]
    no_mand = [r["vacancy_id"] for r in rows if r["mandatory_group_count"] == 0]
    L = ["# Аудит набору вакансій (data/)", "",
         f"Версія: `{version}` (sha256 фікстур: " + ", ".join(f"`{k}` {v[:12]}" for k, v in files.items()) + ").",
         "Згенеровано `app/scripts/chapter4/data_package.py` з фікстур репозиторію (ті самі файли засіває "
         "`backend/seed.py`).", "",
         "## Склад", "", "| Професія | Тип джерела | Вакансій |", "|---|---|---|"]
    L += [f"| {p} | {s} | {n} |" for (p, s), n in sorted(by.items())]
    L += ["", f"Усього вакансій: {len(rows)}; груп вимог: {sum(r['requirement_group_count'] for r in rows)} "
              f"(обов'язкових {sum(r['mandatory_group_count'] for r in rows)}, бажаних "
              f"{sum(r['preferred_group_count'] for r in rows)}); OR-груп: {sum(r['or_group_count'] for r in rows)}; "
              f"альтернатив: {len(reqs)}.", "",
          "## Перевірки", "", "| Перевірка | Результат |", "|---|---|",
          f"| Унікальність vacancy_id | {'PASS' if not dup_ids else 'FAIL ' + str(dup_ids)} |",
          f"| Однакові тексти опису | {sum(n for n in desc.values() if n > 1)} вакансій у {sum(1 for n in desc.values() if n > 1)} групах дублікатів |",
          f"| Однакові (назва, компанія) | {sum(1 for n in title_co.values() if n > 1)} пар |",
          f"| Група без альтернатив | {len(empty_groups)} |",
          f"| Вакансія без обов'язкових груп | {len(no_mand)} |",
          f"| competency_id відсутній у competencies.json | {unknown_comp or 'немає'} |",
          f"| competency_id без засіяної рубрики | {no_rubric or 'немає'} |",
          f"| criterion_ids (D_vga) поза рубрикою своєї компетентності | {len(bad_crit)} |",
          f"| Альтернатив без D_vga | {len(missing_dvga)} |",
          "| Логіка | групи між собою — AND; альтернативи в групі — OR (`eval_group`: SATISFIED, якщо задовольняє "
          "будь-яка; FAILED, лише якщо провалено всі) |", "",
          "## Походження і застереження", "",
          "- `REAL` (49): короткі описи, складені з публічних оголошень Djinni (`djinni-import-v1`, `retrieved_at` "
          "у vacancies.csv). Рівень вакансії для них визначено правилом `SENIORITY_RULE_V1`, а не роботодавцем.",
          "- `CURATED` і `SYNTHETIC` (180): вигадані/адаптовані приклади репозиторію; зовнішнього джерела немає, тому "
          "`source_reference` = фікстура.",
          f"- **Знахідка аудиту (DATASET-1).** Поле відображення `source_name` (fixtures/vacancy_sources.json, "
          f"assignment `{extra['sources'].get('assignment')}`) присвоює {len(flagged)} не-реальним вакансіям назви "
          f"сайтів: " + ", ".join(f"{k}: {n}" for k, n in sorted(label_counts.items())) +
          ". За приміткою файлу це «заява власника проєкту на рівні каталогу (дані адаптовано для ілюстрації)», а не "
          "походження конкретного оголошення. Ці вакансії не можна описувати як отримані з robota.ua/work.ua/DOU; у "
          "vacancies.csv вони мають `source_type` CURATED/SYNTHETIC, мітку збережено в `repo_display_source_name` і "
          "позначено `provenance_flag`. Потрібна синхронізація UI/тексту диплома.",
          f"- **D_vga.** Усі {len(reqs) - len(missing_dvga)} альтернатив мають criterion_ids з правилом "
          f"`{extra['dvga']['criteria_source']}`, зокрема {dvga_real} альтернатив REAL-вакансій: критерії рубрик "
          "визначено правилом репозиторію, а не текстом роботодавця.",
          f"- **Пороги τ.** Значення з карти рівнів {TAU_BY_LEVEL} (`{TAU_SOURCE_LEVEL_MAP}`): у вакансіях немає "
          "порогів роботодавця, тому `threshold_status` = робоче припущення.",
          "- ESCO не використовується для оцінок; скрапінгу в цьому кроці немає.", ""]
    return "\n".join(L) + "\n"


_WORDS = [(0.85, "впевнено, з власним продакшн-досвідом"), (0.75, "застосовував на практиці"),
          (0.5, "розуміє загальну ідею без деталей"), (0.01, "лише чув або поверхово"), (-1, "не працював")]


def _word(x: float) -> str:
    return next(w for t, w in _WORDS if x >= t)


def build_candidates(runs: list[dict]) -> list[dict]:
    rows, hidden, refs, desc = [], [], [], []
    titles = {}
    for r in json.loads((FX / "rubrics.json").read_text(encoding="utf-8"))["rubrics"]:
        for c in r["criteria"]:
            titles[c["criterion_id"]] = c["title"]
    for p in PROFILES:
        s = p.spec()
        rows.append({"candidate_id": p.profile_id, "track": p.track, "desired_title": s.desired_title,
                     "desired_level": p.desired, "years_experience": p.years, "location": s.location,
                     "work_mode": s.work_mode, "self_ratings": json.dumps(s.self_ratings, ensure_ascii=False),
                     "data_origin": "SIMULATED (LLM-authored profile; not a real person)"})
        crit = [c for a in TRACK_ACTIONS["python"] for c in CRITERIA[a]] + list(PRACTICE_CRITERIA)
        hidden.append({"candidate_id": p.profile_id, "scenario_group": p.pattern, "designed_level": p.intended,
                       "oracle_level_policy_v4": oracle_level(p), "latent_rules": dict(p.rules), "default": p.default,
                       "latent_by_criterion": {c: p.truth(c) for c in crit},
                       "answer_anchor_by_criterion": {c: quant(p.truth(c)) for c in crit}})
        for c in crit:
            refs.append({"candidate_id": p.profile_id, "criterion_id": c, "reference_score": None,
                         "reference_status": "NOT_ANNOTATED", "annotator_id": None, "ground_truth_version": None})
        comp = []
        for a in TRACK_ACTIONS["python"]:
            vals = [quant(p.truth(c)) for c in CRITERIA[a]]
            groups = collections.defaultdict(list)
            for c, v in zip(CRITERIA[a], vals):
                groups[_word(v)].append(titles.get(c, c))
            comp.append({"competency_id": a, "statements": {w: t for w, t in groups.items()}})
        practice = {c.split(".")[1]: _word(quant(p.truth(c))) for c in PRACTICE_CRITERIA}
        desc.append({"candidate_id": p.profile_id, "desired_title": s.desired_title, "desired_level": p.desired,
                     "years_experience": p.years, "competencies": comp, "professional_practice": practice,
                     "note": "Опис компетентностей кандидата, незалежний від виходу CompetenceMatch (згенеровано з "
                             "латентного профілю симулятора). Рівень, сценарій і рейтинги системи не показано."})
    write_csv(DATA / "candidates.csv", list(rows[0]), rows)
    (DATA / "hidden").mkdir(parents=True, exist_ok=True)
    write_json(DATA / "hidden" / "scenario_definitions.json",
               {"_note": "HIDDEN: never shown to Interviewer/Evaluator/Planner or to annotators. The product sees "
                         "only candidates.csv fields; answers are generated per asked question from these values.",
                "simulator": SIMULATOR, "profiles": hidden})
    with open(DATA / "candidate_competency_reference.jsonl", "w", encoding="utf-8") as f:
        for r in refs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (DATA / "annotation_inputs").mkdir(parents=True, exist_ok=True)
    with open(DATA / "annotation_inputs" / "candidate_descriptions.jsonl", "w", encoding="utf-8") as f:
        for d in desc:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    return rows


def build_response_bank(runs: list[dict]) -> int:
    seen, out = set(), []
    p2s = {v: k for k, v in PHRASES.items()}
    for r in runs:
        if r["suite"] != "modes" or not r["turns"]:
            continue
        rv = r["equal_conditions"]
        for t in r["turns"]:
            fam = f"{t['action_id']}|{'+'.join(t['target_criteria'][:PER_Q])}|{t['difficulty']}"
            key = (r["profile_id"], fam, t["answer_text"])
            if key in seen:
                continue
            seen.add(key)
            out.append({"response_id": f"rb-{len(out) + 1:05d}", "candidate_id": r["profile_id"],
                        "question_family_id": fam, "competency_id": t["action_id"],
                        "criterion_ids": t["target_criteria"][:PER_Q], "difficulty": t["difficulty"],
                        "example_question": t["question_text"], "response_text": t["answer_text"],
                        "response_origin": "SIMULATED_TEMPLATE" if t["question_source"] == "LLM_INTERVIEWER"
                        else "SIMULATED_GENERIC_FOR_BANK_QUESTION",
                        "intended_scenario": "see data/hidden/scenario_definitions.json (hidden)",
                        "expert_label": None, "rubric_version": "v1", "simulator_version": SIMULATOR,
                        "first_run_id": r["run_id"], "seed": r["seed"], "model": "SIMULATED_STUB (no LLM)",
                        "prompt_version": rv["prompt_version"], "temperature": None,
                        "template_anchors": sorted({p2s[x] for x in PHRASES.values() if x in t["answer_text"]})})
    with open(DATA / "response_bank.jsonl", "w", encoding="utf-8") as f:
        for x in out:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    return len(out)


def _annotations_started() -> bool:
    for name in ANNOTATION_FILES:
        p = DATA / "annotations" / name
        if p.exists() and len(p.read_text(encoding="utf-8").strip().splitlines()) > 1:
            return True
    return False


def build_pools(runs: list[dict], allv: list[dict]) -> int:
    """Fixed vacancy pool per candidate: union of every interview mode's Top-10 (all budgets/seeds, the pooling
    method of IR evaluation) + POOL_RANDOM vacancies of the cohort chosen by hash, stratified by seniority; shown to
    annotators in hash order, without any mode, rank or score."""
    pool_path = DATA / "annotation_inputs" / "vacancy_pool.csv"
    if _annotations_started() and pool_path.exists():
        return -1  # frozen: annotations refer to it
    by_id = {v["id"]: v for v in allv}
    rows = []
    for p in PROFILES:
        rs = [r for r in runs if r["profile_id"] == p.profile_id and r["suite"] == "modes"]
        cohort = rs[0]["ranking"]
        pooled = {v for r in rs for v in r["ranking"][:10]}
        rest = [v for v in cohort if v not in pooled]
        strata = collections.defaultdict(list)
        for v in sorted(rest, key=lambda v: _h(p.profile_id, v)):
            strata[by_id[v]["seniority"]].append(v)
        extra, i = [], 0
        while len(extra) < POOL_RANDOM and any(strata.values()):
            for k in sorted(strata):
                if strata[k] and len(extra) < POOL_RANDOM:
                    extra.append(strata[k].pop(0))
            i += 1
        for v in sorted(pooled | set(extra), key=lambda v: _h("order", p.profile_id, v)):
            rows.append({"candidate_id": p.profile_id, "vacancy_id": v, "pool_version": "pool-v1"})
    write_csv(pool_path, ["candidate_id", "vacancy_id", "pool_version"], rows)
    texts = []
    for v in sorted({r["vacancy_id"] for r in rows}):
        x = by_id[v]
        texts.append({"vacancy_id": v, "title": x["title"], "seniority": x["seniority"], "years_min": x["years_min"],
                      "mandatory": [g["label"] for g in x["groups"] if g["kind"] == "MANDATORY"],
                      "desired": [g["label"] for g in x["groups"] if g["kind"] == "DESIRED"]})
    with open(DATA / "annotation_inputs" / "vacancy_texts.jsonl", "w", encoding="utf-8") as f:
        for t in texts:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    return len(rows)


def build_criterion_items(n_per_candidate: int = 6) -> int:
    """Pilot items for criterion annotation: question + answer only (no score, no scenario)."""
    bank = [json.loads(x) for x in (DATA / "response_bank.jsonl").read_text(encoding="utf-8").splitlines()]
    items = []
    for p in PROFILES:
        mine = sorted((b for b in bank if b["candidate_id"] == p.profile_id and b["response_origin"] ==
                       "SIMULATED_TEMPLATE"), key=lambda b: _h("item", b["response_id"]))[:n_per_candidate]
        items += [{"question_id": b["response_id"], "candidate_id": b["candidate_id"], "question": b["example_question"],
                   "answer": b["response_text"], "criterion_ids": b["criterion_ids"], "rubric_version": "v1"}
                  for b in mine]
    with open(DATA / "annotation_inputs" / "criterion_items.jsonl", "w", encoding="utf-8") as f:
        for x in items:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    return len(items)


def build_annotation_files() -> None:
    d = DATA / "annotations"
    d.mkdir(parents=True, exist_ok=True)
    for name, header in ANNOTATION_FILES.items():
        p = d / name
        if not p.exists() or len(p.read_text(encoding="utf-8").strip().splitlines()) <= 1:
            with open(p, "w", encoding="utf-8", newline="") as f:
                csv.writer(f).writerow(header)


def build() -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    files = {n: _sha(FX / n) for n in ("vacancies.json", "vacancies_real.json", "vacancy_criteria.json",
                                       "vacancy_sources.json", "rubrics.json", "competencies.json")}
    version = "ds-" + _h(*sorted(files.values()))[:12]
    pkg = build_vacancies(version)
    (DATA / "dataset_audit.md").write_text(audit(pkg, version, files), encoding="utf-8")
    runs = load_runs()
    build_candidates(runs)
    n_bank = build_response_bank(runs)
    n_pool = build_pools(runs, pkg["allv"])
    n_items = build_criterion_items()
    build_annotation_files()
    summary = {"dataset_version": version, "vacancies": len(pkg["rows"]), "requirement_alternatives": len(pkg["reqs"]),
               "candidates": len(PROFILES), "response_bank": n_bank,
               "vacancy_pool_rows": n_pool if n_pool >= 0 else "FROZEN (annotations exist)",
               "criterion_items": n_items, "annotations_started": _annotations_started(),
               "research_planner": RESEARCH_VERSION}
    write_json(DATA / "data_manifest.json", summary | {"fixture_sha256": files})
    return summary


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))
