#!/usr/bin/env python3
"""ТЕСТОВІ ДАНІ — ВИГАДАНІ ЧИСЛА — НЕ РЕЗУЛЬТАТИ ЕКСПЕРИМЕНТУ.
Детермінований (seed=4242) генератор МАКЕТУ пакета доказів розділу 4.
Усі числа тут згенеровані випадково; нічого не вимірювалось.
Запуск: python3 mock_generate.py  (пише файли поруч зі скриптом)."""
import itertools, math, random, statistics as st
from pathlib import Path

W = "ТЕСТОВІ ДАНІ — ВИГАДАНІ ЧИСЛА — НЕ РЕЗУЛЬТАТИ ЕКСПЕРИМЕНТУ"
OUT = Path(__file__).resolve().parent
rnd = random.Random(4242)
N = 7
PID = [f"P{i+1:02d}" for i in range(N)]
MODES = {"B": "B — статична анкета", "C": "C — адаптивне без таргетингу", "D": "D — повна система"}
BUDGETS = [3, 5, 7, 10]
f2 = lambda x: f"{x:.2f}".replace(".", ",")
f3 = lambda x: f"{x:.3f}".replace(".", ",")
f4 = lambda x: f"{x:.4f}".replace(".", ",")
clip = lambda x, lo=0.0, hi=0.97: max(lo, min(hi, x))

# ---------- generation ----------
ncrit = [rnd.randint(14, 20) for _ in range(N)]
ability = [rnd.uniform(-0.03, 0.05) for _ in range(N)]
base = {"B": (0.18, 0.032), "C": (0.20, 0.050), "D": (0.22, 0.062)}
cov = {m: {b: [clip(base[m][0] + base[m][1] * b + ability[i] + rnd.gauss(0, 0.015)) for i in range(N)]
           for b in BUDGETS} for m in MODES}
ndcg = {m: [clip(mu + rnd.gauss(0, 0.035), 0, 1) for _ in range(N)] for m, mu in (("B", .62), ("C", .70), ("D", .80))}
ndcg["D"][4] = ndcg["B"][4] - 0.015   # конструкція макета: один учасник із протилежним напрямком
p5 = {m: [round(clip(mu + rnd.gauss(0, 0.12), 0, 1) * 5) / 5 for _ in range(N)] for m, mu in (("B", .48), ("C", .58), ("D", .70))}
unr = {m: [min(ncrit[i], max(0, round(ncrit[i] * (mu + rnd.gauss(0, .06))))) for i in range(N)]
       for m, mu in (("B", .42), ("C", .27), ("D", .14))}
unr_share = {m: [unr[m][i] / ncrit[i] for i in range(N)] for m in MODES}
dur = {m: [max(5, rnd.gauss(mu, 2.2)) for _ in range(N)] for m, mu in (("B", 14), ("C", 24), ("D", 27))}
turns = [rnd.randint(21, 29) for _ in range(N)]
LAT = dict(interviewer=3.1, evaluator=5.4, python=0.04, db=0.08)
lat_rows = []
for i in range(N):
    iv = sum(max(.8, rnd.gauss(LAT["interviewer"], .7)) for _ in range(turns[i]))
    ev = sum(max(1., rnd.gauss(LAT["evaluator"], 1.1)) for _ in range(turns[i]))
    py = sum(max(.01, rnd.gauss(LAT["python"], .01)) for _ in range(turns[i]))
    db = sum(max(.01, rnd.gauss(LAT["db"], .02)) for _ in range(turns[i]))
    lat_rows.append((iv, ev, py, db))

# ---------- statistics ----------
def sign_p(pos, n):
    k = max(pos, n - pos)
    return min(1.0, 2 * sum(math.comb(n, j) for j in range(k, n + 1)) / 2 ** n)

def ranks(a):
    o = sorted(range(len(a)), key=lambda i: a[i]); r = [0.0] * len(a); i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and a[o[j + 1]] == a[o[i]]: j += 1
        for k in range(i, j + 1): r[o[k]] = (i + j) / 2 + 1
        i = j + 1
    return r

def wilcoxon(d):
    ad = [round(abs(x), 6) for x in d]; r = ranks(ad); n = len(d)
    tplus = sum(rk for rk, x in zip(r, d) if x > 0); tobs = min(tplus, sum(r) - tplus)
    cnt = tot = 0
    for s in itertools.product([0, 1], repeat=n):
        t = sum(rk for rk, b in zip(r, s) if b); tot += 1
        if min(t, sum(r) - t) <= tobs + 1e-9: cnt += 1
    return tplus, cnt / tot

def walsh_ci(d, alpha=0.05):
    n = len(d); w = sorted((d[i] + d[j]) / 2 for i in range(n) for j in range(i, n))
    cnts = {}
    for s in itertools.product([0, 1], repeat=n):
        t = sum(i + 1 for i, b in enumerate(s) if b); cnts[t] = cnts.get(t, 0) + 1
    c = -1; cum = 0
    for t in sorted(cnts):
        if 2 * (cum + cnts[t]) / 2 ** n <= alpha: cum += cnts[t]; c = t
        else: break
    conf = 1 - 2 * cum / 2 ** n; k = c + 1
    return w[k - 1], w[len(w) - k], conf, st.median(w)

def stats(d):
    pos = sum(x > 0 for x in d); tp, pw = wilcoxon(d); lo, hi, conf, hl = walsh_ci(d)
    return dict(mean=st.mean(d), sd=st.stdev(d), pos=pos, sign_p=sign_p(pos, len(d)), W=tp, p=pw,
                lo=lo, hi=hi, conf=conf, hl=hl)

def decide(s, direction=True):
    ok = s["pos"] >= 6 and s["p"] < 0.05 and (s["lo"] > 0)
    return "SUPPORTED_PILOT" if ok else "INCONCLUSIVE_PILOT"

d1 = [cov["D"][10][i] - cov["B"][10][i] for i in range(N)]
d2 = [ndcg["D"][i] - ndcg["B"][i] for i in range(N)]
d3 = [unr_share["B"][i] - unr_share["D"][i] for i in range(N)]
dd = [dur["D"][i] - dur["B"][i] for i in range(N)]
S1, S2, S3, SD = stats(d1), stats(d2), stats(d3), stats(dd)

# --- estimator vs experts (items = (participant, criterion)) ---
items = []
for i in range(N):
    for _ in range(ncrit[i]):
        e1 = min(3, max(0, round(rnd.gauss(1.6, 1.0)))); items.append(e1)
e2 = [min(3, max(0, e + rnd.choice([0, 0, 0, 0, 0, 0, 1, -1]))) for e in items]
cons = [e if a == e else rnd.choice([e, a]) for e, a in zip(items, e2)]
est, absent = [], []
for c in cons:
    if rnd.random() < 0.08: est.append(None)
    else:
        u = rnd.random(); est.append(c if u < 0.80 else min(3, max(0, c + rnd.choice([-1, 1]))))
nitems = len(items)

def wkappa(a, b, K=4):
    n = len(a); O = [[0] * K for _ in range(K)]
    for x, y in zip(a, b): O[x][y] += 1
    ra = [sum(O[i]) for i in range(K)]; cb = [sum(O[i][j] for i in range(K)) for j in range(K)]
    num = sum((i - j) ** 2 * O[i][j] for i in range(K) for j in range(K))
    den = sum((i - j) ** 2 * ra[i] * cb[j] / n for i in range(K) for j in range(K))
    return 1 - num / den

pairs = [(e, c) for e, c in zip(est, cons) if e is not None]
ea, ca = [p[0] for p in pairs], [p[1] for p in pairs]
k_exp = wkappa(items, e2); k_est = wkappa(ea, ca)
brng = random.Random(7); boots = []
for _ in range(2000):
    idx = [brng.randrange(len(pairs)) for _ in pairs]
    try: boots.append(wkappa([ea[j] for j in idx], [ca[j] for j in idx]))
    except ZeroDivisionError: pass
boots.sort(); k_lo, k_hi = boots[int(.025 * len(boots))], boots[int(.975 * len(boots))]
conf = [[0] * 4 for _ in range(4)]
for e, c in pairs: conf[c][e] += 1
acc = sum(e == c for e, c in pairs) / len(pairs)
absr = sum(e is None for e in est) / nitems
sel_acc = acc  # selective accuracy = accuracy on non-abstained
overall_acc = sum(e == c for e, c in zip(est, cons) if e is not None) / nitems
fprom = sum(e > c for e, c in pairs) / len(pairs); fdown = sum(e < c for e, c in pairs) / len(pairs)
f1s = []
for k in range(4):
    tp = conf[k][k]; fp = sum(conf[r][k] for r in range(4)) - tp; fn = sum(conf[k]) - tp
    f1s.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
macro_f1 = st.mean(f1s)
H4 = "SUPPORTED_PILOT" if (k_est >= .60 and k_lo > .40 and k_exp >= .60) else "INCONCLUSIVE_PILOT"

# ---------- rendering helpers ----------
HEAD = f"> **{W}**\n\n"
FOOT = f"\n\n---\n> **{W}**\n"
def wrap(t): return HEAD + t.strip() + FOOT
def wl(): return f"*{W}*\n"
def tbl(cap, hdr, rows, note=""):
    s = f"**{cap}**\n\n{wl()}\n| " + " | ".join(hdr) + " |\n|" + "|".join(["---"] * len(hdr)) + "|\n"
    s += "\n".join("| " + " | ".join(str(c) for c in r) + " |" for r in rows) + "\n\n" + wl()
    if note: s += f"\n{note}\n"
    return s
def put(rel, text): (OUT / rel).write_text(text, encoding="utf-8")
def mean(x): return st.mean(x)

# ---------- SVG ----------
COL = {"B": "#7a8aa0", "C": "#d19a3a", "D": "#2b7a78"}
def svg_wrap(title, cap, body, w=720, h=440):
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="Arial, sans-serif">'
            f'<rect width="{w}" height="{h}" fill="#fff"/>'
            f'<text x="{w/2}" y="16" font-size="11" fill="#b00020" font-weight="bold" text-anchor="middle">{W}</text>'
            f'<text x="{w/2}" y="40" font-size="14" font-weight="bold" text-anchor="middle">{esc(title)}</text>{body}'
            f'<text x="{w/2}" y="{h-30}" font-size="11" text-anchor="middle" fill="#333">{esc(cap)}</text>'
            f'<text x="{w/2}" y="{h-16}" font-size="10" fill="#b00020" font-weight="bold" text-anchor="middle">{W}</text>'
            f'<text x="{w/2}" y="{h-4}" font-size="10" fill="#b00020" text-anchor="middle">{W}</text></svg>')

def axes(x0, y0, x1, y1, ymax, ylab, ticks=5):
    s = f'<line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}" stroke="#333"/><line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y1}" stroke="#333"/>'
    for t in range(ticks + 1):
        v = ymax * t / ticks; y = y1 - (y1 - y0) * t / ticks
        s += f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="#ddd"/><text x="{x0-6}" y="{y+4}" font-size="10" text-anchor="end">{f2(v)}</text>'
    s += f'<text x="14" y="{(y0+y1)/2}" font-size="11" text-anchor="middle" transform="rotate(-90 14 {(y0+y1)/2})">{ylab}</text>'
    return s

def legend(x, y):
    return "".join(f'<rect x="{x}" y="{y+i*16}" width="10" height="10" fill="{COL[m]}"/><text x="{x+15}" y="{y+9+i*16}" font-size="10">{MODES[m]}</text>' for i, m in enumerate("BCD"))

def grouped(title, cap, cats, series, ymax, ylab):
    x0, y0, x1, y1 = 60, 60, 690, 340; body = axes(x0, y0, x1, y1, ymax, ylab)
    gw = (x1 - x0) / len(cats); bw = gw * .7 / len(series)
    for ci, c in enumerate(cats):
        for si, (m, vals) in enumerate(series):
            v = vals[ci]; h = (y1 - y0) * v / ymax; x = x0 + ci * gw + gw * .15 + si * bw
            body += f'<rect x="{x:.1f}" y="{y1-h:.1f}" width="{bw:.1f}" height="{h:.1f}" fill="{COL[m]}"/><text x="{x+bw/2:.1f}" y="{y1-h-3:.1f}" font-size="9" text-anchor="middle">{f2(v)}</text>'
        body += f'<text x="{x0+ci*gw+gw/2:.1f}" y="{y1+15}" font-size="10" text-anchor="middle">{c}</text>'
    return svg_wrap(title, cap, body + legend(x1 - 190, y0 - 2))

def line(title, cap, xs, series, ymax, ylab):
    x0, y0, x1, y1 = 60, 60, 690, 340; body = axes(x0, y0, x1, y1, ymax, ylab)
    px = lambda b: x0 + 40 + (x1 - x0 - 80) * (b - xs[0]) / (xs[-1] - xs[0])
    for m, vals in series:
        pts = " ".join(f"{px(b):.1f},{y1-(y1-y0)*v/ymax:.1f}" for b, v in zip(xs, vals))
        body += f'<polyline points="{pts}" fill="none" stroke="{COL[m]}" stroke-width="2.5"/>'
        body += "".join(f'<circle cx="{px(b):.1f}" cy="{y1-(y1-y0)*v/ymax:.1f}" r="3.5" fill="{COL[m]}"/>' for b, v in zip(xs, vals))
    body += "".join(f'<text x="{px(b):.1f}" y="{y1+15}" font-size="10" text-anchor="middle">{b}</text>' for b in xs)
    body += f'<text x="{(x0+x1)/2}" y="{y1+30}" font-size="11" text-anchor="middle">Бюджет: кількість тем</text>'
    return svg_wrap(title, cap, body + legend(x0 + 20, y0 + 6))

def heat(title, cap, M, labels):
    x0, y0, cs = 220, 80, 62; mx = max(max(r) for r in M) or 1; body = ""
    for r in range(4):
        body += f'<text x="{x0-8}" y="{y0+r*cs+cs/2+4}" font-size="11" text-anchor="end">експерти: {labels[r]}</text>'
        body += f'<text x="{x0+r*cs+cs/2}" y="{y0-8}" font-size="11" text-anchor="middle">оцінка: {labels[r]}</text>'
        for c in range(4):
            a = M[r][c] / mx
            body += (f'<rect x="{x0+c*cs}" y="{y0+r*cs}" width="{cs}" height="{cs}" fill="rgb({int(255-a*210)},{int(255-a*130)},{int(255-a*120)})" stroke="#fff"/>'
                     f'<text x="{x0+c*cs+cs/2}" y="{y0+r*cs+cs/2+5}" font-size="14" text-anchor="middle" fill="{"#fff" if a>.55 else "#000"}">{M[r][c]}</text>')
    return svg_wrap(title, cap, body)

# ---------- figures ----------
LV = ["0", "1", "2", "3"]
put("figures/fig_4_1_coverage_vs_budget.svg", svg_wrap.__call__ and line(
    "Рис. 4.1. Покриття рубрики залежно від бюджету тем", "Середнє по 7 учасниках; MOCK-RUN-001",
    BUDGETS, [(m, [mean(cov[m][b]) for b in BUDGETS]) for m in "BCD"], 1.0, "Покриття (частка критеріїв)"))
put("figures/fig_4_2_bcd_coverage.svg", grouped(
    "Рис. 4.2. Покриття при бюджеті 10 тем: B, C, D", "Кожна група — учасник; MOCK-RUN-001",
    PID, [(m, cov[m][10]) for m in "BCD"], 1.0, "Покриття"))
put("figures/fig_4_3_ranking_quality.svg", grouped(
    "Рис. 4.3. Якість ранжування вакансій: P@5 і NDCG@10", "Середнє по учасниках; експертна релевантність; MOCK-RUN-002",
    ["P@5", "NDCG@10"], [(m, [mean(p5[m]), mean(ndcg[m])]) for m in "BCD"], 1.0, "Значення метрики"))
bins = ["0–10 %", "10–20 %", "20–30 %", "30–40 %", "40–50 %", ">50 %"]
def hist(m):
    h = [0] * 6
    for v in unr_share[m]: h[min(5, int(v * 10 // 1 // (1 if v < .5 else 1)) if v < .5 else 5)] += 1
    return h
put("figures/fig_4_4_unresolved_distribution.svg", grouped(
    "Рис. 4.4. Розподіл частки невирішених критеріїв", "Кількість учасників у кожному інтервалі; MOCK-RUN-001",
    bins, [(m, [x / 1 for x in hist(m)]) for m in "BCD"], max(max(hist(m)) for m in "BCD") + 1, "Учасників"))
put("figures/fig_4_5_level_confusion.svg", heat(
    "Рис. 4.5. Матриця помилок рівнів (оцінка системи проти консенсусу експертів)",
    "Лише критерії без утримання; MOCK-RUN-003", conf, LV))
put("figures/fig_4_6_duration.svg", grouped(
    "Рис. 4.6. Тривалість сесії, хв (середнє ± по учасниках)", "Середня тривалість сесії за умовами; MOCK-RUN-004",
    ["Тривалість, хв"], [(m, [mean(dur[m])]) for m in "BCD"], 40, "Хвилини"))
# fix y labels for non-0..1 axes handled via ymax (ticks scale)

# ---------- tables ----------
def srow(name, s): return [name, f3(s["mean"]), f3(s["sd"]), f"{s['pos']}/{N}", f3(s["sign_p"]), f3(s["W"]).replace(",000", ",0"), f4(s["p"]), f"[{f3(s['lo'])}; {f3(s['hi'])}]", f"{s['conf']*100:.1f} %"]
SH = ["Показник", "Середня різниця", "СВ", "Напрям (+)", "p знаків", "T+", "p Вілкоксона (точний)", "Інтервал Волша", "Рівень впевн."]
put("tables/table_4_1.md", wrap(tbl("Таблиця 4.1. Склад пілоту та умови запуску (макет)",
    ["Параметр", "Значення"],
    [["Учасники-люди", f"{N} (P01–P07)"], ["Сліпі експерти", "2 (EXP-A, EXP-B)"], ["Умови", "B, C, D; внутрішньогрупове порівняння"],
     ["Бюджет", "до 10 тем, до 5 питань на тему"], ["Критеріїв на учасника", f"{min(ncrit)}–{max(ncrit)} (разом {nitems})"],
     ["Модель", "MOCK-LLM-local (локальна, умовна)"], ["Запуски", "MOCK-RUN-001…MOCK-RUN-005"], ["Seed", "4242"]])))
rows3 = [[PID[i], f3(cov["B"][10][i]), f3(cov["C"][10][i]), f3(cov["D"][10][i]), f3(d1[i])] for i in range(N)]
rows3.append(["Середнє", f3(mean(cov["B"][10])), f3(mean(cov["C"][10])), f3(mean(cov["D"][10])), f3(S1["mean"])])
put("tables/table_4_2.md", wrap(
    tbl("Таблиця 4.2. Середнє покриття рубрики за бюджетом і умовою (E1)", ["Бюджет (тем)"] + [MODES[m] for m in "BCD"],
        [[b] + [f3(mean(cov[m][b])) for m in "BCD"] for b in BUDGETS]) + "\n" +
    tbl("Таблиця 4.2б. Покриття при бюджеті 10: різниці по учасниках (D − B), H1", ["Учасник", "B", "C", "D", "D − B"], rows3) + "\n" +
    tbl("Таблиця 4.2в. Статистика H1 (n = 7)", SH, [srow("Покриття D − B", S1)])))
rows4 = [[PID[i], f3(ndcg["B"][i]), f3(ndcg["D"][i]), f3(d2[i]), f2(p5["B"][i]), f2(p5["D"][i])] for i in range(N)]
rows4.append(["Середнє", f3(mean(ndcg["B"])), f3(mean(ndcg["D"])), f3(S2["mean"]), f2(mean(p5["B"])), f2(mean(p5["D"]))])
put("tables/table_4_3.md", wrap(
    tbl("Таблиця 4.3. Якість ранжування по учасниках: NDCG@10 і P@5 (E3), H2", ["Учасник", "NDCG@10 B", "NDCG@10 D", "D − B", "P@5 B", "P@5 D"], rows4) + "\n" +
    tbl("Таблиця 4.3б. Середнє за умовами B/C/D", ["Умова", "P@5", "NDCG@10"], [[MODES[m], f2(mean(p5[m])), f3(mean(ndcg[m]))] for m in "BCD"]) + "\n" +
    tbl("Таблиця 4.3в. Статистика H2 (n = 7, основна метрика NDCG@10)", SH, [srow("NDCG@10 D − B", S2)])))
rows5 = [[PID[i], f"{unr['B'][i]}/{ncrit[i]}", f"{unr['D'][i]}/{ncrit[i]}", f3(unr_share["B"][i]), f3(unr_share["D"][i]), f3(d3[i])] for i in range(N)]
rows5.append(["Середнє", "", "", f3(mean(unr_share["B"])), f3(mean(unr_share["D"])), f3(S3["mean"])])
put("tables/table_4_4.md", wrap(
    tbl("Таблиця 4.4. Невирішені критерії по учасниках (E4), H3", ["Учасник", "Невирішено B", "Невирішено D", "Частка B", "Частка D", "B − D"], rows5) + "\n" +
    tbl("Таблиця 4.4б. Статистика H3 (зменшення частки; n = 7)", SH, [srow("Частка B − D", S3)])))
cm = [[f"експерти {LV[r]}"] + conf[r] for r in range(4)]
put("tables/table_4_5.md", wrap(
    tbl("Таблиця 4.5. Метрики оцінювача та узгодженість експертів (E5), H4", ["Метрика", "Значення"], [
        ["Елементів (учасник × критерій)", nitems], ["Зважена каппа (квадратична), EXP-A vs EXP-B", f3(k_exp)],
        ["Зважена каппа, система vs консенсус", f"{f3(k_est)} [95 % бутстреп: {f3(k_lo)}; {f3(k_hi)}]"],
        ["Точність (на не утриманих)", f3(acc)], ["Селективна точність", f3(sel_acc)], ["Частка утримань", f3(absr)],
        ["Макро-F1", f3(macro_f1)], ["Хибне підвищення", f3(fprom)], ["Хибне зниження", f3(fdown)]]) + "\n" +
    tbl("Таблиця 4.5б. Матриця помилок (рядки — консенсус, стовпці — система)", ["", "0", "1", "2", "3"], cm,
        "Примітка: бутстреп на рівні елементів не враховує кластеризацію за учасниками; інтервал оптимістичний.")))
tm = lambda i, j: mean([r[j] for r in lat_rows])
put("tables/table_4_6.md", wrap(
    tbl("Таблиця 4.6. Тривалість сесії, хв (E6)", ["Учасник"] + [MODES[m] for m in "BCD"] + ["D − B"],
        [[PID[i]] + [f"{dur[m][i]:.1f}".replace(".", ",") for m in "BCD"] + [f"{dd[i]:.1f}".replace(".", ",")] for i in range(N)] +
        [["Середнє"] + [f"{mean(dur[m]):.1f}".replace(".", ",") for m in "BCD"] + [f"{SD['mean']:.1f}".replace(".", ",")]]) + "\n" +
    tbl("Таблиця 4.6б. Статистика різниці тривалості D − B (описова; не гіпотеза)", SH, [srow("D − B, хв", SD)]) + "\n" +
    tbl("Таблиця 4.6в. Затримки локальної моделі, с на сесію (середнє по 7)", ["Складова", "Секунд/сесію", "Частка"],
        [[n, f"{tm(0,j):.1f}".replace(".", ","), f"{tm(0,j)/sum(tm(0,k) for k in range(4))*100:.1f} %"] for j, n in enumerate(["Інтерв'юер (MOCK-LLM-local)", "Оцінювач (MOCK-LLM-local)", "Python (бюджети, ранжування)", "БД / введення-виведення"])] +
        [["Разом", f"{sum(tm(0,k) for k in range(4)):.1f}".replace(".", ","), "100 %"]])))
put("tables/table_4_7.md", wrap(
    tbl("Таблиця 4.7. Підсумок технічних перевірок (макет)", ["Набір", "Всього", "Пройдено", "Провалено", "Пропущено"],
        [["Python-тести (backend)", 318, 316, 0, 2], ["Frontend: typecheck", 1, 1, 0, 0], ["Frontend: unit", 94, 94, 0, 0],
         ["Браузерний smoke", 12, 11, 0, 1], ["Міграції PostgreSQL (вгору/вниз)", 6, 6, 0, 0]],
        "Числа вигадані; реальні команди та виводи в цей макет не вставляються.") ))

# per-participant CSV
csv = [f"# {W}", "participant,ncrit,cov_B10,cov_C10,cov_D10,ndcg_B,ndcg_D,unres_B,unres_D,dur_B,dur_D"]
for i in range(N):
    csv.append(",".join(map(str, [PID[i], ncrit[i], *(round(cov[m][10][i], 4) for m in "BCD"), round(ndcg["B"][i], 4), round(ndcg["D"][i], 4), unr["B"][i], unr["D"][i], round(dur["B"][i], 2), round(dur["D"][i], 2)])))
put("MOCK_per_participant_rows.csv", "\n".join(csv) + f"\n# {W}\n")

# ---------- report ----------
def hyp(code, name, s, status, rule_extra=""):
    return (f"### {code}. {name}\n\n**Статус (макет): `{status}`**\n\n"
            f"- Напрям: {s['pos']}/{N} учасників; точний двосторонній критерій Вілкоксона p = {f4(s['p'])} (мінімум для n = 7: 0,0156); "
            f"критерій знаків p = {f3(s['sign_p'])}.\n- Середня різниця {f3(s['mean'])}; оцінка Годжеса–Лемана {f3(s['hl'])}; "
            f"інтервал Волша [{f3(s['lo'])}; {f3(s['hi'])}] (рівень {s['conf']*100:.1f} %).\n{rule_extra}"
            "- Правило рішення: ≥ 6/7 у напрямку, p Вілкоксона < 0,05 і інтервал Волша виключає 0.\n"
            "- Обмеження: n = 7, пілот; жодного висновку про генеральну сукупність.\n\n" + wl() + "\n")
rep = f"""
# Звіт доказів розділу 4 — МАКЕТ (повна форма)

**{W}**

Це вигаданий приклад «успішного» результату для власного планування автора. Не є результатами експерименту, не підлягає цитуванню в дипломній роботі.

## A. Загальний стан

Макет: пілот із 7 учасниками-людьми та 2 сліпими експертами, локальна LLM (MOCK-LLM-local), умови B, C, D. Усі гіпотези H1–H4 мають у макеті статус SUPPORTED_PILOT (H4: `{H4}`). Seed генератора 4242.

{wl()}

## B. Матриця етапів

{tbl("Таблиця B.1. Етапи та стан (макет)", ["Етап", "Стан", "Запуск"], [
 ["Підготовка когорти вакансій та ринкового профілю", "завершено", "MOCK-RUN-001"],
 ["E1 Покриття за бюджетом", "завершено", "MOCK-RUN-001"], ["E2 Покриття B/C/D", "завершено", "MOCK-RUN-001"],
 ["E3 Ранжування", "завершено", "MOCK-RUN-002"], ["E4 Невирішені критерії", "завершено", "MOCK-RUN-001"],
 ["E5 Оцінювач та експерти", "завершено", "MOCK-RUN-003"], ["E6 Тривалість і затримки", "завершено", "MOCK-RUN-004"],
 ["Технічні тести", "завершено", "MOCK-RUN-005"]])}

## C. Результати E1–E6

Середовище (вигадане): MOCK-HOST-01, 8 ядер, 32 ГБ, MOCK-LLM-local (квантизована, локально), Python 3.x, без мережі. Команди: `mock_run --exp E1` тощо (умовні, не існують).

### E1. Покриття рубрики за бюджетом (MOCK-RUN-001)
Метод: для кожного учасника в умовах B/C/D обчислено частку критеріїв із оцінкою не `null` при бюджеті 3/5/7/10 тем. Результат: при 10 темах B = {f3(mean(cov['B'][10]))}, C = {f3(mean(cov['C'][10]))}, D = {f3(mean(cov['D'][10]))} (табл. 4.2, рис. 4.1). Обмеження: 7 учасників, ефект порядку не контролювався повністю.

### E2. Покриття B/C/D (MOCK-RUN-001)
Різниці D − B по учасниках у табл. 4.2б, рис. 4.2. Усі 7 різниць додатні (середня {f3(S1['mean'])}). Обмеження: учасники-добровольці.

### E3. Ранжування вакансій (MOCK-RUN-002)
Середній NDCG@10: B {f3(mean(ndcg['B']))}, C {f3(mean(ndcg['C']))}, D {f3(mean(ndcg['D']))}; P@5 D {f2(mean(p5['D']))}. Релевантність — сліпі експерти. Табл. 4.3, рис. 4.3. Обмеження: когорта вакансій невелика; P@5 дискретна.

### E4. Невирішені критерії (MOCK-RUN-001)
Середня частка: B {f3(mean(unr_share['B']))}, C {f3(mean(unr_share['C']))}, D {f3(mean(unr_share['D']))}. Табл. 4.4, рис. 4.4.

### E5. Оцінювач проти експертів (MOCK-RUN-003)
Каппа експертів {f3(k_exp)}; каппа система/консенсус {f3(k_est)}; точність {f3(acc)}; утримання {f3(absr)}; макро-F1 {f3(macro_f1)}. Табл. 4.5, рис. 4.5. Обмеження: оцінки — це оцінки наданих відповідей, не перевірена історія роботи.

### E6. Тривалість і затримки (MOCK-RUN-004)
Середня тривалість: B {mean(dur['B']):.1f}, C {mean(dur['C']):.1f}, D {mean(dur['D']):.1f} хв. Затримка локальної моделі домінує над Python-частиною (табл. 4.6, рис. 4.6). Обмеження: одна апаратна конфігурація.

## D. Проблеми

{tbl("Таблиця D.1. Реєстр проблем (макет)", ["ID", "Пріоритет", "Опис", "Стан"], [
 ["MOCK-P0-none", "P0", "Блокуючих проблем не виявлено", "—"],
 ["MOCK-P1-01", "P1", "Один учасник (P05) має від'ємну різницю NDCG@10; причина — вузька когорта вакансій", "відкрита, описана"],
 ["MOCK-P1-02", "P1", "Бутстреп каппи не враховує кластеризацію за учасниками", "відкрита, обмеження"],
 ["MOCK-P2-01", "P2", "Подовжений час першого запиту локальної моделі (прогрів)", "прийнято"],
 ["MOCK-P2-02", "P2", "Пропущено 2 python-тести без доступного оточення", "прийнято"],
 ["MOCK-P2-03", "P2", "Орфографічна неузгодженість у двох підписах рисунків", "виправлено у макеті"]])}

## E. Придатність доказів

Для макета: докази придатні для демонстрації формату; для реальної роботи придатними були б лише виміряні дані з зафіксованими запусками. Висновки обмежені n = 7.

## F. Відповіді на 10 запитань

1. Чи виконано всі експерименти E1–E6? Так (у макеті).
2. Чи фіксуються запуски та середовище? Так, умовні MOCK-RUN-001…005.
3. Скільки учасників і експертів? 7 та 2.
4. Чи підтверджено H1? `{decide(S1)}`.
5. Чи підтверджено H2? `{decide(S2)}`.
6. Чи підтверджено H3? `{decide(S3)}`.
7. Чи підтверджено H4? `{H4}`.
8. Чи є блокуючі проблеми P0? Ні (у макеті).
9. Чи можна узагальнювати? Ні: n = 7, пілот.
10. Що ще потрібне? Див. `missing_evidence.md`.

## G. Гіпотези H1–H4

H1 — адаптивна повна система (D) дає більше покриття, ніж статична анкета (B), при бюджеті 10 тем. H2 — D дає вищий NDCG@10, ніж B. H3 — D зменшує частку невирішених критеріїв. H4 — оцінки системи узгоджені з консенсусом експертів (зважена каппа ≥ 0,60, нижня межа бутстрепу > 0,40, каппа експертів ≥ 0,60).

{hyp("H1", "Покриття D > B", S1, decide(S1))}
{hyp("H2", "NDCG@10 D > B", S2, decide(S2), "- Один учасник (P05) із протилежним напрямком — свідома риса макета.\n")}
{hyp("H3", "Менше невирішених критеріїв у D", S3, decide(S3))}
### H4. Узгодженість із експертами

**Статус (макет): `{H4}`.** Каппа експертів {f3(k_exp)}; каппа система/консенсус {f3(k_est)} [бутстреп {f3(k_lo)}; {f3(k_hi)}]. Обмеження: кластеризація не враховується; 7 учасників.

{wl()}

## Дані для відтворення макета
`mock_generate.py`, seed 4242; `MOCK_per_participant_rows.csv`.
"""
put("chapter4_evidence_report.md", wrap(rep))

put("thesis_changes_1_3.md", wrap(f"""
# Зміни до розділів 1–3 (макет)

{wl()}
- Розд. 1: уточнити постановку — вимірювання покриття рубрики та невирішених критеріїв як первинні показники.
- Розд. 2: узгодити формулювання гіпотез H1–H4 і правила рішення для n = 7 (≥ 6/7, точний Вілкоксон, інтервал Волша).
- Розд. 3: описати пілотний дизайн (7 учасників, 2 сліпі експерти, локальна модель) і обмеження узагальнення.
- Нейтральне формулювання походження вакансій без позначок типу даних.
- DOCX-файли цим макетом не редагуються.
"""))
put("missing_evidence.md", wrap(f"""
# Яких реальних доказів не вистачає (макет)

{wl()}
1. Реальні запуски зі справжніми ідентифікаторами та журналами.
2. Справжні відповіді учасників і їх згода.
3. Незалежні сліпі оцінки двох експертів і розрахунок узгодженості на реальних даних.
4. Вимірювання тривалості та затримок на реальному обладнанні.
5. Підтверджені результати технічних тестів з фактичними виводами команд.
6. Більший обсяг вибірки для будь-яких узагальнень (n = 7 дозволяє лише пілотні висновки).
"""))
put("README.md", wrap(f"""
# chapter4_mock_package — МАКЕТ

**Це МАКЕТ із вигаданими числами. Нічого не вимірювалось.** Призначений лише для особистого планування автора; не для дипломної роботи.

{wl()}
Вміст: `chapter4_evidence_report.md`, `tables/table_4_1…4_7.md`, `figures/*.svg` (6), `thesis_changes_1_3.md`, `missing_evidence.md`, `MOCK_per_participant_rows.csv`, `mock_generate.py`.
Відтворення: `python3 mock_generate.py` (seed 4242). Ідентифікатори MOCK-RUN-* вигадані й не відповідають жодним реальним артефактам.
"""))
print("H1", decide(S1), S1); print("H2", decide(S2), S2); print("H3", decide(S3), S3); print("H4", H4, k_exp, k_est, k_lo)
