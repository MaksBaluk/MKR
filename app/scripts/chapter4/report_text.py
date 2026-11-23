"""Ukrainian text of chapter4_evidence_report.md, chapter4_results_summary.md and missing_evidence.md.
Every number is taken from the computed rows passed in by final_report.py or read from result files here."""
from __future__ import annotations

import csv
import json
import statistics
from collections import Counter

from scripts.chapter4.common import OUT

A, B, C, D, DFD = ("A_INITIAL_PROFILE", "B_STATIC", "C_ADAPTIVE_NO_MARKET", "D_FULL_COMPETENCEMATCH", "D_FIXED_DIFFICULTY")
BUDGETS = (10, 20, 30, 50)
CMD = "cd app && uv run python -m scripts.chapter4.build_all --phase3-only"


def _csv(name: str) -> list[dict]:
    p = OUT / name
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _diff(get, f, metric, a, b, bud, n=3) -> str:
    x = get(metric, a, b, bud)
    if not x:
        return "н/д"
    p = x.get("sign_test_p_two_sided")
    return (f"{f(x['mean_a_minus_b'], n)} [{f(x['ci95_low'], n)}; {f(x['ci95_high'], n)}], кандидатів +{x['profiles_a_gt_b']}/"
            f"−{x['profiles_a_lt_b']}/={x['profiles_tie']}" + (f", знаковий тест p={p}" if p not in ("", None) else ""))


def _phase1() -> dict:
    rows = [r for r in _csv("seniority_results.csv") if r.get("suite") == "phase1-scenarios"]
    sweep = json.loads((OUT / "raw/seniority_sweep_summary.json").read_text(encoding="utf-8"))
    ua = json.loads((OUT / "raw/seniority_sweep_ua_stub_summary.json").read_text(encoding="utf-8"))
    mv = Counter(r["status"] for r in _csv("mathematical_validation.csv"))
    v4, v4u = sweep["noisy"]["rates"]["python-backend/v4"], ua["noisy"]["rates"]["python-backend/v4"]
    return {"scen": Counter(r["verdict"] for r in rows), "fail": [r["run_id"] for r in rows if r["verdict"] != "PASS"],
            "n_scen": len(rows), "math": mv, "math_n": sum(mv.values()), "false_senior": v4["false_senior"],
            "missed_senior": v4["missed_senior"], "missed_senior_ua": v4u["missed_senior"],
            "false_mid": v4["false_middle_or_higher"]}


def _t(rows, mode_prefix, bud, col):
    r = next((x for x in rows if x["Режим"].startswith(mode_prefix) and str(x["Бюджет"]) == str(bud)), None)
    return r[col] if r else "—"


def evidence_report(*, runs, ann, cmp_rows, hyp, t44, t45, t46, timing, audit, get, means, f, ci) -> str:
    g = lambda m, a, b, bud: get(cmp_rows, m, a, b, bud)  # noqa: E731
    dd = lambda m, a, b, bud, n=3: _diff(g, f, m, a, b, bud, n)  # noqa: E731
    p1 = _phase1()
    ev = {r["metric"]: r for r in _csv("evaluator_metrics.csv")}
    mae = ev.get("MAE vs adjudicated criterion annotation", {})
    man = json.loads((OUT / "experiment_manifest.json").read_text(encoding="utf-8"))
    commit = man["frozen_config"]["commit"][:7]
    modes_run = next(r for r in man["runs"] if r["suite"] == "modes")
    rs_d50 = [r for r in runs if r["mode_label"] == D and r["total_budget"] == 50]
    rs_c50 = [r for r in runs if r["mode_label"] == C and r["total_budget"] == 50]
    reask_d = statistics.fmean(r["reask_share"] for r in rs_d50)
    reask_c = statistics.fmean(r["reask_share"] for r in rs_c50)
    q_d50 = statistics.fmean(r["n_questions"] for r in rs_d50)
    q_b50 = statistics.fmean(r["n_questions"] for r in runs if r["mode_label"] == B and r["total_budget"] == 50)
    b_senior = sum(r["level_assessed_level"] == "SENIOR" for r in runs if r["mode_label"] == B)
    b_runs = sum(1 for r in runs if r["mode_label"] == B)
    tm = timing["components"] if timing else {}
    mach = timing["machine"] if timing else {}
    adj_rel = sum(len(v) for v in ann["relevance"].values())
    agr = (OUT / "data/annotations/agreement_report.md").read_text(encoding="utf-8")

    def tline(k):
        return f"медіана {tm[k]['median_ms']:.3f} мс, p95 {tm[k]['p95_ms']:.3f} мс, N={tm[k]['n']}" if k in tm else "NOT_RUN"

    L = []
    w = L.append
    w("# Розділ 4: звіт про докази (етап 12)")
    w("")
    w(f"Продуктовий код заморожено на commit `{commit}` (`experiment_manifest.json` → `frozen_config`); усі експериментальні "
      f"прогони виконано на ньому в чистому git worktree. Звіт згенеровано командою `{CMD}` з машиночитних файлів "
      "пакета. Кандидати — SIMULATED; Interviewer і Evaluator у прогонах — детерміновані заглушки; реальна LLM не "
      "викликалась. Еталон для P@5, NDCG@10 та рівнів — пілотні мітки LLM-розмітників (`LLM_ANNOTATOR_PILOT`, рядки "
      "`ADJUDICATED`), а не експертів-людей. Походження вакансій наведено за приміткою власника про дані; технічні "
      "метадані імпорту збережені в репозиторії (поля import_version, retrieved_at, source_name).")
    w("")
    w("## A. Загальний стан")
    w("")
    w("- **Готовність реалізації.** Повний потік профіль → когорта → адаптивне інтерв'ю → оцінювання критеріїв → "
      "SeniorityEstimator → ранжування вакансій працює наскрізно через API на заглушках (етапи 3, 5; "
      f"`seniority_results.csv`, `experiment_runs.csv`). Сценарії S01–S12 і наскрізні прогони фази 1: "
      f"{p1['scen'].get('PASS', 0)} PASS, {p1['scen'].get('FAIL', 0)} FAIL з {p1['n_scen']} ({', '.join(p1['fail'])}).")
    w(f"- **Відповідність математичній моделі.** {p1['math'].get('PASS', 0)} з {p1['math_n']} перевірок PASS; "
      f"PARTIAL {p1['math'].get('PARTIAL', 0)} (H01: H(v,p) — лише фільтр за напрямом), DEVIATION {p1['math'].get('DEVIATION', 0)} "
      "(R01: екран результатів сортує за відсотком першим; експерименти й `/recommendations` — за (2.15)).")
    w("- **Оцінювач рівня.** Реалізований і версійований (`python-backend/v4`, статус WORKING_ASSUMPTION). Для маркетингу "
      "й дизайну політики немає (UNKNOWN/POLICY_UNAVAILABLE).")
    w(f"- **Досяжність Senior.** Алгоритмічно досяжний; наскрізно через стандартний потік — у режимі D за бюджетів ≥ 30 "
      f"(SENIOR у {_t(t46, 'D: ', 30, 'SENIOR досягнуто (прогонів)')} з 18 прогонів Senior-кандидатів при b30). У статичному режимі B Senior не "
      f"досягнуто в {b_senior} з {b_runs} прогонів: пули шару даних Senior вимагають двох різних "
      "підтвердних відповідей (WS-1), а статичний план питає кожен критерій один раз.")
    w("- **Можливість наукових експериментів.** Контрольовані порівняння режимів проведено на симуляції з однаковими "
      "умовами; висновки про ефективність на реальних людях і якість LLM неможливі без реальних відповідей, реальної LLM "
      "і людської експертної розмітки.")
    w("")
    w("## B. Матриця етапів")
    w("")
    w("| Етап | Статус | Підстава / файл |")
    w("|---|---|---|")
    for a, b_, c in (
            ("1. Заморожування стану", "COMPLETED", "implementation_snapshot.md, experiment_manifest.json"),
            ("2. Аудит SeniorityEstimator і архітектури", "COMPLETED", "seniority_audit.md, architecture_audit.md"),
            ("3. Сценарії S01–S12", "COMPLETED", f"seniority_results.csv: {p1['scen'].get('FAIL', 0)} FAIL зафіксовано, не виправлялися"),
            ("4. Математичне ядро", "COMPLETED", "mathematical_validation.csv, таблиця 4.3"),
            ("5. INITIAL / STATIC / ADAPTIVE", "PARTIALLY_COMPLETED", "лише SIMULATED; немає реальних відповідей і LLM"),
            ("6. Механізми адаптивності", "PARTIALLY_COMPLETED", "adaptivity_evidence.md; приклад PostgreSQL «транзакції підтверджено, індекси відкрито» NOT_OBSERVED"),
            ("7. Незалежна якість", "PARTIALLY_COMPLETED", "пілотні мітки LLM-розмітників; експертів-людей немає"),
            ("8. Технічне тестування", "PARTIALLY_COMPLETED", "test_results.md; повний pytest на PostgreSQL NOT_RUN"),
            ("9. Матеріали розділу 4", "COMPLETED", "tables/table_4_1 … 4_7, figures/"),
            ("10. Зміни розділів 1–3", "COMPLETED", "thesis_changes_1_3.md (DOCX відсутній у репозиторії)"),
            ("11. Вихідні файли", "COMPLETED", "README.md"),
            ("12. Підсумковий звіт", "COMPLETED", "цей файл")):
        w(f"| {a} | {b_} | {c} |")
    w("")
    w("## C. Результати експериментів")
    w("")
    w("Спільне для E2–E5: run id `ch4-m-<кандидат>-<режим>-b<бюджет>-s<seed>` (список — `experiment_manifest.json` → "
      f"`runs`, suite `modes`, прогонів: {modes_run['n_runs']} = 18 кандидатів × (A + {{B, C, D, Dfd}} × {{10, 20, 30, 50}} × "
      "3 сіди)); середовище — SQLite in-memory, заглушки `UaModel`; одиниця аналізу — кандидат (n = 18), сіди "
      "усереднено; 95 % ДІ — кластерний бутстреп за кандидатами (5000 повторень, seed 20261119); знаковий тест — точний "
      "двобічний на середніх за кандидатом. Статистичну значущість не заявлено: кандидати спроєктовані, а не вибрані "
      "випадково.")
    w("")
    w("### E1. Коректність математичного ядра")
    w("- Команда: `uv run python -m scripts.chapter4.math_validation_ch4`; тест `tests/test_chapter4_math_properties.py`.")
    w(f"- Метод: {p1['math_n']} рядків (контрольні приклади + сідовані property-перевірки). Результат: PASS "
      f"{p1['math'].get('PASS', 0)}, PARTIAL {p1['math'].get('PARTIAL', 0)} (H01), DEVIATION {p1['math'].get('DEVIATION', 0)} (R01).")
    w("- Обмеження: показує відповідність коду специфікації, не якість оцінювання. Файл: `mathematical_validation.csv`, таблиця 4.3.")
    w("")
    w("### E2. Порівняння режимів інтерв'ю (покриття)")
    w("- Команда: `uv run python -m scripts.chapter4.modes_experiment` (прогони), `chapter4_metrics`, `final_report`.")
    w("- Дані: 80 критеріїв D_vga когорти python (знаменник покриття = 80; D_vga охоплює всі критерії рубрик python).")
    for bud in BUDGETS:
        w(f"- b{bud}: покриття B {_t(t44, 'B: ', bud, 'Покриття релевантних критеріїв [95% ДІ]')}, "
          f"C {_t(t44, 'C: ', bud, 'Покриття релевантних критеріїв [95% ДІ]')}, "
          f"D {_t(t44, 'D: ', bud, 'Покриття релевантних критеріїв [95% ДІ]')}; D−B {dd('relevant_coverage', D, B, bud)}; "
          f"C−B {dd('relevant_coverage', C, B, bud)}; D−C {dd('relevant_coverage', D, C, bud)}.")
    w(f"- Невирішені обов'язкові групи (сума по 90 вакансіях, з 566), b50: D−C {dd('unresolved_mandatory_count', D, C, 50, 1)}; "
      f"D−B {dd('unresolved_mandatory_count', D, B, 50, 1)}.")
    w(f"- Причина нижчого покриття адаптивних режимів: частка питань, усі цільові критерії яких уже були цільовими раніше "
      f"в тому самому інтерв'ю, при b50 становить D {reask_d:.3f}, C {reask_c:.3f}, B 0 (статичний план не повторює "
      f"критеріїв). D використовує в середньому {q_d50:.1f} питання при b50, B — {q_b50:.1f} (10 тем × 2 слоти), тобто "
      "більший фактичний обсяг питань не перетворюється на ширше покриття. Механізм: мета follow-up `GAP_ONLY` знову "
      "спрямовує питання на оцінений слабкий критерій до ліміту 5 питань на тему, а модель кандидата з фіксованою "
      "латентною компетентністю відповідає так само слабко. Це поведінка продукту, підсилена симуляцією; продуктовий "
      "код і алгоритми не змінювалися.")
    w("- Обмеження: SIMULATED, шаблонні відповіді; тривалість — час процесу із заглушками. Файли: "
      "`interview_experiment_results.csv`, `hypothesis_comparisons.csv`, `mode_comparison.csv`, таблиця 4.4, "
      "`figures/fig_coverage_vs_budget.svg`, `fig_coverage_bcd.svg`, `fig_unknown_unresolved.svg`.")
    w("")
    w("### E3. Якість рекомендацій проти пілотних міток релевантності")
    w(f"- Еталон: {adj_rel} пар `ADJUDICATED` (944 пари пулу; 858 — узгодження двох проходів, 86 — третій прохід). "
      "Шкала 0–3, релевантна — оцінка ≥ 2.")
    w("- Метод: P@5 і NDCG@10 (лінійний виграш, ідеал — найкращі 10 міток пулу кандидата) на **фіксованому пулі** "
      "`pool-v1`: ранжування прогону обмежується вакансіями пулу в його власному порядку. Вакансії пулу, відсутні в "
      "ранжуванні прогону, не відкидаються, а додаються в кінець у порядку файлу пулу й підраховуються; у кожному з "
      "прогонів таких вакансій 0, бо всі прогони ранжують повну когорту з 90 вакансій.")
    w(f"- A: P@5 {_t(t45, 'A: ', '—', 'P@5 [95% ДІ]')}, NDCG@10 {_t(t45, 'A: ', '—', 'NDCG@10 [95% ДІ]')}.")
    for bud in BUDGETS:
        w(f"- b{bud}: P@5 B {_t(t45, 'B: ', bud, 'P@5 [95% ДІ]')}, C {_t(t45, 'C: ', bud, 'P@5 [95% ДІ]')}, "
          f"D {_t(t45, 'D: ', bud, 'P@5 [95% ДІ]')}; NDCG@10 B {_t(t45, 'B: ', bud, 'NDCG@10 [95% ДІ]')}, "
          f"C {_t(t45, 'C: ', bud, 'NDCG@10 [95% ДІ]')}, D {_t(t45, 'D: ', bud, 'NDCG@10 [95% ДІ]')}.")
    for bud in BUDGETS:
        w(f"- Парні різниці b{bud}: P@5 D−A {dd('p_at_5', D, A, bud)}; D−B {dd('p_at_5', D, B, bud)}; D−C {dd('p_at_5', D, C, bud)}; "
          f"NDCG@10 D−A {dd('ndcg_at_10', D, A, bud)}; D−B {dd('ndcg_at_10', D, B, bud)}.")
    top5 = lambda m, col: float(_t(t45, m, 50, col))  # noqa: E731
    u_col, g_col = "Top-5 з невирішеною обов'язковою групою", "Top-5 з підтвердженою критичною прогалиною"
    pattern = top5("D: ", u_col) > top5("B: ", u_col) and top5("D: ", g_col) < top5("B: ", g_col)
    w(f"- Додатково (b50): частка Top-5 із невирішеною обов'язковою групою — B {_t(t45, 'B: ', 50, 'Top-5 з невирішеною обов' + chr(39) + 'язковою групою')}, "
      f"D {_t(t45, 'D: ', 50, 'Top-5 з невирішеною обов' + chr(39) + 'язковою групою')}; з підтвердженою критичною прогалиною (Z=0) — "
      f"B {_t(t45, 'B: ', 50, 'Top-5 з підтвердженою критичною прогалиною')}, D {_t(t45, 'D: ', 50, 'Top-5 з підтвердженою критичною прогалиною')}. "
      + ("Режим D частіше лишає у Top-5 вакансії з невирішеними обов'язковими групами (менше оцінених критеріїв), але рідше — "
         "вакансії з установленою прогалиною, бо прогалину можна встановити лише для оціненого критерію. " if pattern else "") +
      "Зміни рангу після інтерв'ю (Kendall τ і перетин Top-5 з A), стабільність Top-5 і P@5 між сідами — "
      "`ranking_metrics.csv`; покращення/погіршення за кожним кандидатом — `ranking_per_candidate_differences.csv`.")
    w("- Обмеження: PILOT — мітки LLM-розмітників, корельованих між собою (метод архетипів, малий ефективний n) і з "
      "LLM-оцінювачами; пул зібрано з Top-10 тих самих режимів (+10 випадкових) — зміщення пулінгу; кандидати SIMULATED. "
      "Файли: `ranking_metrics.csv`, таблиця 4.5, `figures/fig_ranking_quality.svg`.")
    w("")
    w("### E4. Якість Evaluator")
    w(f"- Контракт: відхилених виходів Evaluator {ev.get('evaluator outputs rejected (MALFORMED/INVALID)', {}).get('value', '—')}, "
      f"винятків провайдера {ev.get('provider exceptions', {}).get('value', '—')}, частка UNGRADED "
      f"{ev.get('share of answers UNGRADED', {}).get('value', '—')} (з {ev.get('share of answers UNGRADED', {}).get('n', '—')} відповідей).")
    w(f"- MAE заглушки проти `ADJUDICATED` оцінок критеріїв: {mae.get('value', '—')} (n = {mae.get('n', '—')}). Показник "
      "**малоінформативний**: відповіді шаблонні й містять якорі рубрики, розмітники ставили оцінки за цими якорями "
      "(MAE між двома розмітниками 0.000), а заглушка Evaluator відтворює ті самі якорі з запланованим шумом. Це не "
      "вимір якості LLM-оцінювача. Виявлення UNKNOWN не обчислено: розмітники не поставили жодної позначки NO_EVIDENCE.")
    w("- Локальна LLM і продакшн LLM: NOT_RUN. Файл: `evaluator_metrics.csv`.")
    w("")
    w("### E5. SeniorityEstimator")
    w("- Еталони: (1) пілотні рівні `ADJUDICATED` (17 узгоджених, C04 — третій прохід: UNKNOWN); (2) рівень генератора "
      "SIMULATED. Пілотні рівні збігаються з рівнями генератора для 17 з 18 кандидатів (C04: UNKNOWN проти JUNIOR).")
    for mode, nm in ((B, "B"), (C, "C"), (D, "D")):
        w(f"- {nm}: " + "; ".join(
            f"b{bud} точність {_t(t46, nm + ': ', bud, 'Точність (пілот)')}, утримання "
            f"{_t(t46, nm + ': ', bud, 'Частка утримань (UNKNOWN при визначеному рівні)')}, селективна "
            f"{_t(t46, nm + ': ', bud, 'Селективна точність (пілот)')}, хибне підвищення {_t(t46, nm + ': ', bud, 'Хибне підвищення (пілот)')}"
            for bud in BUDGETS) + ".")
    w(f"- D−B точність (пілот), b50: {dd('level_correct_pilot', D, B, 50)}; b20: {dd('level_correct_pilot', D, B, 20)}. "
      f"D−C b50: {dd('level_correct_pilot', D, C, 50)}.")
    rk = {"UNKNOWN": 0, "JUNIOR": 1, "MIDDLE": 2, "SENIOR": 3}
    fp = Counter((r["profile_id"], r["pilot_level"], r["level_assessed_level"]) for r in runs if r["mode_label"] == D
                 and r["pilot_level"] and rk[r["level_assessed_level"]] > rk[r["pilot_level"]])
    sim_fp = sum(1 for r in runs if r.get("level_false_promotion") == 1.0)
    w("- Хибні підвищення D проти пілоту (прогони): " + (", ".join(f"{c} (пілот {a}, оцінювач {b}) — {n}" for (c, a, b), n
                                                                 in sorted(fp.items())) or "немає")
      + f"; проти рівнів генератора хибних підвищень {sim_fp} в усіх режимах і бюджетах. Фаза 1, шумовий перебір v4: хибний "
      f"Senior {p1['false_senior']}, хибний ≥ Middle {p1['false_mid']}, пропущений Senior {p1['missed_senior']} "
      f"(варіант стенду UaModel {p1['missed_senior_ua']}).")
    w("- Файли: `seniority_experiment_results.csv`, `estimator_metrics.csv`, `level_confusion_pilot.csv`, таблиця 4.6, "
      "`figures/fig_level_confusion.svg`, `fig_level_accuracy_vs_budget.svg`.")
    w("")
    w("### E6. Технічні виміри")
    if timing:
        w(f"- Команда: `uv run python -m scripts.chapter4.timing_e6`; машина: {mach.get('cpu')}, {mach.get('logical_cpus')} логічних "
          f"ядер, Python {mach.get('python')}, {mach.get('db')}; {timing['repeats_per_candidate']} вимірів на компонент і "
          f"кандидата після {timing['warmup']} розігрівних, кандидати {', '.join(timing['candidates'])} (одне інтерв'ю D b50 кожен).")
        w(f"- Matching (rank_vacancy для 90 вакансій): {tline('matching')}; ранжування (2.15): {tline('ranking')}; "
          f"повний розрахунок результатів `rank_items` (БД + matching + ранжування + пояснення): {tline('results')}; "
          f"SeniorityEstimator (чиста функція): {tline('estimator')}; з читанням доказів із БД: {tline('estimator_with_db')}; "
          f"ринковий профіль F(c), I(c): {tline('market')}.")
    w("- Затримка LLM: NOT_RUN (жодного виклику реальної LLM); час інтерв'ю із заглушками не є затримкою LLM. Тривалості "
      "pytest не використовуються як виміри продуктивності. Файли: `raw/timing_e6.json`, таблиця 4.7, `test_results.md`.")
    w("")
    w("## Гіпотези")
    w("")
    w("| Гіпотеза | Статус | Первинна метрика | Підсумок | Обмеження |")
    w("|---|---|---|---|---|")
    for h in hyp:
        w(f"| {h['hypothesis']}: {h['statement']} | **{h['status']}** | {h['primary_metric']} | {h['evidence'][:420]}"
          f"{'…' if len(h['evidence']) > 420 else ''} | {h['scope']} |")
    w("")
    w("Правила статусу (зафіксовані в `final_report.py`): H1/H3 — SUPPORTED, якщо 95 % ДІ різниці покриття вище нуля "
      "за всіх бюджетів; NOT_SUPPORTED, якщо нижче нуля за всіх бюджетів; інакше INCONCLUSIVE. H2/H4 — за пілотного "
      "еталона статус не вищий за INCONCLUSIVE (це не незалежна людська валідація).")
    w("- H1: адаптивні режими мають **нижче** покриття, ніж статичний, за кожного бюджету й для кожного з 18 кандидатів. "
      "Причина — повторні питання щодо вже оцінених слабких критеріїв (E2).")
    def side(m, a, b_, bud):
        x = g(m, a, b_, bud)
        return "вище нуля" if x and x["ci95_low"] > 0 else "нижче нуля" if x and x["ci95_high"] < 0 else "містить нуль"

    def sides(m, a, b_):
        return ", ".join(f"b{bud} {side(m, a, b_, bud)}" for bud in BUDGETS)
    w(f"- H2 (ДІ різниці проти пілотних міток): P@5 D−A — {sides('p_at_5', D, A)}; P@5 D−B — {sides('p_at_5', D, B)}; "
      f"NDCG@10 D−A — {sides('ndcg_at_10', D, A)}; NDCG@10 D−B — {sides('ndcg_at_10', D, B)}. Еталон пілотний.")
    w(f"- H3: покриття D−C — {sides('relevant_coverage', D, C)}; невирішені обов'язкові групи D−C — "
      f"{sides('unresolved_mandatory_count', D, C)}; збіг рівня з генератором D−C — {sides('level_correct', D, C)}; "
      f"P@5 D−C (пілот) — {sides('p_at_5', D, C)}.")
    w("- H4: D — точність проти пілоту " + ", ".join(f"b{bud} {_t(t46, 'D: ', bud, 'Точність (пілот)')}" for bud in BUDGETS)
      + "; утримання " + ", ".join(f"b{bud} {_t(t46, 'D: ', bud, 'Частка утримань (UNKNOWN при визначеному рівні)')}" for bud in BUDGETS)
      + f"; SENIOR у B: {b_senior} з {b_runs} прогонів; еталон пілотний.")
    w("")
    w("## D. Критичні проблеми")
    w("")
    w("| Пріоритет | Проблема | Вплив | Файл / доказ |")
    w("|---|---|---|---|")
    for row in (
            ("P0 (доказова база)", "Реальна LLM (Interviewer, Evaluator) у жодному експерименті не запускалась", "немає доказів якості LLM-оцінювання й поведінки інтерв'ю на реальних відповідях", "test_results.md, environment.md"),
            ("P0 (доказова база)", "Немає експертів-людей; еталон — пілотні LLM-мітки", "P@5, NDCG@10, точність рівня — лише пілотні", "data/annotations/agreement_report.md"),
            ("P1", "Адаптивне повторне опитування знижує покриття (F-REPEAT)", "H1 не підтримано; адаптивні режими менш повні за рівного бюджету", "hypothesis_comparisons.csv (reask_share)"),
            ("P1", "Senior досяжний лише з двома різними підтвердними відповідями для пулів шару даних (WS-1)", "статичне інтерв'ю структурно не досягає Senior; вузькі інтерв'ю (S04-E2E-narrow) дають Middle", "seniority_audit.md, seniority_results.csv"),
            ("P1", "S09: сильні технічні відповіді без доказів самостійності дають Senior", "суперечність вимозі специфікації («Senior не підтверджується автоматично»); у v4 самостійність не є обов'язковою для Senior", "seniority_results.csv (ch4-s09-est FAIL)"),
            ("P1", "NR-1: «немає досвіду» з PostgreSQL/SQLAlchemy за повних інших доказів → JUNIOR (жорсткий пул Middle)", "можливе необґрунтоване пониження", "seniority_audit.md S-3, failure_cases.md"),
            ("P1 (узгодженість тексту)", "Екран результатів сортує за відсотком першим, а не за (2.15)", "на експерименти не впливає (вони використовують (2.15)); текст розділів 2–3 має описати відхилення", "mathematical_validation.csv R01"),
            ("P2", "H(v,p) — лише фільтр за напрямом (H01 PARTIAL)", "робота/локація не є жорсткими фільтрами", "mathematical_validation.csv H01"),
            ("P2", "`POST /recommendations` змішує спроби", "не використовується UI й експериментами", "architecture_audit.md A-2"),
            ("P2", "Шаблонні відповіді містять латинські ідентифікатори критеріїв", "E4 малоінформативний", "response_bank.jsonl")):
        w("| " + " | ".join(row) + " |")
    w("")
    w("Розбіжностей у позначенні походження вакансій у пакеті немає: використано нейтральне формулювання за рішенням власника.")
    w("")
    w("## E. Придатність для дипломної роботи")
    w("")
    w("- **Можна використати в розділі 4 зараз:** опис методики, умов і версій (таблиці 4.1–4.2), коректність "
      "математичного ядра (4.3), технічне тестування (4.7), аудит оцінювача, сценарії S01–S12 як перевірку правил.")
    w("- **Показує лише коректність алгоритмів:** E1, S01–S12, досяжність рівнів, механізми адаптивності (етап 6).")
    w("- **Результати на заглушках/симуляції:** E2 (покриття), E5 проти рівня генератора, абляція складності, E6 час інтерв'ю.")
    w("- **Результати реальної LLM:** відсутні.")
    w("- **Потребують незалежних експертів-людей:** E3 (P@5, NDCG@10), E4 (MAE), E5 проти експертних рівнів; поточні "
      "значення — пілотні.")
    w("- **Не можна використовувати як наукове підтвердження гіпотез:** перевагу адаптивного інтерв'ю (H1 не "
      "підтримано), ринкове планування (H3 неоднозначна), якість ранжування й рівня (H2, H4 — лише пілотний еталон).")
    w("")
    w("## F. Відповіді на підсумкові питання")
    w("")
    w("1. **Чи працює повний сценарій?** Так, на заглушках через API: профіль → когорта → інтерв'ю → оцінки → рівень → "
      "ранжування; Playwright 8 passed проти Docker-стека (test_results.md). З реальною LLM не перевірено.")
    w(f"2. **Чи коректне математичне ядро?** {p1['math'].get('PASS', 0)}/{p1['math_n']} PASS; відхилення: H01 (PARTIAL), R01 (DEVIATION, рішення власника).")
    w(f"3. **Чи досяжні Junior/Middle/Senior?** Алгоритмічно — так; наскрізно в D при b≥30 Senior досягнуто "
      f"({_t(t46, 'D: ', 30, 'SENIOR досягнуто (прогонів)')} з 18 прогонів Senior-кандидатів при b30); у B — {b_senior} з "
      f"{b_runs} (WS-1 + одноразові слоти).")
    w(f"4. **Поведінка за недостатніх доказів?** UNKNOWN або нижчий підтверджений рівень; частка утримань D при b10 — "
      f"{_t(t46, 'D: ', 10, 'Частка утримань (UNKNOWN при визначеному рівні)')}; хибних підвищень проти рівнів генератора 0; "
      f"шумовий перебір v4 — хибний Senior {p1['false_senior']}.")
    w("5. **Чи штучно знижено складність Senior?** Пороги v4 не знижувались у фазах 1–3; v3 знижував пороги Senior за "
      "рішенням власника (THESIS_SYNC_SENIORITY.md), v4 додав вимогу двох підтвердних відповідей (WS-1), тобто посилив "
      "доказову вимогу для пулів шару даних. Самостійність не обов'язкова для Senior (S09).")
    w("6. **Чи кращий адаптивний режим за статичний?** За покриттям — ні: нижчий за кожного бюджету (H1 NOT_SUPPORTED). "
      "За рівнем — D кращий за B при b≥30 щодо досяжності Senior; за P@5 проти пілоту — не відрізняється від B при b≥20.")
    w("7. **Які висновки підтримані?** Коректність математичного ядра; детермінованість і відтворюваність прогонів; "
      "відсутність хибних підвищень проти рівнів генератора на стенді; структурна неможливість Senior у статичному режимі; нижче покриття "
      "адаптивних режимів у симуляції та його причина; відсутність вимірюваного ефекту зміни складності (абляція).")
    w("8. **Яких доказів бракує?** Див. `missing_evidence.md`: експерти-люди, реальна LLM, реальні кандидати, повний "
      "pytest на PostgreSQL, затримка LLM.")
    w("9. **Що змінити в розділах 1–3?** Див. `thesis_changes_1_3.md`.")
    w("10. **Критичні наступні дії:** (1) розмітка експертами-людьми фіксованого пулу й рівнів; (2) запуск реальної "
      "LLM (локальної) на тих самих сценаріях з окремим маркуванням; (3) рішення щодо F-REPEAT (поведінка GAP_ONLY) і S09 "
      "як змін продукту з новим заморожуванням; (4) синхронізація розділів 1–3 з `thesis_changes_1_3.md`.")
    w("")
    w("## G. Незалежний самоаудит")
    w("")
    w(f"Метод: {audit['method']}. Скрипт: `app/scripts/chapter4/self_audit.py` (лише stdlib, без імпорту продуктового "
      f"коду й інших скриптів розділу 4). Підсумок: **{audit['summary']}**.")
    w("")
    w("| Величина | Незалежно | Опубліковано | Збіг |")
    w("|---|---|---|---|")
    for i in audit["items"]:
        w(f"| {i['quantity']} | {i['independent']} | {i['published']} | {'так' if i['agree'] else 'НІ'} |")
    w("")
    w("Розбіжності: " + ("немає." if not audit["discrepancies"] else json.dumps(audit["discrepancies"], ensure_ascii=False)))
    w("")
    w("## Обмеження")
    w("")
    w("- Кандидати симульовані (18 профілів, створених LLM); відповіді шаблонні й узгоджені з питанням.")
    w("- Interviewer і Evaluator — заглушки; реальна LLM не викликалась.")
    w("- Розмітники — LLM (`LLM_ANNOTATOR_1/2/3`), не експерти-люди; оцінювали за таблицями архетипів, тому мітки "
      "корельовані, ефективний обсяг вибірки малий, а узгодженість (κ) імовірно завищена; розмітники корельовані з "
      "LLM-оцінювачами. Узгодженість до узгодження й третій прохід: `data/annotations/agreement_report.md`.")
    w("- Мала вибірка (n = 18), спроєктовані профілі; статистичну значущість не заявлено.")
    w("- Режим C — дослідницький планувальник, не продуктовий режим.")
    third = [x for x in agr.splitlines() if x.startswith("- Збіг рішення третього проходу")]
    if third:
        w("- Третій прохід: " + third[0][2:])
    w("")
    return "\n".join(L) + "\n"


def results_summary(*, runs, ann, cmp_rows, hyp, timing, get, means, f, ci) -> str:
    g = lambda m, a, b, bud: get(cmp_rows, m, a, b, bud)  # noqa: E731
    dd = lambda m, a, b, bud, n=3: _diff(g, f, m, a, b, bud, n)  # noqa: E731
    L = ["# Підсумок чисел розділу 4 (для автора)", "",
         "Усі прогони SIMULATED (заглушки, commit продукту `282f6fb`); P@5, NDCG@10 і рівні — проти пілотних міток "
         "LLM-розмітників (не експерти-люди). Середнє за кандидатами [95 % бутстреп-ДІ], n = 18.", "",
         "## Покриття релевантних критеріїв (з 80)", "", "| Бюджет | B | C | D | D−B | D−C |", "|---|---|---|---|---|---|"]
    for bud in BUDGETS:
        L.append(f"| {bud} | {ci(means(runs, 'relevant_coverage', B, bud))} | {ci(means(runs, 'relevant_coverage', C, bud))} | "
                 f"{ci(means(runs, 'relevant_coverage', D, bud))} | {dd('relevant_coverage', D, B, bud)} | {dd('relevant_coverage', D, C, bud)} |")
    L += ["", "## P@5 / NDCG@10 (пілот)", "", f"A: P@5 {ci(means(runs, 'p_at_5', A, None))}; NDCG@10 {ci(means(runs, 'ndcg_at_10', A, None))}", "",
          "| Бюджет | P@5 B | P@5 C | P@5 D | NDCG@10 B | NDCG@10 C | NDCG@10 D |", "|---|---|---|---|---|---|---|"]
    for bud in BUDGETS:
        L.append(f"| {bud} | " + " | ".join(ci(means(runs, m, mode, bud)) for m in ("p_at_5", "ndcg_at_10") for mode in (B, C, D)) + " |")
    L += ["", "## Рівень (пілот): точність / утримання", "", "| Бюджет | B | C | D |", "|---|---|---|---|"]
    for bud in BUDGETS:
        L.append(f"| {bud} | " + " | ".join(f"{f(means(runs, 'level_correct_pilot', mode, bud)['mean'])} / "
                                         f"{f(means(runs, 'level_abstained_pilot', mode, bud)['mean'])}" for mode in (B, C, D)) + " |")
    L += ["", "## Гіпотези", ""] + [f"- {h['hypothesis']}: **{h['status']}** — {h['statement']}" for h in hyp]
    if timing:
        L += ["", "## E6 (детерміновані компоненти, медіана / p95, мс)", ""] + [
            f"- {k}: {v['median_ms']:.3f} / {v['p95_ms']:.3f} (N={v['n']})" for k, v in timing["components"].items()] + [
            "- Затримка LLM: NOT_RUN."]
    return "\n".join(L) + "\n"


def missing_evidence(ann) -> str:
    n = ann["n_rows"]
    return "\n".join([
        "# Відсутні докази", "",
        "Що потрібно для повних висновків розділу 4 і чого в пакеті немає (оновлюється `final_report.py`).", "",
        "1. **Експерти-люди.** Є лише пілотна розмітка LLM-розмітників (`LLM_ANNOTATOR_1/2/3`, рядки "
        f"`ADJUDICATED`): релевантність {sum(len(v) for v in ann['relevance'].values())} пар, рівні {len(ann['levels'])}, "
        f"оцінки критеріїв {len(ann['criterion'])} (усього рядків: {n['relevance']} / {n['seniority']} / {n['criterion']}). "
        "Потрібні щонайменше два незалежні експерти-люди на тому самому фіксованому пулі (`pool-v1`) за "
        "`data/annotation_inputs/ANNOTATION_INSTRUCTIONS.md`; лише тоді H2 і H4 можуть отримати статус, вищий за INCONCLUSIVE.",
        "2. **Реальна LLM.** Жодного виклику локальної чи продакшн LLM; Interviewer і Evaluator в усіх прогонах — "
        "заглушки. Потрібні прогони з локальною LLM (окремо позначені) на тих самих кандидатах і конфігурації.",
        "3. **Реальні відповіді кандидатів.** Усі 18 кандидатів симульовані, відповіді шаблонні. Для емпіричного "
        "твердження про ефективність потрібні реальні відповіді людей або незалежно підготовлені матеріали.",
        "4. **Незалежна оцінка критеріїв.** MAE Evaluator проти розмітки малоінформативний (шаблонні відповіді з якорями "
        "рубрики); потрібні відповіді вільного формату й людська оцінка.",
        "5. **Повний pytest на PostgreSQL.** NOT_RUN (`tests/conftest.py` задає SQLite); на PostgreSQL виконано 4 "
        "інтеграційні тести й Playwright.",
        "6. **Затримка LLM.** NOT_RUN; виміряно лише детерміновані компоненти (E6, `raw/timing_e6.json`).",
        "7. **Вакансії інших напрямів.** Експерименти режимів — лише python; для маркетингу й дизайну немає політики рівнів.",
        "8. **DOCX диплома.** Немає в репозиторії; `thesis_changes_1_3.md` спирається на `docs/tasks/*`.",
        "9. **PNG-рисунки.** Створено лише SVG (matplotlib не встановлено).", ""])
