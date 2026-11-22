"""Merge two pilot annotation passes, compute agreement (before adjudication), adjudicate per
ANNOTATION_INSTRUCTIONS.md section 5 steps 1-2, list rows for a third pass.

Usage: python app/scripts/chapter4/annotation_merge.py [--src DIR] [--out DIR]
Idempotent: rows of the merged annotator ids are replaced on rerun.
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "artifacts/chapter4/data"
SRC = ROOT / ".superpowers/sdd/annot"
A1, A2, ADJ = "LLM_ANNOTATOR_1", "LLM_ANNOTATOR_2", "ADJUDICATED"
LEVELS = ["JUNIOR", "MIDDLE", "SENIOR", "UNKNOWN"]
FILES = {
    "sen": "expert_seniority.csv",
    "crit": "expert_criterion_annotations.csv",
    "rel": "expert_vacancy_relevance.csv",
}
KEYS = {"sen": ("candidate_id",), "crit": ("candidate_id", "criterion_id", "question_id"), "rel": ("candidate_id", "vacancy_id")}
COUNTS = {"sen": 18, "crit": 202, "rel": 944}


def read(p: Path) -> tuple[list[str], list[dict]]:
    with p.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames), list(r)


def write(p: Path, header: list[str], rows: list[dict]) -> None:
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def kappa(a: list, b: list, labels: list, weight=lambda i, j, k: 0.0 if i == j else 1.0) -> float:
    """Cohen's kappa with disagreement weights w(i,j,k) (default unweighted)."""
    n, k = len(a), len(labels)
    idx = {l: i for i, l in enumerate(labels)}
    o = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b):
        o[idx[x]][idx[y]] += 1 / n
    pa = [sum(o[i]) for i in range(k)]
    pb = [sum(o[i][j] for i in range(k)) for j in range(k)]
    num = sum(weight(i, j, k) * o[i][j] for i in range(k) for j in range(k))
    den = sum(weight(i, j, k) * pa[i] * pb[j] for i in range(k) for j in range(k))
    return float("nan") if den == 0 else 1 - num / den


def quad(i, j, k):
    return ((i - j) / (k - 1)) ** 2


def validate(src: Path, inputs: Path) -> dict[str, list[str]]:
    import json
    cands = {json.loads(l)["candidate_id"] for l in (inputs / "candidate_descriptions.jsonl").open(encoding="utf-8")}
    items = set()
    for l in (inputs / "criterion_items.jsonl").open(encoding="utf-8"):
        d = json.loads(l)
        for c in d["criterion_ids"]:
            items.add((d["candidate_id"], c, d["question_id"]))
    _, pool = read(inputs / "vacancy_pool.csv")
    pool_keys = {(r["candidate_id"], r["vacancy_id"]) for r in pool}
    errs = []
    for a, aid in (("annotator_1", A1), ("annotator_2", A2)):
        for kind, fn in FILES.items():
            _, rows = read(src / a / fn)
            if len(rows) != COUNTS[kind]:
                errs.append(f"{a}/{fn}: {len(rows)} rows, expected {COUNTS[kind]}")
            keys = [tuple(r[k] for k in KEYS[kind]) for r in rows]
            if len(set(keys)) != len(keys):
                errs.append(f"{a}/{fn}: duplicate keys")
            for r in rows:
                if r["annotator_id"] != aid:
                    errs.append(f"{a}/{fn}: annotator_id {r['annotator_id']}")
                key = tuple(r[k] for k in KEYS[kind])
                if r["candidate_id"] not in cands:
                    errs.append(f"{a}/{fn}: unknown candidate {key}")
                if kind == "sen" and r["level"] not in LEVELS:
                    errs.append(f"{a}: bad level {key}")
                if kind == "rel":
                    if key not in pool_keys:
                        errs.append(f"{a}: pair not in pool {key}")
                    if r["relevance"] not in {"0", "1", "2", "3"}:
                        errs.append(f"{a}: bad relevance {key}")
                if kind == "crit":
                    if key not in items:
                        errs.append(f"{a}: criterion/question not in inputs {key}")
                    if r["evidence_status"] == "EVIDENCED":
                        if not 0 <= float(r["score"]) <= 1:
                            errs.append(f"{a}: bad score {key}")
                    elif r["evidence_status"] != "NO_EVIDENCE" or r["score"] != "":
                        errs.append(f"{a}: bad evidence_status {key}")
    return {"errors": errs}


def merge(src: Path, out: Path, inputs: Path) -> dict:
    res: dict = {"third": [], "n": {}, "m": {}}
    third = res["third"]
    for kind, fn in FILES.items():
        h, r1 = read(src / "annotator_1" / fn)
        _, r2 = read(src / "annotator_2" / fn)
        d1 = {tuple(r[k] for k in KEYS[kind]): r for r in r1}
        d2 = {tuple(r[k] for k in KEYS[kind]): r for r in r2}
        keys = sorted(d1)
        assert set(d1) == set(d2), f"{fn}: key sets differ"
        adj = []
        pairs = []
        for k in keys:
            a, b = d1[k], d2[k]
            base = {c: "" for c in h}
            base.update({c: a[c] for c in KEYS[kind]})
            base["annotator_id"] = ADJ
            if kind == "rel":
                x, y = int(a["relevance"]), int(b["relevance"])
                pairs.append((k, x, y))
                if abs(x - y) >= 2 or (x >= 2) != (y >= 2):
                    third.append(("relevance", k[0], k[1], x, y, a["rationale"], b["rationale"]))
                    continue
                base.update(relevance=(x + y) // 2, rationale=f"A1: {a['rationale']} | A2: {b['rationale']}",
                            scale_version=a["scale_version"])
            elif kind == "sen":
                pairs.append((k, a["level"], b["level"]))
                if a["level"] != b["level"]:
                    third.append(("level", k[0], "", a["level"], b["level"], a["rationale"], b["rationale"]))
                    continue
                base.update(level=a["level"], rationale=f"A1: {a['rationale']} | A2: {b['rationale']}",
                            evidence_refs=a["evidence_refs"])
            else:
                s1, s2 = a["score"], b["score"]
                pairs.append((k, None if s1 == "" else float(s1), None if s2 == "" else float(s2)))
                if (s1 == "") != (s2 == "") or (s1 != "" and abs(float(s1) - float(s2)) > 0.2 + 1e-9):
                    third.append(("criterion", k[0], f"{k[1]}@{k[2]}", s1, s2, a["comment"], b["comment"]))
                    continue
                base.update(rubric_version=a["rubric_version"],
                            comment=f"A1: {a['comment']} | A2: {b['comment']}")
                if s1 == "":
                    base.update(evidence_status="NO_EVIDENCE", score="")
                else:
                    base.update(evidence_status="EVIDENCED", score=f"{(float(s1) + float(s2)) / 2:.3f}".rstrip("0").rstrip("."))
            adj.append(base)
        res[kind] = pairs
        res["n"][kind] = len(adj)
        _, existing = read(out / fn)
        keep = [r for r in existing if r["annotator_id"] not in {A1, A2, ADJ}]
        write(out / fn, h, keep + r1 + r2 + adj)
    tp = out / "third_pass_needed.csv"
    with tp.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["kind", "candidate_id", "vacancy_or_criterion_id", "label_1", "label_2", "rationale_1", "rationale_2"])
        w.writerows(third)
    return res


def stats(res: dict) -> dict:
    s: dict = {}
    rel = res["rel"]
    x = [p[1] for p in rel]; y = [p[2] for p in rel]
    s["rel_wk"] = kappa(x, y, [0, 1, 2, 3], quad)
    s["rel_exact"] = sum(a == b for a, b in zip(x, y)) / len(x)
    bx = [int(a >= 2) for a in x]; by = [int(b >= 2) for b in y]
    s["bin_agree"] = sum(a == b for a, b in zip(bx, by)) / len(x)
    s["bin_k"] = kappa(bx, by, [0, 1])
    s["rel_cm"] = Counter((a, b) for a, b in zip(x, y))
    byc = defaultdict(list)
    for (k, a, b) in rel:
        byc[k[0]].append((a, b))
    s["per_cand"] = {}
    for c, v in sorted(byc.items()):
        aa = [p[0] for p in v]; bb = [p[1] for p in v]
        s["per_cand"][c] = (len(v), sum(a == b for a, b in v) / len(v), sum(abs(a - b) for a, b in v) / len(v),
                            kappa(aa, bb, [0, 1, 2, 3], quad) if len(set(aa)) > 1 and len(set(bb)) > 1 else float("nan"))
    sen = res["sen"]
    s["lev_k"] = kappa([p[1] for p in sen], [p[2] for p in sen], LEVELS)
    s["lev_exact"] = sum(p[1] == p[2] for p in sen) / len(sen)
    s["lev_cm"] = Counter((p[1], p[2]) for p in sen)
    both = [p for p in res["crit"] if p[1] is not None and p[2] is not None]
    s["crit_n"] = len(res["crit"]); s["crit_both"] = len(both)
    s["crit_mae"] = sum(abs(p[1] - p[2]) for p in both) / len(both)
    s["crit_big"] = sum(abs(p[1] - p[2]) > 0.2 + 1e-9 for p in both) / len(both)
    return s


def fmt(v: float) -> str:
    return "н/д" if isinstance(v, float) and math.isnan(v) else f"{v:.3f}"


def report(res: dict, s: dict, out: Path) -> None:
    t = Counter(x[0] for x in res["third"])
    L = ["# Узгодженість двох пілотних проходів розмітки", "",
         "## Метод", "",
         "Два незалежні проходи `LLM_ANNOTATOR_1` та `LLM_ANNOTATOR_2` (мітка `LLM_ANNOTATOR_PILOT`) — "
         "це **LLM-розмітники, а не експерти-люди**. Узгодженість обчислено **до** узгодження "
         "(ANNOTATION_INSTRUCTIONS.md, §5.4): зважена каппа Коена з квадратичними вагами для релевантності 0–3; "
         "бінарна згода та каппа за порогом ≥2; каппа Коена й матриця неузгодженості для рівня; MAE та частка "
         "|Δ|>0.2 для оцінок критеріїв. Скрипт: `app/scripts/chapter4/annotation_merge.py` (відтворює всі числа).", "",
         "## Валідація входу", "",
         "Обидва проходи: 18 рівнів, 202 оцінки критеріїв, 944 пари кандидат–вакансія; ідентифікатори кандидатів, "
         "пар (пул) та пар критерій–питання існують у `annotation_inputs`; значення в допустимих межах.", "",
         "## Релевантність (944 пари)", "",
         f"- Зважена каппа (квадратична): **{fmt(s['rel_wk'])}**",
         f"- Точна згода: {fmt(s['rel_exact'])}",
         f"- Бінарна згода (≥2): {fmt(s['bin_agree'])}; бінарна каппа: **{fmt(s['bin_k'])}**", "",
         "Матриця (рядок — розмітник 1, стовпець — розмітник 2):", "",
         "| A1\\A2 | 0 | 1 | 2 | 3 |", "|---|---|---|---|---|"]
    for a in range(4):
        L.append(f"| {a} | " + " | ".join(str(s['rel_cm'].get((a, b), 0)) for b in range(4)) + " |")
    L += ["", "### Узгодженість за кандидатами", "",
          "| Кандидат | Пар | Точна згода | MAE | wκ |", "|---|---|---|---|---|"]
    for c, (n, e, m, k) in s["per_cand"].items():
        L.append(f"| {c} | {n} | {fmt(e)} | {fmt(m)} | {fmt(k)} |")
    L += ["", "## Рівень (18 кандидатів)", "",
          f"- Каппа Коена: **{fmt(s['lev_k'])}**; точна згода: {fmt(s['lev_exact'])}", "",
          "| A1\\A2 | " + " | ".join(LEVELS) + " |", "|---|" + "---|" * 4]
    for a in LEVELS:
        L.append(f"| {a} | " + " | ".join(str(s['lev_cm'].get((a, b), 0)) for b in LEVELS) + " |")
    L += ["", "## Критерії", "",
          f"- Оцінок: {s['crit_n']} (з обома значеннями: {s['crit_both']}); MAE = **{fmt(s['crit_mae'])}**; "
          f"частка |Δ|>0.2 = **{fmt(s['crit_big'])}**.",
          "- Обидва проходи ставили оцінки за якорями рубрики з фраз відповіді (відповіді шаблонні), тому "
          "збіг критеріїв значною мірою тривіальний і не свідчить про незалежну якість розмітки.", "",
          "## Узгодження (§5.1–5.2)", "",
          f"Записано рядків `ADJUDICATED`: релевантність {res['n']['rel']}, рівень {res['n']['sen']}, критерії {res['n']['crit']}. "
          "Релевантність: середнє з округленням униз, якщо |r1−r2|≤1 і обидві оцінки по одну сторону порогу 2 "
          "(пара 1 vs 2 перетинає поріг, тому йде на третій прохід за §5.1); критерій — середнє; рівень — спільне значення.", "",
          "## Рядки для третього проходу", "",
          f"Файл `third_pass_needed.csv` (обидві мітки й обґрунтування; не розв'язано): релевантність **{t['relevance']}**, "
          f"рівень **{t['level']}**, критерії **{t['criterion']}**.", "",
          "## Застереження", "",
          "- Розмітники — LLM, а не люди-експерти; це **пілот**, не еталон.",
          "- Обидва оцінювали за таблицями архетипів/груп профілів (див. їхні notes.md), тому мітки в межах групи "
          "сильно корельовані; ефективний обсяг вибірки значно менший за 944/202, а показники узгодженості, "
          "імовірно, **завищені**.",
          "- Значення κ не слід трактувати як довіру до якості еталону; потрібна розмітка експертами-людьми.",
          "- Кандидати та вакансії синтетичні."]
    (out / "agreement_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument("--out", type=Path, default=DATA / "annotations")
    ap.add_argument("--inputs", type=Path, default=DATA / "annotation_inputs")
    a = ap.parse_args()
    errs = validate(a.src, a.inputs)["errors"]
    if errs:
        raise SystemExit("validation failed:\n" + "\n".join(errs[:20]))
    res = merge(a.src, a.out, a.inputs)
    s = stats(res)
    report(res, s, a.out)
    print({k: v for k, v in s.items() if isinstance(v, float)}, Counter(x[0] for x in res["third"]), res["n"])


if __name__ == "__main__":
    main()
