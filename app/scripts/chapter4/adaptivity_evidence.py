"""Stage 6: adaptivity mechanisms shown on the logged SIMULATED runs of scripts.chapter4.modes_experiment.

Nothing is re-run here: every example is a stored turn of raw/modes_runs.jsonl.gz (run id + sequence), so the evidence
is the product's own decisions (planner, difficulty/v2, follow-up goal, level probe) on simulated answers.
Writes adaptivity_evidence.json and adaptivity_evidence.md. Run from app/:
    uv run python -m scripts.chapter4.adaptivity_evidence
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from scripts.chapter4.common import OUT, write_csv, write_json
from scripts.chapter4.modes_experiment import load_runs

ORDER = {"BASIC": 0, "INTERMEDIATE": 1, "ADVANCED": 2}
FIG = OUT / "figures_data"


def _scores_by_turn(run: dict) -> dict[str, dict[str, float | None]]:
    """turn id -> {criterion: score} of the revisions that quote that turn (what the Evaluator read in that answer)."""
    out: dict[str, dict[str, float | None]] = defaultdict(dict)
    for rv in run["revisions"]:
        for t in rv["evidence_turns"]:
            out[t][rv["criterion_id"]] = rv["score"]
    return out


def _final(run: dict) -> dict[str, float | None]:
    return {a["criterion_id"]: a["score"] for a in run["assessments"]}


def _turn_view(t: dict, scored: dict) -> dict:
    return {"sequence": t["sequence"], "action_id": t["action_id"], "difficulty": t["difficulty"],
            "difficulty_reason": t["difficulty_reason"], "followup_reason": t["followup_reason"],
            "target_criteria": t["target_criteria"], "question_text": t["question_text"], "answer_text": t["answer_text"],
            "scores_quoting_this_answer": scored.get(t["turn_id"], {}), "eval_goal_after_answer": t["eval_goal"]}


def topic_selection(runs: list[dict]) -> dict:
    idx = {(r["profile_id"], r["mode_label"], r["total_budget"], r["seed"]): r for r in runs if r["suite"] == "modes"}
    rows, differs = [], Counter()
    for (pid, mode, bud, seed), c in sorted(idx.items(), key=lambda kv: str(kv[0])):
        if mode != "D_FULL_COMPETENCEMATCH":
            continue
        b = idx[(pid, "B_STATIC", bud, seed)]
        plan = (b["static_plan"] or {}).get("topics", [])
        c_order = list(dict.fromkeys(c["topic_sequence"]))
        b_order = list(dict.fromkeys(b["topic_sequence"]))
        k = next((i for i, (x, y) in enumerate(zip(c_order, plan)) if x != y), None)
        differs[bud, "order_differs"] += c_order != plan[:len(c_order)]
        differs[bud, "set_differs"] += set(c_order) != set(b_order)
        differs[bud, "n"] += 1
        rows.append({"profile_id": pid, "total_budget": bud, "seed": seed, "static_plan": " > ".join(plan),
                     "static_asked_topics": " > ".join(b_order), "adaptive_topics": " > ".join(c_order),
                     "adaptive_question_sequence": " > ".join(c["topic_sequence"]),
                     "first_divergence_index": "" if k is None else k,
                     "only_adaptive": " ".join(sorted(set(c_order) - set(b_order))),
                     "only_static": " ".join(sorted(set(b_order) - set(c_order)))})
    write_csv(FIG / "topic_sequences_static_vs_adaptive.csv", list(rows[0]), rows)
    by_budget = {b: {"runs": differs[b, "n"], "adaptive_order_differs_from_static_plan": differs[b, "order_differs"],
                     "topic_set_differs": differs[b, "set_differs"]}
                 for b in sorted({k[0] for k in differs})}
    # positive vs negative answers: same cohort (python), same budget/seed, different latent truth
    contrast = {}
    for pid in ("C13", "C07", "C01", "C06"):
        r = idx.get((pid, "D_FULL_COMPETENCEMATCH", 50, 0))
        if r:
            contrast[pid] = {"run_id": r["run_id"], "questions": r["n_questions"],
                             "topic_sequence": r["topic_sequence"], "questions_per_topic": r["questions_per_topic"],
                             "followup_reasons": Counter(t["followup_reason"] for t in r["turns"]).most_common()}
    static_orders = Counter(" > ".join((idx[k]["static_plan"] or {}).get("topics", [])) for k in idx
                            if k[1] == "B_STATIC" and idx[k]["track"] == "python")
    adaptive_orders = Counter(" > ".join(dict.fromkeys(idx[k]["topic_sequence"])) for k in idx
                              if k[1] == "D_FULL_COMPETENCEMATCH" and idx[k]["track"] == "python" and k[2] == 50)
    return {"by_budget": by_budget, "contrast_budget50_seed0": contrast,
            "distinct_static_plans_python": len(static_orders),
            "distinct_adaptive_topic_orders_python_budget50": len(adaptive_orders),
            "file": "figures_data/topic_sequences_static_vs_adaptive.csv"}


def difficulty_events(runs: list[dict]) -> dict:
    ev = defaultdict(list)
    for r in runs:
        if r["mode_label"] != "D_FULL_COMPETENCEMATCH" or r["suite"] not in ("modes", "ablation_sensitive"):
            continue
        scored = _scores_by_turn(r)
        ts = r["turns"]
        for a, b in zip(ts, ts[1:]):
            if a["action_id"] != b["action_id"] or a["question_source"] != "LLM_INTERVIEWER":
                continue
            da, db = ORDER[a["difficulty"]], ORDER[b["difficulty"]]
            sa = scored.get(a["turn_id"], {})
            tgt = [x for x in a["target_criteria"][:1] if x in sa]
            key = (r["suite"], r["candidate_model"])
            if db > da and (b["difficulty_reason"] or "").startswith("STRONG"):
                ev["UP_AFTER_STRONG", key].append((r, a, b, scored))
            if da == 2 and db < da and (b["difficulty_reason"] or "").startswith("WEAK"):
                weak = [c for c, s in sa.items() if s is not None and s < 0.5 and not c.startswith("practice")]
                ev["DOWN_AFTER_WEAK_ADVANCED", key].append((r, a, b, scored))
                if set(weak) & set(b["target_criteria"]):
                    ev["DOWN_AFTER_WEAK_ADVANCED_TARGETS_WEAK", key].append((r, a, b, scored))
            del tgt
    counts = {f"{k[0]}|{k[1][0]}|{k[1][1]}": len(v) for k, v in ev.items()}

    def example(kind, prefer=None):
        pool = [x for (k, key), v in ev.items() if k == kind for x in v]
        if prefer:
            pool = sorted(pool, key=lambda x: (x[0]["profile_id"] != prefer, x[0]["seed"] or 0, x[0]["total_budget"] or 0))
        if not pool:
            return None
        r, a, b, scored = pool[0]
        return {"run_id": r["run_id"], "profile_id": r["profile_id"], "candidate_model": r["candidate_model"],
                "turn": _turn_view(a, scored), "next_turn": _turn_view(b, scored)}

    # one strong topic must not raise every topic: spike profile, per topic opening/maximum difficulty
    spike = {}
    for r in runs:
        if r["profile_id"] == "C02" and r["mode_label"] == "D_FULL_COMPETENCEMATCH" and r["total_budget"] == 50 \
                and r["seed"] == 0:
            per = defaultdict(list)
            for t in r["turns"]:
                per[t["action_id"]].append(f"{t['difficulty'][0]}:{t['difficulty_reason']}")
            spike[f"{r['suite']}|{r['candidate_model']}"] = {"run_id": r["run_id"], "per_topic": dict(per),
                                                           "assessed_level": r["level_assessed_level"]}
    # desired Junior does not cap depth: P08 (latent Senior, desired junior)
    junior_cap = []
    for r in runs:
        if r["profile_id"] == "C14" and r["mode_label"] in (
                "D_FULL_COMPETENCEMATCH", "D_FIXED_DIFFICULTY", "B_STATIC") and r["suite"] in ("modes", "ablation_sensitive"):
            junior_cap.append({"run_id": r["run_id"], "suite": r["suite"], "candidate_model": r["candidate_model"],
                               "mode_label": r["mode_label"], "total_budget": r["total_budget"], "seed": r["seed"],
                               "first_reason": r["turns"][0]["difficulty_reason"] if r["turns"] else "",
                               "difficulty_mix": dict(Counter(r["difficulty_sequence"])),
                               "reached_advanced": "ADVANCED" in r["difficulty_sequence"],
                               "assessed_level": r["level_assessed_level"]})
    write_csv(FIG / "desired_junior_depth.csv", list(junior_cap[0]), junior_cap)
    summary = defaultdict(lambda: Counter())
    for x in junior_cap:
        k = f"{x['suite']}|{x['candidate_model']}|{x['mode_label']}"
        summary[k]["runs"] += 1
        summary[k]["reached_advanced"] += x["reached_advanced"]
        summary[k][f"level_{x['assessed_level']}"] += 1
    return {"event_counts": counts,
            "example_up_after_strong": example("UP_AFTER_STRONG", "C14"),
            "example_weak_on_advanced_then_diagnostic": example("DOWN_AFTER_WEAK_ADVANCED_TARGETS_WEAK",
                                                                "C11")
            or example("DOWN_AFTER_WEAK_ADVANCED", "C11"),
            "spike_profile_budget50_seed0": spike,
            "desired_junior_summary": {k: dict(v) for k, v in summary.items()},
            "file": "figures_data/desired_junior_depth.csv"}


def followup_goal(runs: list[dict]) -> dict:
    """A turn where one targeted criterion is confirmed and another is weak or ungraded, followed by a question of the
    same topic aimed at the open one; the confirmed score must survive to the end of the attempt."""
    hits, pg = [], []
    for r in runs:
        if r["mode_label"] != "D_FULL_COMPETENCEMATCH" or r["suite"] != "modes":
            continue
        scored, final = _scores_by_turn(r), _final(r)
        ts = r["turns"]
        for a, b in zip(ts, ts[1:]):
            if a["action_id"] != b["action_id"] or len(a["target_criteria"]) < 2:
                continue
            sa = scored.get(a["turn_id"], {})
            asked = a["target_criteria"][:2]
            conf = [c for c in asked if (sa.get(c) or 0) >= 0.75]
            open_ = [c for c in asked if sa.get(c) is None or sa[c] < 0.5]
            if conf and open_ and open_[0] in b["target_criteria"] and not set(conf) & set(b["target_criteria"][:2]):
                kept = all((final.get(c) or 0) >= 0.75 for c in conf)
                rec = {"run_id": r["run_id"], "profile_id": r["profile_id"], "confirmed": conf, "open": open_,
                       "open_was_ungraded": [c for c in open_ if sa.get(c) is None],
                       "confirmed_kept_to_end": kept, "final_scores": {c: final.get(c) for c in conf + open_},
                       "turn": _turn_view(a, scored), "next_turn": _turn_view(b, scored)}
                hits.append(rec)
                if a["action_id"] == "postgresql" and "postgresql.transactions" in conf and \
                        "postgresql.indexes" in open_:
                    pg.append(rec)
    pg.sort(key=lambda x: (x["profile_id"] != "C12", x["run_id"]))
    unknown = [h for h in hits if h["open_was_ungraded"]]
    return {"events": len(hits), "events_confirmed_kept_to_end": sum(h["confirmed_kept_to_end"] for h in hits),
            "events_open_criterion_ungraded": len(unknown),
            "events_by_followup_reason": dict(Counter(h["next_turn"]["followup_reason"] for h in hits)),
            "postgresql_transactions_confirmed_indexes_open": len(pg),
            "postgresql_example": pg[0] if pg else None,
            "ungraded_open_example": unknown[0] if unknown else None}


def _md(ev: dict) -> str:
    ts, de, fg = ev["6.1_topic_selection"], ev["6.2_difficulty"], ev["6.3_followup_goal"]
    L = ["# Механізми адаптивності (етап 6) — SIMULATED", "",
         "Джерело: збережені ходи прогонів `raw/modes_runs.jsonl.gz` (набір `modes` і `ablation_sensitive`), "
         "створені `scripts/chapter4/modes_experiment.py`; файл згенеровано `scripts/chapter4/adaptivity_evidence.py`. "
         "Інтерв'юер, оцінювач і кандидат — детерміновані заглушки (див. `simulation_method.md`); рішення про тему, "
         "складність і уточнення — код продукту без змін. Це перевірка поведінки механізмів, а не якості на реальних "
         "кандидатах.", "",
         "## 6.1 Вибір теми після позитивних і негативних відповідей", "",
         "| Бюджет | Пар B/C | Порядок тем C відрізняється від статичного плану B | Множина тем відрізняється |",
         "|---|---|---|---|"]
    for b, x in ts["by_budget"].items():
        L.append(f"| {b} | {x['runs']} | {x['adaptive_order_differs_from_static_plan']} | {x['topic_set_differs']} |")
    L += ["", f"Різних статичних планів на треку python: {ts['distinct_static_plans_python']}; різних порядків тем "
              f"адаптивного режиму (бюджет 50): {ts['distinct_adaptive_topic_orders_python_budget50']}. "
              "Повні послідовності: `figures_data/topic_sequences_static_vs_adaptive.csv`.", "",
          "Контраст за однакової когорти, бюджету 50 і seed 0 (адаптивний режим):", "",
          "| Профіль | run_id | Питань | Питань на тему | Причини уточнень (followup_reason) |", "|---|---|---|---|---|"]
    for pid, x in ts["contrast_budget50_seed0"].items():
        L.append(f"| {pid} | `{x['run_id']}` | {x['questions']} | `{json.dumps(x['questions_per_topic'], ensure_ascii=False)}` "
                 f"| {', '.join(f'{k}: {v}' for k, v in x['followup_reasons'])} |")
    L += ["", "## 6.2 Адаптація складності (difficulty/v2)", "", "Кількість подій (набір | модель кандидата):", ""]
    for k, v in sorted(de["event_counts"].items()):
        L.append(f"- `{k}`: {v}")
    for title, key in (("Сильна відповідь → складніше питання", "example_up_after_strong"),
                       ("Слабка відповідь на ADVANCED → діагностичне уточнення нижчого рівня",
                        "example_weak_on_advanced_then_diagnostic")):
        x = de[key]
        L += ["", f"**{title}.**", ""]
        if not x:
            L.append("У журналах немає такої події (NOT_OBSERVED).")
            continue
        for lab, t in (("хід", x["turn"]), ("наступний хід", x["next_turn"])):
            L.append(f"- `{x['run_id']}` {lab} {t['sequence']} ({t['action_id']}, {t['difficulty']}, "
                     f"причина `{t['difficulty_reason']}`), цілі `{t['target_criteria'][:2]}`, оцінки з цієї відповіді "
                     f"`{json.dumps(t['scores_quoting_this_answer'], ensure_ascii=False)}`")
    L += ["", "**Висока оцінка в одній темі не піднімає складність усіх тем** (профіль C02: сильний Python, слабкий PostgreSQL; бюджет 50, seed 0; формат `рівень:причина` для кожного питання теми):", ""]
    for k, x in de["spike_profile_budget50_seed0"].items():
        L.append(f"- `{x['run_id']}` ({k}), рівень: {x['assessed_level']}")
        for topic, seq in x["per_topic"].items():
            L.append(f"  - {topic}: {', '.join(seq)}")
    L += ["", "**Бажаний рівень Junior не обмежує глибину** (C14: латентний Senior, бажаний junior):", "",
          "| Набір / модель / режим | Прогонів | Дійшли до ADVANCED | Рівні |", "|---|---|---|---|"]
    for k, v in sorted(de["desired_junior_summary"].items()):
        lv = ", ".join(f"{a[6:]}: {b}" for a, b in sorted(v.items()) if a.startswith("level_"))
        L.append(f"| {k} | {v['runs']} | {v.get('reached_advanced', 0)} | {lv} |")
    L += ["", "## 6.3 followup_goal визначає наступне питання", "",
          f"Подій «один критерій питання підтверджено (≥ 0.75), інший слабкий (< 0.5) або без оцінки → наступне "
          f"питання тієї ж теми спрямоване на відкритий критерій»: {fg['events']}; з них підтверджена оцінка "
          f"збереглася до кінця спроби: {fg['events_confirmed_kept_to_end']}; відкритий критерій був без оцінки "
          f"(не приписаний): {fg['events_open_criterion_ungraded']}. Причини наступного питання: "
          f"`{json.dumps(fg['events_by_followup_reason'], ensure_ascii=False)}`. Випадків PostgreSQL "
          f"(transactions підтверджено, indexes відкритий): {fg['postgresql_transactions_confirmed_indexes_open']}.", ""]
    for title, x in (("Приклад PostgreSQL", fg["postgresql_example"]),
                     ("Приклад, де відкритий критерій лишився без оцінки", fg["ungraded_open_example"])):
        L += [f"**{title}.**", ""]
        if not x:
            L += ["Не спостерігалося (NOT_OBSERVED).", ""]
            continue
        for lab, t in (("хід", x["turn"]), ("наступний хід", x["next_turn"])):
            L.append(f"- `{x['run_id']}` {lab} {t['sequence']}: питання «{t['question_text']}»; цілі "
                     f"`{t['target_criteria'][:2]}`; followup_reason `{t['followup_reason']}`; оцінки з відповіді "
                     f"`{json.dumps(t['scores_quoting_this_answer'], ensure_ascii=False)}`; ціль оцінювача після "
                     f"відповіді `{json.dumps((t['eval_goal_after_answer'] or {}).get('criterion_ids'), ensure_ascii=False)}`")
        L += [f"- Підсумкові оцінки спроби: `{json.dumps(x['final_scores'], ensure_ascii=False)}`; підтверджене "
              f"збережено: {x['confirmed_kept_to_end']}.", ""]
    L += ["## 6.4 Абляція", "", "Див. `ablation_results.csv` і розділ 6.4 у `modes_report.md`."]
    return "\n".join(L) + "\n"


def build() -> dict:
    runs = load_runs()
    ev = {"label": "SIMULATED", "source": "raw/modes_runs.jsonl.gz",
          "6.1_topic_selection": topic_selection(runs), "6.2_difficulty": difficulty_events(runs),
          "6.3_followup_goal": followup_goal(runs)}
    write_json(OUT / "adaptivity_evidence.json", ev)
    (OUT / "adaptivity_evidence.md").write_text(_md(ev), encoding="utf-8")
    return ev


if __name__ == "__main__":
    e = build()
    print(json.dumps({k: (v if k != "6.2_difficulty" else v["event_counts"]) for k, v in e.items()
                      if k.startswith("6.")}, ensure_ascii=False, default=str)[:3000])
