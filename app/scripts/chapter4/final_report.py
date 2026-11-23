"""Phase 3: hypotheses H1-H4, paired comparisons vs pilot labels, tables 4.1-4.7, figures, evidence report.

Reads only machine-readable files: raw/modes_runs.jsonl.gz (SIMULATED runs on the frozen commit), data/annotations
(ADJUDICATED pilot labels, LLM_ANNOTATOR_PILOT), data/annotation_inputs/vacancy_pool.csv, mathematical_validation.csv,
dataset_summary.csv, data/data_manifest.json, experiment_manifest.json, raw/timing_e6.json, test_results.md (run
tables), ablation_results.csv. Writes tables/, figures/, figures_data/, hypothesis_comparisons.csv,
ranking_per_candidate_differences.csv, level_confusion_pilot.csv, chapter4_evidence_report.md,
chapter4_results_summary.md, missing_evidence.md, self_audit.json (via self_audit.py) and the manifest `phase3` block.
Deterministic: seeded bootstrap; no timestamps in generated text.
Run from app/:  uv run python -m scripts.chapter4.final_report
"""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from scripts.chapter4.chapter4_metrics import _md_table, _read, _svg_lines, annotations, pools, run_pool_metrics
from scripts.chapter4.common import OUT, write_csv, write_json
from scripts.chapter4.modes_analysis import A, B, BOOT, C, D, DFD, RANK, RNG_SEED, derive, mode_means, paired
from scripts.chapter4.modes_experiment import load_runs

TAB, FIGS, FIGD = OUT / "tables", OUT / "figures", OUT / "figures_data"
BUDGETS = (10, 20, 30, 50)
SHORT = {A: "A", B: "B", C: "C", D: "D", DFD: "Dfd"}
UA = {A: "A: початковий профіль", B: "B: статичне", C: "C: адаптивне без ринку", D: "D: CompetenceMatch",
      DFD: "D без зміни складності"}
LEVELS = ["JUNIOR", "MIDDLE", "SENIOR", "UNKNOWN"]
PAIRS = ((C, B), (D, C), (D, B), (D, A), (B, A), (C, A))
GT_UA = "пілотні мітки LLM-розмітників (LLM_ANNOTATOR_PILOT, ADJUDICATED), не експерти-люди"
PILOT_FLAG = ("PILOT: мітки LLM-розмітників, корельовані між собою (метод архетипів, малий ефективний n) і з "
              "LLM-оцінювачами; не незалежна людська валідація")


def f(x, n=3) -> str:
    return "—" if x in ("", None) else f"{float(x):.{n}f}"


def ci(m: dict, n=3) -> str:
    return f"{f(m['mean'], n)} [{f(m['ci95_low'], n)}; {f(m['ci95_high'], n)}]" if m.get("mean") != "" else "—"


# ---------- per-run values ----------
def prepare() -> tuple[list[dict], dict]:
    ann = annotations()
    pool_map = pools()
    runs = []
    for r in load_runs():
        if r["suite"] != "modes":
            continue
        r = derive(r)
        pm = run_pool_metrics(r, ann, pool_map)
        r["p_at_5"] = pm["p5"] if pm else None
        r["ndcg_at_10"] = pm["ndcg10"] if pm else None
        r["pool_missing"] = pm["missing"] if pm else None
        lvl = ann["levels"].get(r["profile_id"])
        got = r["level_assessed_level"]
        r["pilot_level"] = lvl
        r["level_correct_pilot"] = None if not lvl or got is None else float(got == lvl)
        r["level_abstained_pilot"] = None if not lvl or got is None else float(got == "UNKNOWN" and lvl != "UNKNOWN")
        top5 = r["top10"][:5]
        r["top5_share_unresolved_mandatory"] = sum(x["z"] == 1 for x in top5) / len(top5) if top5 else None
        r["top5_share_confirmed_gap"] = sum(x["z"] == 0 for x in top5) / len(top5) if top5 else None
        # re-asking: every target criterion of the question was already a target of an earlier question of the run
        seen, rep = set(), 0
        for t in r["turns"]:
            tg = t["target_criteria"]
            tg = json.loads(tg.replace("'", '"')) if isinstance(tg, str) else (tg or [])
            if tg and set(tg) <= seen:
                rep += 1
            seen.update(tg)
        r["reask_share"] = rep / len(r["turns"]) if r["turns"] else None
        r["distinct_targets_per_question"] = len(seen) / len(r["turns"]) if r["turns"] else None
        runs.append(r)
    return runs, ann


def comparisons(runs) -> list[dict]:
    metrics = ("relevant_coverage", "p_at_5", "ndcg_at_10", "level_correct_pilot", "level_correct",
               "level_abstained_pilot", "unresolved_mandatory_count", "unknown_count",
               "top5_share_unresolved_mandatory", "top5_share_confirmed_gap", "n_questions", "reask_share")
    out = []
    for metric in metrics:
        for a, b in PAIRS + ((D, DFD),):
            for bud in BUDGETS:
                p = paired(runs, metric, a, b, bud)
                if p:
                    n = p["profiles_a_gt_b"] + p["profiles_a_lt_b"]
                    p["sign_test_note"] = ("n (без нічиїх) < 6: знаковий тест не може дати p<0.05" if n < 6 else "")
                    p["ground_truth"] = "PILOT_LLM_ANNOTATOR" if metric in ("p_at_5", "ndcg_at_10", "level_correct_pilot",
                                                                            "level_abstained_pilot") else \
                        ("SIMULATED_GROUND_TRUTH" if metric == "level_correct" else "")
                    out.append(p)
    return out


def get(cmp_rows, metric, a, b, bud) -> dict:
    return next((x for x in cmp_rows if x["metric"] == metric and x["a"] == a and x["b"] == b and x["budget"] == bud), {})


def means(runs, metric, mode, bud) -> dict:
    return mode_means(runs, metric, mode, bud)


def per_candidate_diffs(e3: list[dict]) -> list[dict]:
    idx = {(x["candidate_id"], x["mode"], str(x["budget"])): x for x in e3}
    out = []
    for (cid, mode, bud), x in sorted(idx.items()):
        if mode != D or not bud:
            continue
        for other in (A, B, C):
            y = idx.get((cid, other, "" if other == A else bud))
            if not y or x["precision_at_5"] == "" or y["precision_at_5"] == "":
                continue
            dp = float(x["precision_at_5"]) - float(y["precision_at_5"])
            dn = (float(x["ndcg_at_10"]) - float(y["ndcg_at_10"])) if x["ndcg_at_10"] != "" and y["ndcg_at_10"] != "" else None
            out.append({"candidate_id": cid, "budget": bud, "comparison": f"D-{SHORT[other]}",
                        "p_at_5_D": x["precision_at_5"], "p_at_5_other": y["precision_at_5"], "diff_p_at_5": round(dp, 4),
                        "ndcg_at_10_D": x["ndcg_at_10"], "ndcg_at_10_other": y["ndcg_at_10"],
                        "diff_ndcg_at_10": "" if dn is None else round(dn, 4),
                        "direction_p_at_5": "покращення" if dp > 1e-9 else "погіршення" if dp < -1e-9 else "без змін",
                        "direction_ndcg_at_10": "" if dn is None else
                        ("покращення" if dn > 1e-9 else "погіршення" if dn < -1e-9 else "без змін"),
                        "ground_truth": "PILOT_LLM_ANNOTATOR"})
    return out


def confusion(runs) -> list[dict]:
    out = []
    for mode in (A, B, C, D):
        for bud in ((None,) if mode == A else BUDGETS):
            rs = [r for r in runs if r["mode_label"] == mode and (mode == A or r["total_budget"] == bud) and r["pilot_level"]]
            cm = Counter((r["pilot_level"], r["level_assessed_level"]) for r in rs)
            for t in LEVELS:
                out.append({"mode": mode, "budget": bud or "", "pilot_level": t,
                            **{f"assessed_{p}": cm.get((t, p), 0) for p in LEVELS}, "n_runs": len(rs),
                            "ground_truth": "PILOT_LLM_ANNOTATOR"})
    return out


# ---------- hypotheses ----------
def hypotheses(cmp_rows, ann) -> list[dict]:
    def all_ci(metric, a, b, sign):
        rows = [get(cmp_rows, metric, a, b, bud) for bud in BUDGETS]
        if sign > 0:
            return all(r and r["ci95_low"] != "" and r["ci95_low"] > 0 for r in rows)
        return all(r and r["ci95_high"] != "" and r["ci95_high"] < 0 for r in rows)

    def line(metric, a, b, n=3):
        return "; ".join(f"b{bud}: {f(get(cmp_rows, metric, a, b, bud).get('mean_a_minus_b'), n)} "
                         f"[{f(get(cmp_rows, metric, a, b, bud).get('ci95_low'), n)}; "
                         f"{f(get(cmp_rows, metric, a, b, bud).get('ci95_high'), n)}], "
                         f"{get(cmp_rows, metric, a, b, bud).get('profiles_a_gt_b')}+/"
                         f"{get(cmp_rows, metric, a, b, bud).get('profiles_a_lt_b')}−" for bud in BUDGETS)

    out = []
    # H1: primary metric relevant coverage at equal budget, B vs C and B vs D
    if all_ci("relevant_coverage", C, B, -1) and all_ci("relevant_coverage", D, B, -1):
        h1 = "NOT_SUPPORTED"
    elif all_ci("relevant_coverage", C, B, +1) and all_ci("relevant_coverage", D, B, +1):
        h1 = "SUPPORTED"
    else:
        h1 = "INCONCLUSIVE"
    out.append({"hypothesis": "H1", "statement": "адаптивне інтерв'ю дає більше покриття, ніж статичне, за рівного бюджету",
                "primary_metric": "relevant_coverage (частка 80 критеріїв D_vga з оцінкою), C−B і D−B, усі бюджети",
                "status": h1, "ground_truth": "не потрібна (покриття)", "evidence": "C−B: " + line("relevant_coverage", C, B)
                + " | D−B: " + line("relevant_coverage", D, B),
                "scope": "SIMULATED: 18 симульованих кандидатів, заглушки Interviewer/Evaluator"})
    # H2: ranking vs independent relevance; ground truth is a pilot -> capped at INCONCLUSIVE
    gt = ann["ground_truth_version"]
    if gt != "HUMAN_EXPERT":
        h2 = "INCONCLUSIVE" if gt else "NOT_TESTED"
    else:
        h2 = ("SUPPORTED" if all(all_ci(m, D, o, +1) for m in ("p_at_5", "ndcg_at_10") for o in (A, B)) else
              "NOT_SUPPORTED" if any(all_ci(m, D, o, -1) for m in ("p_at_5", "ndcg_at_10") for o in (A, B)) else "INCONCLUSIVE")
    out.append({"hypothesis": "H2", "statement": "ранжування за профілем після адаптивного інтерв'ю ближче до незалежної "
                "релевантності, ніж INITIAL і STATIC",
                "primary_metric": "P@5 (релевантна ≥2) і NDCG@10 на фіксованому пулі, D−A і D−B",
                "status": h2, "ground_truth": GT_UA,
                "evidence": "P@5 D−A: " + line("p_at_5", D, A) + " | P@5 D−B: " + line("p_at_5", D, B)
                + " | NDCG@10 D−A: " + line("ndcg_at_10", D, A) + " | NDCG@10 D−B: " + line("ndcg_at_10", D, B),
                "scope": "SIMULATED кандидати; " + PILOT_FLAG + "; статус обмежено INCONCLUSIVE, бо еталон пілотний"})
    # H3: market planning (D) vs adaptive without market (C), primary metric relevant coverage
    if all_ci("relevant_coverage", D, C, +1):
        h3 = "SUPPORTED"
    elif all_ci("relevant_coverage", D, C, -1):
        h3 = "NOT_SUPPORTED"
    else:
        h3 = "INCONCLUSIVE"
    out.append({"hypothesis": "H3", "statement": "ринкове планування (F(c), I(c), Q_t) краще за адаптивне без ринкової "
                "пріоритизації", "primary_metric": "relevant_coverage D−C, усі бюджети; вторинні: невирішені обов'язкові "
                "групи, рівень, P@5", "status": h3, "ground_truth": "не потрібна (первинна метрика)",
                "evidence": "покриття D−C: " + line("relevant_coverage", D, C) + " | невирішені обов'язкові групи D−C: "
                + line("unresolved_mandatory_count", D, C, 1) + " | збіг рівня з SIMULATED-істиною D−C: "
                + line("level_correct", D, C) + " | P@5 D−C (пілот): " + line("p_at_5", D, C),
                "scope": "SIMULATED; режим C — дослідницький планувальник research-no-market/v1, не продуктовий режим"})
    out.append({"hypothesis": "H4", "statement": "оцінювач визначає J/M/S за достатніх доказів і утримується (UNKNOWN) за "
                "недостатніх", "primary_metric": "точність, селективна точність, частка утримань, хибне підвищення "
                "проти пілотних рівнів і SIMULATED-рівнів, D за бюджетами",
                "status": "INCONCLUSIVE" if gt else "NOT_TESTED", "ground_truth": GT_UA + "; SIMULATED-рівні генератора",
                "evidence": "див. таблицю 4.6 і level_confusion_pilot.csv",
                "scope": "SIMULATED; " + PILOT_FLAG + "; статус обмежено INCONCLUSIVE"})
    return out


# ---------- SVG helpers ----------
COL = ["#1f5fa8", "#c2410c", "#15803d", "#7c3aed", "#6b7280"]


def svg_bars(path: Path, title: str, ylab: str, groups: list[str], series: dict[str, list], ymax: float,
             err: dict[str, list] | None = None, note: str = "") -> None:
    w = max(640, 90 + len(groups) * (24 * len(series) + 30) + 180)
    h, l, b, t, r = 420, 64, 70, 44, 190
    gw = (w - l - r) / len(groups)
    bw = min(28, (gw - 14) / len(series))
    fy = lambda y: h - b - (y / ymax) * (h - b - t)  # noqa: E731
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h}" font-family="sans-serif" font-size="12">',
         f'<rect width="{w:.0f}" height="{h}" fill="white"/>', f'<text x="{l}" y="22" font-size="14">{title}</text>',
         f'<line x1="{l}" y1="{h - b}" x2="{w - r}" y2="{h - b}" stroke="black"/>',
         f'<line x1="{l}" y1="{t}" x2="{l}" y2="{h - b}" stroke="black"/>',
         f'<text x="14" y="{(t + h - b) / 2}" transform="rotate(-90 14 {(t + h - b) / 2})" text-anchor="middle">{ylab}</text>']
    if note:
        o.append(f'<text x="{l}" y="{h - 10}" font-size="11" fill="#444">{note}</text>')
    for i in range(6):
        y = ymax * i / 5
        o.append(f'<text x="{l - 6}" y="{fy(y) + 4:.1f}" text-anchor="end">{y:.3g}</text>'
                 f'<line x1="{l}" y1="{fy(y):.1f}" x2="{w - r}" y2="{fy(y):.1f}" stroke="#e5e7eb"/>')
    for gi, g in enumerate(groups):
        x0 = l + gi * gw + (gw - bw * len(series)) / 2
        o.append(f'<text x="{l + gi * gw + gw / 2:.1f}" y="{h - b + 16}" text-anchor="middle">{g}</text>')
        for si, (name, vals) in enumerate(series.items()):
            v = vals[gi]
            if v is None:
                o.append(f'<text x="{x0 + si * bw + bw / 2:.1f}" y="{h - b - 4}" text-anchor="middle" font-size="9">н/д</text>')
                continue
            x = x0 + si * bw
            o.append(f'<rect x="{x:.1f}" y="{fy(v):.1f}" width="{bw - 2:.1f}" height="{h - b - fy(v):.1f}" fill="{COL[si % 5]}"/>')
            if err and err.get(name) and err[name][gi]:
                lo, hi = err[name][gi]
                cx = x + (bw - 2) / 2
                o.append(f'<line x1="{cx:.1f}" y1="{fy(lo):.1f}" x2="{cx:.1f}" y2="{fy(hi):.1f}" stroke="black"/>')
    for si, name in enumerate(series):
        o.append(f'<rect x="{w - r + 12}" y="{t + 18 * si}" width="12" height="10" fill="{COL[si % 5]}"/>'
                 f'<text x="{w - r + 30}" y="{t + 18 * si + 9}">{name}</text>')
    o.append("</svg>")
    path.write_text("\n".join(o) + "\n", encoding="utf-8")


def svg_heatmaps(path: Path, title: str, mats: dict[str, dict[tuple[str, str], int]], rows: list[str], cols: list[str]) -> None:
    cell, l, t = 56, 110, 70
    pw = l + cell * len(cols) + 40
    w, h = pw * len(mats) + 20, t + cell * len(rows) + 70
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" font-family="sans-serif" font-size="12">',
         f'<rect width="{w}" height="{h}" fill="white"/>', f'<text x="10" y="22" font-size="14">{title}</text>']
    for pi, (name, m) in enumerate(mats.items()):
        x0 = 10 + pi * pw
        mx = max(m.values() or [1]) or 1
        o.append(f'<text x="{x0 + l}" y="{t - 30}">{name}</text>')
        o.append(f'<text x="{x0 + l + cell * len(cols) / 2}" y="{t - 12}" text-anchor="middle" font-size="11">оцінений рівень</text>')
        o.append(f'<text x="{x0 + 4}" y="{t - 12}" font-size="11">пілотний рівень</text>')
        for ci_, c in enumerate(cols):
            o.append(f'<text x="{x0 + l + ci_ * cell + cell / 2}" y="{t + cell * len(rows) + 16}" text-anchor="middle" '
                     f'font-size="10">{c[:3]}</text>')
        for ri, rr in enumerate(rows):
            o.append(f'<text x="{x0 + l - 6}" y="{t + ri * cell + cell / 2 + 4}" text-anchor="end">{rr}</text>')
            for ci_, c in enumerate(cols):
                v = m.get((rr, c), 0)
                shade = int(255 - 200 * v / mx)
                o.append(f'<rect x="{x0 + l + ci_ * cell}" y="{t + ri * cell}" width="{cell - 2}" height="{cell - 2}" '
                         f'fill="rgb({shade},{shade},255)"/><text x="{x0 + l + ci_ * cell + cell / 2 - 1}" '
                         f'y="{t + ri * cell + cell / 2 + 4}" text-anchor="middle" fill="{"white" if v > mx / 2 else "black"}">{v}</text>')
    o.append(f'<text x="10" y="{h - 10}" font-size="11" fill="#444">Кількість прогонів (18 кандидатів × 3 сіди). '
             f'Еталон — пілотні мітки LLM-розмітників, не експерти-люди.</text>')
    o.append("</svg>")
    path.write_text("\n".join(o) + "\n", encoding="utf-8")


# ---------- tables ----------
def write_table(name: str, title: str, rows: list[dict], note: str = "") -> None:
    TAB.mkdir(parents=True, exist_ok=True)
    cols = list(dict.fromkeys(k for r in rows for k in r))
    write_csv(TAB / f"{name}.csv", cols, rows)
    (TAB / f"{name}.md").write_text(f"# {title}\n\n" + _md_table(rows, cols) + ("\n\n" + note if note else "") + "\n",
                                    encoding="utf-8")


def table_4_1(ann) -> list[dict]:
    ds = _read(OUT / "dataset_summary.csv")
    dm = json.loads((OUT / "data" / "data_manifest.json").read_text(encoding="utf-8"))
    cands = _read(OUT / "data" / "candidates.csv")
    n = ann["n_rows"]
    src = "dataset_summary.csv"
    rows = [{"Показник": "Професійні напрями (треки)", "Значення": ", ".join(r["track"] for r in ds), "Статус": "ВИМІРЯНО",
             "Джерело": src}]
    for r in ds:
        rows.append({"Показник": f"Вакансій у когорті, {r['track']}", "Значення": r["vacancies"], "Статус": "ВИМІРЯНО", "Джерело": src})
        rows.append({"Показник": f"Рубрик / критеріїв, {r['track']}", "Значення": f"{r['rubrics_used']} / {r['criteria_in_used_rubrics']}",
                     "Статус": "ВИМІРЯНО", "Джерело": src})
        rows.append({"Показник": f"Груп вимог: обов'язкових / бажаних / АБО, {r['track']}",
                     "Значення": f"{r['mandatory_groups']} / {r['desired_groups']} / {r['or_groups']}", "Статус": "ВИМІРЯНО",
                     "Джерело": src})
        rows.append({"Показник": f"Розподіл рівнів вакансій, {r['track']}", "Значення": r["seniority_distribution"].replace('"', ""),
                     "Статус": "ВИМІРЯНО", "Джерело": src})
    lv = Counter(c["desired_level"] for c in cands)
    rows += [{"Показник": "Кандидати (експерименти — лише python)", "Значення": f"{len(cands)} (бажаний рівень: "
              + ", ".join(f"{k} {v}" for k, v in sorted(lv.items())) + ")", "Статус": "SIMULATED", "Джерело": "data/candidates.csv"},
             {"Показник": "Походження кандидатів", "Значення": "симульовані профілі, створені LLM; не реальні люди",
              "Статус": "SIMULATED", "Джерело": "data/candidates.csv (data_origin)"},
             {"Показник": "Походження вакансій", "Значення": "Походження вакансій наведено за приміткою власника про дані; "
              "технічні метадані імпорту збережені в репозиторії (поля import_version, retrieved_at, source_name)",
              "Статус": "ЗА ПРИМІТКОЮ ВЛАСНИКА", "Джерело": "data/dataset_audit.md"},
             {"Показник": "Версія набору даних", "Значення": dm["dataset_version"], "Статус": "ЗАФІКСОВАНО",
              "Джерело": "data/data_manifest.json"},
             {"Показник": "Альтернатив вимог (усі треки)", "Значення": dm["requirement_alternatives"], "Статус": "ВИМІРЯНО",
              "Джерело": "data/data_manifest.json"},
             {"Показник": "Пул вакансій для розмітки (пари кандидат–вакансія)", "Значення": len(_read(OUT / "data" / "annotation_inputs" / "vacancy_pool.csv")),
              "Статус": "ЗАФІКСОВАНО (pool-v1)", "Джерело": "data/annotation_inputs/vacancy_pool.csv"},
             {"Показник": "Рядки пілотної розмітки: релевантність / рівень / критерії",
              "Значення": f"{n['relevance']} / {n['seniority']} / {n['criterion']} (ADJUDICATED: {sum(len(v) for v in ann['relevance'].values())} / "
              f"{len(ann['levels'])} / {len(ann['criterion'])})", "Статус": "PILOT_LLM_ANNOTATOR", "Джерело": "data/annotations/"},
             {"Показник": "Експертна розмітка людьми", "Значення": "відсутня", "Статус": "NO_GROUND_TRUTH",
              "Джерело": "missing_evidence.md"}]
    return rows


def table_4_2() -> list[dict]:
    man = json.loads((OUT / "experiment_manifest.json").read_text(encoding="utf-8"))
    fc = man["frozen_config"]
    mr = next(r for r in man["runs"] if r["suite"] == "modes")
    eq = mr.get("equal_conditions_check", {})
    rows = [("Продуктовий код (commit)", fc["commit"][:12], "ЗАФІКСОВАНО"),
            ("Режими", "A INITIAL_PROFILE; B STATIC_INTERVIEW; C ADAPTIVE_NO_MARKET (дослідницький планувальник, не "
             "продукт); D FULL_COMPETENCEMATCH; Dfd — D без зміни складності (абляція)", "ЗАФІКСОВАНО"),
            ("Бюджети питань", ", ".join(str(b) for b in mr["budgets"]), "ЗАФІКСОВАНО"),
            ("Сіди", ", ".join(str(s) for s in mr["seeds"]), "ЗАФІКСОВАНО"),
            ("Кандидати", f"{len(mr['profiles'])} симульованих (python)", "SIMULATED"),
            ("Прогонів (suite modes)", mr["n_runs"], "SIMULATED"),
            ("Interviewer / Evaluator", f"детерміновані заглушки ({mr['stub']}); реальна LLM не викликалась", "SIMULATED"),
            ("Модель кандидата", mr["candidate_model"], "SIMULATED"),
            ("Політика рівнів", f"{fc['seniority_policy']['current_python']} ({fc['seniority_policy']['status']}), "
             f"min_confirming_turns={fc['seniority_policy']['min_confirming_turns']}", "ЗАФІКСОВАНО"),
            ("Контролер складності", fc["difficulty_controller"]["version"], "ЗАФІКСОВАНО"),
            ("Ранжування в експериментах", fc["ranking"]["experiments_and_recommendations"], "ЗАФІКСОВАНО"),
            ("Ранжування на екрані результатів", fc["ranking"]["results_screen"], "ВІДХИЛЕННЯ ВІД (2.15); не впливає на експерименти"),
            ("Версія промптів", fc["prompt_version"][:12], "ЗАФІКСОВАНО"),
            ("Ліміти інтерв'ю", f"тем ≤ {fc['interview_limits']['max_topics']}, питань на тему ≤ "
             f"{fc['interview_limits']['max_questions_per_topic']}, мінімум {fc['interview_limits']['min_questions_per_open_topic']}",
             "ЗАФІКСОВАНО"),
            ("Перевірка однакових умов", json.dumps(eq, ensure_ascii=False)[:300] if eq else "—", "ПЕРЕВІРЕНО" if eq else "—"),
            ("Відтворюваність", json.dumps(mr.get("reproducibility", {}), ensure_ascii=False)[:200], "ПЕРЕВІРЕНО"),
            ("Налаштована LLM (не використовувалась)", f"{fc['llm']['configured_provider']} / {fc['llm']['configured_model']}, "
             f"t={fc['llm']['temperature']}", "NOT_RUN"),
            ("Еталон для P@5/NDCG/рівня", GT_UA, "PILOT_LLM_ANNOTATOR")]
    return [{"Умова": a, "Значення": b, "Статус": c} for a, b, c in rows]


def table_4_3() -> list[dict]:
    mv = _read(OUT / "mathematical_validation.csv")
    g = defaultdict(list)
    for r in mv:
        g[(r["kind"], r["quantity"])].append(r)
    out = []
    for (kind, q), rs in sorted(g.items()):
        st = Counter(r["status"] for r in rs)
        out.append({"Тип перевірки": "контрольний приклад" if kind == "CONTROL_EXAMPLE" else "властивість",
                    "Величина": q, "Перевірок": len(rs), "PASS": st.get("PASS", 0),
                    "Інші статуси": ", ".join(f"{k} {v} ({', '.join(r['id'] for r in rs if r['status'] == k)})"
                                              for k, v in st.items() if k != "PASS") or "—"})
    st = Counter(r["status"] for r in mv)
    out.append({"Тип перевірки": "УСЬОГО", "Величина": "", "Перевірок": len(mv), "PASS": st.get("PASS", 0),
                "Інші статуси": ", ".join(f"{k} {v}" for k, v in st.items() if k != "PASS")})
    return out


def table_4_4(runs, cmp_rows) -> list[dict]:
    out = []
    for mode in (A, B, C, D, DFD):
        for bud in ((None,) if mode == A else BUDGETS):
            rs = [r for r in runs if r["mode_label"] == mode and (mode == A or r["total_budget"] == bud)]
            cov = means(runs, "relevant_coverage", mode, bud)
            dB = get(cmp_rows, "relevant_coverage", mode, B, bud) if mode in (C, D) else {}
            out.append({"Режим": UA[mode], "Бюджет": bud or "—", "Прогонів": len(rs),
                        "Питань (середнє)": f(statistics.fmean(r["n_questions"] for r in rs), 1),
                        "Покриття релевантних критеріїв [95% ДІ]": ci(cov),
                        "Різниця покриття з B [95% ДІ]": f"{f(dB.get('mean_a_minus_b'))} [{f(dB.get('ci95_low'))}; "
                        f"{f(dB.get('ci95_high'))}]" if dB else "—",
                        "Покриття критичних критеріїв": f(statistics.fmean(1 - r["unresolved_critical_share"] for r in rs
                                                                           if r["unresolved_critical_share"] is not None)),
                        "Неоцінених критеріїв (з 80)": f(statistics.fmean(r["unknown_count"] for r in rs), 1),
                        "Невирішених обов'язкових груп (з 566)": f(statistics.fmean(r["unresolved_mandatory_count"] for r in rs), 1),
                        "Частка повторних питань": f(statistics.fmean(r["reask_share"] for r in rs)) if rs[0]["turns"] else "—",
                        "Follow-up (середнє)": f(statistics.fmean(r["followups"] for r in rs), 1),
                        "Тривалість, с (заглушки, не LLM)": f(statistics.median(r["total_s"] for r in rs), 2)
                        if rs[0]["turns"] else "—",
                        "Статус": "SIMULATED"})
    return out


def table_4_5(runs, cmp_rows) -> list[dict]:
    e3 = _read(OUT / "ranking_metrics.csv")

    def e3m(mode, bud, col):
        v = [float(x[col]) for x in e3 if x["mode"] == mode and x["budget"] == (str(bud) if bud else "") and x[col] != ""]
        return f(statistics.fmean(v)) if v else "—"
    out = []
    for mode in (A, B, C, D, DFD):
        for bud in ((None,) if mode == A else BUDGETS):
            rs = [r for r in runs if r["mode_label"] == mode and (mode == A or r["total_budget"] == bud)]
            out.append({"Режим": UA[mode], "Бюджет": bud or "—", "Кандидатів": len({r["profile_id"] for r in rs}),
                        "P@5 [95% ДІ]": ci(means(runs, "p_at_5", mode, bud)),
                        "NDCG@10 [95% ДІ]": ci(means(runs, "ndcg_at_10", mode, bud)),
                        "Top-5 з невирішеною обов'язковою групою": f(statistics.fmean(r["top5_share_unresolved_mandatory"] for r in rs)),
                        "Top-5 з підтвердженою критичною прогалиною": f(statistics.fmean(r["top5_share_confirmed_gap"] for r in rs)),
                        "Kendall τ з A (зміна рангу)": e3m(mode, bud, "kendall_tau_vs_A"),
                        "Перетин Top-5 з A": e3m(mode, bud, "top5_overlap_vs_A"),
                        "Стабільність Top-5 між сідами": e3m(mode, bud, "top5_stability_across_seeds"),
                        "SD P@5 між сідами": e3m(mode, bud, "precision_at_5_sd_seeds"),
                        "Тип еталона": "пілот LLM-розмітників (ADJUDICATED)",
                        "Статус": "COMPUTED_PILOT_LLM_ANNOTATOR"})
    return out


def table_4_6(runs) -> list[dict]:
    out = []
    for mode in (A, B, C, D, DFD):
        for bud in ((None,) if mode == A else BUDGETS):
            rs = [r for r in runs if r["mode_label"] == mode and (mode == A or r["total_budget"] == bud)]
            pil = [r for r in rs if r["pilot_level"]]
            non = [r for r in pil if r["level_assessed_level"] != "UNKNOWN"]
            by_c = defaultdict(list)
            for r in pil:
                by_c[r["profile_id"]].append(r["level_correct_pilot"])

            def f1(lab):
                tp = sum(r["level_assessed_level"] == lab and r["pilot_level"] == lab for r in pil)
                fp = sum(r["level_assessed_level"] == lab and r["pilot_level"] != lab for r in pil)
                fn = sum(r["level_assessed_level"] != lab and r["pilot_level"] == lab for r in pil)
                return 0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn)
            sim_c = defaultdict(list)
            for r in rs:
                if r["level_correct"] is not None:
                    sim_c[r["profile_id"]].append(r["level_correct"])
            out.append({"Режим": UA[mode], "Бюджет": bud or "—", "Прогонів": len(pil),
                        "Точність (пілот)": f(statistics.fmean(statistics.fmean(v) for v in by_c.values())),
                        "Macro-F1 (пілот, 4 класи)": f(statistics.fmean(f1(lab) for lab in LEVELS)),
                        "Частка утримань (UNKNOWN при визначеному рівні)": f(statistics.fmean(r["level_abstained_pilot"] for r in pil)),
                        "Селективна точність (пілот)": f(statistics.fmean(r["level_correct_pilot"] for r in non)) if non else "н/д: усі UNKNOWN",
                        "Хибне підвищення (пілот)": f(statistics.fmean(RANK[r["level_assessed_level"]] > RANK[r["pilot_level"]] for r in pil)),
                        "Необґрунтоване пониження (пілот)": f(statistics.fmean(0 < RANK[r["level_assessed_level"]] < RANK[r["pilot_level"]]
                                                                                for r in pil)),
                        "SENIOR досягнуто (прогонів)": sum(r["level_assessed_level"] == "SENIOR" for r in rs),
                        "Точність (SIMULATED-рівень генератора)": f(statistics.fmean(statistics.fmean(v) for v in sim_c.values())),
                        "Статус": "PILOT + SIMULATED"})
    return out


def parse_test_results() -> list[dict]:
    txt = (OUT / "test_results.md").read_text(encoding="utf-8")
    out, section = [], ""
    for line in txt.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if "`" not in line or cells[0] in ("#", "Команда", "Перевірка"):
            continue
        if section.startswith("2."):
            continue
        if cells[0].isdigit():
            cells = cells[1:]
        if len(cells) < 4:
            continue
        out.append({"Розділ test_results.md": section, "Команда": cells[0], "Середовище": cells[1], "Результат": cells[2],
                    "Тривалість": cells[3]})
    return out


def table_4_7(timing: dict | None) -> list[dict]:
    rows = parse_test_results()
    rows.append({"Розділ test_results.md": "—", "Команда": "повний pytest на PostgreSQL", "Середовище": "—",
                 "Результат": "NOT_RUN: tests/conftest.py задає SQLite", "Тривалість": "—"})
    rows.append({"Розділ test_results.md": "—", "Команда": "реальна LLM (локальна / продакшн)", "Середовище": "—",
                 "Результат": "NOT_RUN: локальна кінцева точка недоступна; платні виклики не дозволено", "Тривалість": "—"})
    if timing:
        for k, v in timing["components"].items():
            rows.append({"Розділ test_results.md": "E6 (raw/timing_e6.json)", "Команда": f"scripts.chapter4.timing_e6: {k}",
                         "Середовище": f"{timing['machine']['cpu']}, Python {timing['machine']['python']}, SQLite in-memory",
                         "Результат": f"медіана {v['median_ms']:.3f} мс, p95 {v['p95_ms']:.3f} мс (N={v['n']})",
                         "Тривалість": "—"})
    return rows


# ---------- figures ----------
def figures(runs, cmp_rows) -> list[str]:
    FIGS.mkdir(parents=True, exist_ok=True)
    made = []
    # 1 coverage vs budget by mode
    rows = []
    for mode in (A, B, C, D):
        for bud in BUDGETS:
            m = means(runs, "relevant_coverage", mode, bud)
            rows.append({"mode": mode, "budget": bud, "relevant_coverage_mean": m["mean"], "ci95_low": m["ci95_low"],
                         "ci95_high": m["ci95_high"], "status": "SIMULATED"})
    write_csv(FIGD / "fig_coverage_vs_budget.csv", list(rows[0]), rows)
    _svg_lines(FIGS / "fig_coverage_vs_budget.svg", "Покриття релевантних критеріїв залежно від бюджету (SIMULATED)",
               "бюджет питань", "частка оцінених критеріїв (з 80)",
               {UA[m]: [(float(x["budget"]), x["relevant_coverage_mean"]) for x in rows if x["mode"] == m] for m in (A, B, C, D)}, 1.0)
    made.append("fig_coverage_vs_budget")
    # 2 coverage B/C/D bars with CI
    grp = [f"b{b}" for b in BUDGETS]
    ser = {UA[m]: [next(x["relevant_coverage_mean"] for x in rows if x["mode"] == m and x["budget"] == b) for b in BUDGETS]
           for m in (B, C, D)}
    err = {UA[m]: [(next(x["ci95_low"] for x in rows if x["mode"] == m and x["budget"] == b),
                    next(x["ci95_high"] for x in rows if x["mode"] == m and x["budget"] == b)) for b in BUDGETS] for m in (B, C, D)}
    write_csv(FIGD / "fig_coverage_bcd.csv", list(rows[0]), [x for x in rows if x["mode"] in (B, C, D)])
    svg_bars(FIGS / "fig_coverage_bcd.svg", "Покриття критеріїв: B / C / D за рівного бюджету (SIMULATED)",
             "частка оцінених критеріїв", grp, ser, 0.6, err, "Вуса — 95% кластерний бутстреп-ДІ за кандидатами (n=18).")
    made.append("fig_coverage_bcd")
    # 3 P@5 and NDCG@10 by mode
    rk = []
    for mode in (A, B, C, D):
        for bud in ((None,) if mode == A else BUDGETS):
            for metric in ("p_at_5", "ndcg_at_10"):
                m = means(runs, metric, mode, bud)
                rk.append({"mode": mode, "budget": bud or "", "metric": metric, "mean": m["mean"], "ci95_low": m["ci95_low"],
                           "ci95_high": m["ci95_high"], "ground_truth": "PILOT_LLM_ANNOTATOR"})
    write_csv(FIGD / "fig_ranking_quality.csv", list(rk[0]), rk)
    groups = ["A"] + [f"{SHORT[m]} b{b}" for m in (B, C, D) for b in BUDGETS]
    keys = [(A, "")] + [(m, b) for m in (B, C, D) for b in BUDGETS]

    def pick(metric, k, field):
        return next(x[field] for x in rk if x["mode"] == k[0] and x["budget"] == k[1] and x["metric"] == metric)
    svg_bars(FIGS / "fig_ranking_quality.svg", "P@5 і NDCG@10 за режимами (еталон — пілот LLM-розмітників)", "значення",
             groups, {"P@5": [pick("p_at_5", k, "mean") for k in keys], "NDCG@10": [pick("ndcg_at_10", k, "mean") for k in keys]},
             1.0, {"P@5": [(pick("p_at_5", k, "ci95_low"), pick("p_at_5", k, "ci95_high")) for k in keys],
                   "NDCG@10": [(pick("ndcg_at_10", k, "ci95_low"), pick("ndcg_at_10", k, "ci95_high")) for k in keys]},
             "PILOT: мітки LLM-розмітників, не експерти-люди; кандидати SIMULATED; вуса — 95% бутстреп-ДІ.")
    made.append("fig_ranking_quality")
    # 4 unknown / unresolved distribution (share; whiskers = min/max of candidate means)
    ur = []
    for mode in (A, B, C, D):
        for bud in ((None,) if mode == A else BUDGETS):
            rs = [r for r in runs if r["mode_label"] == mode and (mode == A or r["total_budget"] == bud)]
            for metric, den in (("unknown_count", rs[0]["n_vacancy_relevant_criteria"]), ("unresolved_mandatory_count",
                                                                                       rs[0]["mandatory_groups_total"])):
                bc = defaultdict(list)
                for r in rs:
                    bc[r["profile_id"]].append(r[metric] / den)
                cm = [statistics.fmean(v) for v in bc.values()]
                ur.append({"mode": mode, "budget": bud or "", "metric": metric, "denominator": den,
                           "share_mean": round(statistics.fmean(cm), 4), "candidate_min": round(min(cm), 4),
                           "candidate_max": round(max(cm), 4), "status": "SIMULATED"})
    write_csv(FIGD / "fig_unknown_unresolved.csv", list(ur[0]), ur)

    def pu(metric, k, field):
        return next(x[field] for x in ur if x["mode"] == k[0] and x["budget"] == k[1] and x["metric"] == metric)
    svg_bars(FIGS / "fig_unknown_unresolved.svg", "Неоцінені критерії та невирішені обов'язкові групи (SIMULATED)", "частка",
             groups, {"неоцінені критерії (з 80)": [pu("unknown_count", k, "share_mean") for k in keys],
                      "невирішені обов'язкові групи (з 566)": [pu("unresolved_mandatory_count", k, "share_mean") for k in keys]},
             1.0, {"неоцінені критерії (з 80)": [(pu("unknown_count", k, "candidate_min"), pu("unknown_count", k, "candidate_max")) for k in keys],
                   "невирішені обов'язкові групи (з 566)": [(pu("unresolved_mandatory_count", k, "candidate_min"),
                                                             pu("unresolved_mandatory_count", k, "candidate_max")) for k in keys]},
             "Вуса — мінімум і максимум середніх за кандидатами.")
    made.append("fig_unknown_unresolved")
    # 5 confusion matrices B b50 and D b50 vs pilot levels
    mats = {}
    for mode in (B, D):
        rs = [r for r in runs if r["mode_label"] == mode and r["total_budget"] == 50 and r["pilot_level"]]
        mats[f"{UA[mode]}, бюджет 50"] = Counter((r["pilot_level"], r["level_assessed_level"]) for r in rs)
    write_csv(FIGD / "fig_level_confusion.csv", ["panel", "pilot_level", "assessed_level", "runs"],
              [{"panel": k, "pilot_level": a, "assessed_level": b, "runs": v} for k, m in mats.items() for (a, b), v in sorted(m.items())])
    svg_heatmaps(FIGS / "fig_level_confusion.svg", "Матриця рівнів: оцінювач проти пілотних міток", mats, LEVELS, LEVELS)
    made.append("fig_level_confusion")
    # 6 interview duration (stub) and questions
    du = []
    for mode in (B, C, D):
        for bud in BUDGETS:
            rs = [r for r in runs if r["mode_label"] == mode and r["total_budget"] == bud]
            du.append({"mode": mode, "budget": bud, "duration_s_median": round(statistics.median(r["total_s"] for r in rs), 3),
                       "duration_s_p95": round(sorted(r["total_s"] for r in rs)[int(0.95 * len(rs)) - 1], 3),
                       "questions_mean": round(statistics.fmean(r["n_questions"] for r in rs), 2),
                       "status": "SIMULATED (stub; not LLM latency)"})
    write_csv(FIGD / "fig_interview_duration.csv", list(du[0]), du)
    svg_bars(FIGS / "fig_interview_duration.svg", "Тривалість симульованого інтерв'ю (заглушки, не затримка LLM)", "секунд, медіана",
             grp, {UA[m]: [next(x["duration_s_median"] for x in du if x["mode"] == m and x["budget"] == b) for b in BUDGETS]
                   for m in (B, C, D)}, max(x["duration_s_median"] for x in du) * 1.2,
             note="Час процесу з детермінованими заглушками Interviewer/Evaluator у SQLite; реальна LLM не викликалась.")
    made.append("fig_interview_duration")
    _svg_lines(FIGS / "fig_questions_used.svg", "Фактично використані питання (SIMULATED)", "бюджет питань", "питань",
               {UA[m]: [(float(x["budget"]), x["questions_mean"]) for x in du if x["mode"] == m] for m in (B, C, D)}, 50.0)
    made.append("fig_questions_used")
    lv = []
    for mode in (B, C, D):
        for bud in BUDGETS:
            for metric in ("level_correct", "level_correct_pilot"):
                m = means(runs, metric, mode, bud)
                lv.append({"mode": mode, "budget": bud, "truth": "SIMULATED" if metric == "level_correct" else "PILOT_LLM_ANNOTATOR",
                           "accuracy_mean": m["mean"], "ci95_low": m["ci95_low"], "ci95_high": m["ci95_high"]})
    write_csv(FIGD / "fig_level_accuracy_vs_budget.csv", list(lv[0]), lv)
    _svg_lines(FIGS / "fig_level_accuracy_vs_budget.svg", "Збіг рівня: суцільні — пілотні мітки, «sim» — рівень генератора",
               "бюджет питань", "частка збігів",
               {**{UA[m]: [(float(x["budget"]), x["accuracy_mean"]) for x in lv if x["mode"] == m and x["truth"] != "SIMULATED"]
                   for m in (B, C, D)},
                **{f"{SHORT[m]} sim": [(float(x["budget"]), x["accuracy_mean"]) for x in lv if x["mode"] == m and x["truth"] == "SIMULATED"]
                   for m in (B, D)}}, 1.0)
    made.append("fig_level_accuracy_vs_budget")
    return made


# ---------- reports ----------
def report(runs, ann, cmp_rows, hyp, t44, t45, t46, timing, audit) -> str:
    from scripts.chapter4.report_text import evidence_report
    return evidence_report(runs=runs, ann=ann, cmp_rows=cmp_rows, hyp=hyp, t44=t44, t45=t45, t46=t46, timing=timing,
                           audit=audit, get=get, means=means, f=f, ci=ci)


def update_manifest(made: list[str], hyp: list[dict], ann) -> None:
    p = OUT / "experiment_manifest.json"
    man = json.loads(p.read_text(encoding="utf-8"))
    man["phase3"] = {
        "git_commit_product": man["frozen_config"]["commit"],
        "ground_truth_version": ann["ground_truth_version"],
        "ground_truth_note": "ADJUDICATED pilot labels from LLM_ANNOTATOR_1/2 + third pass LLM_ANNOTATOR_3; not human experts",
        "annotation_rows": ann["n_rows"],
        "result_status": {"E1": "COMPLETED (algorithm correctness)", "E2": "COMPLETED_SIMULATED",
                          "E3": "COMPUTED_PILOT_LLM_ANNOTATOR (SIMULATED candidates)",
                          "E4": "LOW_INFORMATION: templated answers, stub Evaluator; local/production LLM NOT_RUN",
                          "E5": "COMPUTED_PILOT_LLM_ANNOTATOR + SIMULATED_GROUND_TRUTH",
                          "E6": "DETERMINISTIC_MEASURED; LLM latency NOT_RUN"},
        "evaluation_set": "fixed annotated pool pool-v1 (944 pairs); run rankings restricted to the pool",
        "statistics": f"unit = candidate (n=18); cluster bootstrap {BOOT} reps, rng seed {RNG_SEED}; exact sign test",
        "hypotheses": {h["hypothesis"]: h["status"] for h in hyp},
        "figures": made, "command": "cd app && uv run python -m scripts.chapter4.build_all --phase3-only"}
    write_json(p, man)


def build() -> dict:
    runs, ann = prepare()
    cmp_rows = comparisons(runs)
    write_csv(OUT / "hypothesis_comparisons.csv", list(dict.fromkeys(k for r in cmp_rows for k in r)), cmp_rows)
    e3 = _read(OUT / "ranking_metrics.csv")
    pcd = per_candidate_diffs(e3)
    write_csv(OUT / "ranking_per_candidate_differences.csv", list(pcd[0]), pcd)
    cm = confusion(runs)
    write_csv(OUT / "level_confusion_pilot.csv", list(cm[0]), cm)
    hyp = hypotheses(cmp_rows, ann)
    write_csv(OUT / "hypotheses.csv", list(hyp[0]), hyp)
    timing_p = OUT / "raw" / "timing_e6.json"
    timing = json.loads(timing_p.read_text(encoding="utf-8")) if timing_p.exists() else None
    t44, t45, t46 = table_4_4(runs, cmp_rows), table_4_5(runs, cmp_rows), table_4_6(runs)
    write_table("table_4_1_data", "Таблиця 4.1. Характеристики даних", table_4_1(ann))
    write_table("table_4_2_conditions", "Таблиця 4.2. Умови експерименту", table_4_2())
    write_table("table_4_3_math", "Таблиця 4.3. Перевірка коректності математичного ядра (E1)", table_4_3(),
                "Джерело: mathematical_validation.csv. PARTIAL H01: H(v,p) реалізовано як фільтр за напрямом; DEVIATION R01: "
                "екран результатів сортує за відсотком першим (рішення власника), експерименти — за (2.15).")
    write_table("table_4_4_interview", "Таблиця 4.4. Порівняння режимів інтерв'ю (E2, SIMULATED; середнє за кандидатами)", t44,
                "Одиниця аналізу — кандидат (n=18), сіди усереднено; ДІ — кластерний бутстреп. Тривалість — час процесу із "
                "заглушками, не затримка LLM. B використовує не більше 20 питань (10 тем × 2 слоти).")
    write_table("table_4_5_recommendations", "Таблиця 4.5. Якість рекомендацій (E3) проти пілотних міток релевантності", t45,
                f"{PILOT_FLAG}. Оцінювання на фіксованому пулі (pool-v1, 944 пари, у середньому 52 вакансії на кандидата); "
                "ранжування прогону обмежено вакансіями пулу; вакансій пулу, відсутніх у ранжуванні, — 0 у кожному прогоні "
                "(повні 90-вакансійні ранжування). Пул сформовано з Top-10 усіх режимів + 10 випадкових — можливе зміщення пулінгу.")
    write_table("table_4_6_estimator", "Таблиця 4.6. SeniorityEstimator (E5) проти пілотних рівнів і рівнів генератора", t46,
                f"{PILOT_FLAG}. Пілотні рівні збігаються з рівнями генератора для 17 з 18 кандидатів (C04: пілот UNKNOWN, "
                "генератор JUNIOR).")
    write_table("table_4_7_technical", "Таблиця 4.7. Технічне тестування (з test_results.md) і E6", table_4_7(timing),
                "Тривалості pytest не є вимірами продуктивності. E6 — окремі повторні виміри детермінованих компонентів.")
    abl = _read(OUT / "ablation_results.csv")
    if abl:
        write_table("table_4_4b_ablation", "Таблиця 4.4б. Абляція зміни складності (D / D без зміни складності / B / C), SIMULATED",
                    [{k: r[k] for k in ("candidate_model", "total_budget", "mode_label", "n_runs", "n_questions", "graded_share",
                                        "level_correct", "difficulty_changes_overall")} for r in abl])
    made = figures(runs, cmp_rows)
    from scripts.chapter4 import self_audit
    audit = self_audit.run()
    from scripts.chapter4.report_text import missing_evidence, results_summary
    (OUT / "chapter4_evidence_report.md").write_text(report(runs, ann, cmp_rows, hyp, t44, t45, t46, timing, audit),
                                                     encoding="utf-8")
    (OUT / "chapter4_results_summary.md").write_text(results_summary(runs=runs, ann=ann, cmp_rows=cmp_rows, hyp=hyp,
                                                                     timing=timing, get=get, means=means, f=f, ci=ci),
                                                     encoding="utf-8")
    (OUT / "missing_evidence.md").write_text(missing_evidence(ann), encoding="utf-8")
    update_manifest(made, hyp, ann)
    return {"hypotheses": {h["hypothesis"]: h["status"] for h in hyp}, "comparisons": len(cmp_rows), "figures": made,
            "self_audit": audit["summary"]}


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))
