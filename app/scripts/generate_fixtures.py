"""Regenerate 90 clearly fictional yet detailed vacancies + 60 actions + 120 questions.

No scraping and no third-party job text. Deterministic seed. Run from app/:
python scripts/generate_fixtures.py
"""
from __future__ import annotations
import json
import random
from pathlib import Path
from fixture_catalog import CATALOG

OUT = Path(__file__).resolve().parents[1] / "fixtures"
RNG = random.Random(20261113)

PYTHON_TITLES = [
 "Junior Python Backend Developer", "Python FastAPI Developer", "Senior Django Backend Engineer",
 "Middle Python API Engineer", "Python Automation Engineer", "Backend Python Developer — FinTech",
 "Senior Microservices Engineer (Python)", "Python Data Platform Engineer", "Junior Backend Developer (Python)",
 "Python Integration Engineer", "Senior Python Platform Engineer", "Middle Django Developer",
 "FastAPI Services Engineer", "Python Backend Engineer — E-commerce", "Lead Python Software Engineer",
 "Python Developer — Internal Tools", "Backend Engineer (Python & PostgreSQL)", "Python Developer — Logistics",
 "Senior API Infrastructure Engineer", "Python Developer — Analytics", "Python Cloud Backend Engineer",
 "Middle Python Software Developer", "Python Developer — Payments", "Backend Python Engineer — HealthTech",
 "Junior FastAPI Developer", "Python Developer — SaaS", "Senior Python Backend Developer",
 "Python Event-Driven Services Engineer", "Python Developer — Cybersecurity", "Backend Team Lead (Python)",
]
MARKETING_TITLES = [
 "Junior Digital Marketing Specialist", "Performance Marketing Manager", "Senior SEO Specialist",
 "Growth Marketing Analyst", "CRM & Lifecycle Marketing Manager", "Google Ads PPC Specialist",
 "B2B Content Marketing Manager", "Marketing Operations Specialist", "Senior Performance Marketer",
 "Social Media Marketing Specialist", "Email & Marketing Automation Specialist", "Acquisition Marketing Manager",
 "Paid Social Specialist (Meta Ads)", "SEO & Content Strategist", "Growth Marketing Lead",
 "Marketing Data Analyst", "Brand & Communications Specialist", "Conversion Rate Optimization Specialist",
 "Demand Generation Manager", "Junior PPC Specialist", "Retention Marketing Specialist",
 "E-commerce Performance Marketer", "Digital Marketing Strategist", "Senior CRM Specialist",
 "Marketing Campaign Manager", "Marketing Analytics Specialist", "Head of Growth Marketing",
 "Regional Digital Marketing Manager", "Product Marketing Specialist", "Senior Acquisition Lead",
]
DESIGN_TITLES = [
 "Junior UI/UX Designer", "Product Designer (B2B SaaS)", "Senior UX/UI Designer",
 "Visual Designer — Digital Products", "UX Researcher", "Senior Product Designer",
 "Brand & Digital Designer", "Interaction Designer", "Design System Specialist",
 "Mobile App Product Designer", "UI Designer — FinTech", "Product Design Lead",
 "UX Designer — E-commerce", "Visual Communication Designer", "Junior Product Designer",
 "Senior UX Researcher", "Motion & UI Designer", "Digital Experience Designer",
 "UX/UI Designer — HealthTech", "Marketing Visual Designer", "Design Systems Lead",
 "Product Designer — Analytics", "Mobile Interaction Designer", "Web & UX Designer",
 "Creative Brand Designer", "Senior UI Designer", "Accessibility-focused Product Designer",
 "UX Architect", "Design Research & Strategy Specialist", "Lead Product Designer",
]
TITLES = {"python": PYTHON_TITLES, "marketing": MARKETING_TITLES, "design": DESIGN_TITLES}

FICTIONAL_COMPANIES = [
 "Northbridge Labs", "Clearpath Digital", "Sparrow Systems", "Mosaic Venture Studio", "Orbitly Products",
 "Amberfield Tech", "BluePeak Analytics", "Riverton Works", "Cobalt Harbor", "Mellor Commerce",
 "Sequoia Loop", "BrightCurrent", "Atlasberry Studio", "Ninefold Cloud", "Vertex Harbor",
 "Dawnside Products", "NovaRidge Digital", "Lighthouse Metric", "Mintline Labs", "Fairway Foundry",
 "Everglow Systems", "Pilotwave", "Prismfield", "PointNorth Labs", "Glacierbox",
 "Fablebyte", "Octave Signal", "Kitepath Group", "Tideframe", "Bluefox Platform",
]
SECTORS = [
 "B2B SaaS", "FinTech", "e-commerce", "HealthTech", "EdTech", "логістичних сервісів",
 "martech", "аналітичної платформи", "HR Tech", "marketplace", "медіасервісів", "інструментів для команд",
]
LOCATIONS = [("Remote — Europe", "REMOTE"), ("Kyiv", "HYBRID"), ("Lviv", "HYBRID"),
             ("Remote — Ukraine", "REMOTE"), ("Warsaw", "HYBRID"), ("Kyiv", "OFFICE")]
SENIORITY = ["JUNIOR", "MIDDLE", "SENIOR", "MIDDLE", "LEAD", "SENIOR", "MIDDLE", "JUNIOR", "MIDDLE", "SENIOR"]
YEARS = {"JUNIOR": (0, 2), "MIDDLE": (2, 5), "SENIOR": (4, 8), "LEAD": (6, None)}
SALARY = {"python": {"JUNIOR": (900, 1800), "MIDDLE": (2100, 3600), "SENIOR": (3700, 5800), "LEAD": (5000, 7200)},
          "marketing": {"JUNIOR": (650, 1200), "MIDDLE": (1500, 2600), "SENIOR": (2600, 4000), "LEAD": (3700, 5300)},
          "design": {"JUNIOR": (650, 1250), "MIDDLE": (1550, 2700), "SENIOR": (2800, 4200), "LEAD": (3900, 5600)}}
INTRO = {
 "python": "Ми будуємо надійні серверні сервіси для {sector} та поступово збільшуємо навантаження. Команда працює невеликими ітераціями, підтримує культуру code review, автоматизованих перевірок і прозорих технічних рішень. Ця роль передбачає вплив на API-контракти, стабільність сервісів та якість даних.",
 "marketing": "Команда розвиває продукт у сегменті {sector} і приймає маркетингові рішення на основі даних. Ми шукаємо людину, яка вміє поєднувати гіпотези, акуратне вимірювання та зрозумілу комунікацію результатів. Важливі якість експериментів, відповідальність за бюджети й співпраця з продуктовою командою.",
 "design": "Ми створюємо цифровий продукт для {sector} зі складними сценаріями використання. Дизайн-команда працює разом із дослідниками, розробниками та продуктовими менеджерами. Ми цінуємо доступність, уважність до деталей, аргументовані рішення та послідовний дизайн у різних точках взаємодії.",
}
RESPONSIBILITIES = {
 "python": [
  "Проєктувати й підтримувати REST API з передбачуваним контрактом помилок і версіонуванням.",
  "Оптимізувати запити до бази даних, індекси та межі транзакцій.",
  "Писати модульні й інтеграційні тести для критичних бізнес-сценаріїв.",
  "Брати участь у code review та пояснювати компроміси між простотою і масштабованістю.",
  "Підтримувати контейнеризацію, конфігурацію оточень і pipeline доставки.",
  "Спостерігати за метриками API та локалізувати першопричини інцидентів.",
  "Працювати з подієвими інтеграціями і повторними повідомленнями без дублювання операцій.",
  "Узгоджувати схеми даних, API-контракти та стратегію міграцій з іншими командами.",
 ],
 "marketing": [
  "Будувати план експериментів, KPI та систему оцінювання ефективності каналів.",
  "Збирати й інтерпретувати аналітику кампаній із прозорою атрибуцією.",
  "Координувати створення рекламних креативів та узгоджувати повідомлення для сегментів.",
  "Оптимізувати воронки, landing pages і комунікації протягом життєвого циклу клієнта.",
  "Працювати з CRM-даними, UTM-мітками та якістю подій аналітики.",
  "Підготовлювати регулярні звіти про CAC, ROAS та conversion rate.",
  "Тестувати позиціонування й комунікації з продуктовими та sales-командами.",
  "Формувати гіпотези на основі дослідження ринку й конкурентних рішень.",
 ],
 "design": [
  "Досліджувати проблеми користувачів та будувати зрозумілі user flows.",
  "Створювати вайрфрейми, клікабельні прототипи та фінальні UI-макети.",
  "Підтримувати дизайн-систему, адаптивність і доступність інтерфейсів.",
  "Проводити рев'ю рішень із розробниками та документувати стани компонентів.",
  "Готувати та аналізувати юзабіліті-тести, формулювати наступні ітерації.",
  "Працювати з типографікою, візуальною ієрархією та складними таблицями даних.",
  "Презентувати рішення стейкхолдерам та аргументувати вибір даними.",
  "Підготовлювати графічні матеріали з урахуванням технічних обмежень вебу.",
 ],
}
BENEFITS = [
 "Гнучкий робочий графік і прозорі очікування щодо результатів.",
 "Оплачуване навчання, професійні конференції та внутрішні knowledge-sharing сесії.",
 "Командна підтримка, регулярний feedback і можливість впливати на продукт.",
 "Оплачувана відпустка та зрозумілий процес онбордингу.",
 "Сучасне робоче обладнання та бюджет на професійні інструменти.",
 "Культура асинхронної комунікації та документації ключових рішень.",
 "Можливість брати участь у релізах від discovery до ретроспективи.",
]
ROLE_FOCUS = {
 "python": ["fastapi", "django", "postgresql", "sql", "sqlalchemy", "docker", "aws", "celery", "async-python", "git", "rest-api", "app-security"],
 "marketing": ["google-ads", "meta-ads", "ga4", "seo", "crm", "cro", "email-marketing", "performance-marketing", "content-strategy", "ab-testing", "segmentation"],
 "design": ["figma", "ui-design", "ux-research", "design-systems", "prototyping", "accessibility", "visual-design", "usability-testing", "responsive-design", "interaction-design"],
}
ALTERNATIVE_PAIRS = {
 "python": [("fastapi", "django"), ("redis", "kafka"), ("pytest", "ci-cd")],
 "marketing": [("google-ads", "meta-ads"), ("ga4", "looker-studio"), ("seo", "content-strategy")],
 "design": [("figma", "illustrator"), ("ux-research", "usability-testing"), ("ui-design", "visual-design")],
}

def write_json(name, content):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build():
    competencies = []
    questions = {}
    for track, entries in CATALOG.items():
        for cid, en, uk, summary, question, options, answer_index, scenario in entries:
            competencies.append({"id": cid, "label": en, "label_uk": uk, "track": track, "summary": summary,
                                 "aliases": [en.casefold(), uk.casefold()], "catalog_version": "local-curated-v1"})
            questions[cid] = [
                {"id": f"{cid}-mcq-v1", "kind": "MULTIPLE_CHOICE", "text": question,
                 "options": [{"id": chr(97+i), "text": o} for i, o in enumerate(options)],
                 "correct_option": chr(97+answer_index), "rubric_version": "demo-task-v1"},
                {"id": f"{cid}-scenario-v1", "kind": "FREE_TEXT", "text": scenario,
                 "options": [], "correct_option": None, "rubric_version": "human-review-v1"},
            ]
    by_id = {c["id"]: c for c in competencies}
    vacancies = []
    for track, titles in TITLES.items():
        available = [c["id"] for c in competencies if c["track"] == track]
        for index, title in enumerate(titles):
            slug = f"{track}-{index+1:02d}"
            seniority = SENIORITY[index % len(SENIORITY)]
            years_min, years_max = YEARS[seniority]
            company = FICTIONAL_COMPANIES[(index + (0 if track=="python" else 9 if track=="marketing" else 17)) % len(FICTIONAL_COMPANIES)]
            sector = SECTORS[(index*3 + len(track)) % len(SECTORS)]
            location, work_mode = LOCATIONS[(index * 5 + len(track)) % len(LOCATIONS)]
            required_level = 1 if seniority == "JUNIOR" else (2 if seniority == "MIDDLE" else 3)
            focus = [c for c in ROLE_FOCUS[track] if c in available]
            RNG.shuffle(focus)
            core = focus[:5]
            remaining = [c for c in available if c not in core]
            RNG.shuffle(remaining)
            must = core + remaining[:2]
            desired = [c for c in remaining[2:] if c not in must][:3]
            pair = ALTERNATIVE_PAIRS[track][index % len(ALTERNATIVE_PAIRS[track])]
            # An OR group is one logical requirement, not two mandatory requirements.
            groups = []
            for j, action in enumerate(must):
                lvl = min(3, max(1, required_level - int(j in (5, 6))))
                label = f"Досвід з {by_id[action]['label']}: {by_id[action]['summary']} (рівень від {lvl}/3)."
                groups.append({"id": f"{slug}-g{len(groups)+1:02d}", "kind": "MANDATORY", "label": label,
                               "excerpt": label, "alternatives": [{"competency_id": action, "required_level": lvl,
                                                                    "normalization_status": "ACCEPTED_CURATED"}]})
            pair_level = min(required_level, 2)
            orlabel = f"Практичний досвід хоча б з одного інструмента: {by_id[pair[0]]['label']} або {by_id[pair[1]]['label']} (рівень від {pair_level}/3)."
            groups.append({"id": f"{slug}-g{len(groups)+1:02d}", "kind": "MANDATORY", "label": orlabel,
                           "excerpt": orlabel, "alternatives": [{"competency_id": x, "required_level": pair_level,
                                                                  "normalization_status": "ACCEPTED_CURATED"} for x in pair]})
            for j, action in enumerate(desired):
                label = f"Буде перевагою: {by_id[action]['label']} — {by_id[action]['summary']}"
                groups.append({"id": f"{slug}-g{len(groups)+1:02d}", "kind": "DESIRED", "label": label,
                               "excerpt": label, "alternatives": [{"competency_id": action,
                                                                    "required_level": max(1, required_level-1),
                                                                    "normalization_status": "ACCEPTED_CURATED"}]})
            tasks = RNG.sample(RESPONSIBILITIES[track], 6)
            perks = RNG.sample(BENEFITS, 4)
            stack = list(dict.fromkeys([by_id[alt["competency_id"]]["label"] for g in groups
                                        for alt in g["alternatives"]]))
            salary_start, salary_end = SALARY[track][seniority]
            salary_min = salary_start + (index % 4) * 75
            salary_max = salary_end + (index % 5) * 100
            about = INTRO[track].format(sector=sector)
            summary = f"{title} у команді {company}: {sector}, {location.lower()}, {seniority.lower()} рівень. " + about.split(". ")[0] + "."
            text = "\n".join([
                f"{title} | {company}", "", "Про команду", about,
                "", "Завдання на посаді", *[f"- {task}" for task in tasks],
                "", "Обов'язкові вимоги", *[f"- {g['label']}" for g in groups if g["kind"] == "MANDATORY"],
                "", "Буде перевагою", *[f"- {g['label']}" for g in groups if g["kind"] == "DESIRED"],
                "", "Умови та підтримка", *[f"- {benefit}" for benefit in perks],
                "", f"Досвід: від {years_min} років (не виводимо з рівня технологій).",
                f"Локація: {location}. Формат: {work_mode}. Зайнятість: Full-time.",
                f"Орієнтовна компенсація: {salary_min}–{salary_max} USD на місяць.",
                "", "Це авторська демонстраційна вакансія для навчального MVP; вона не є реальною публікацією роботодавця.",
            ])
            vacancies.append({"id": slug, "track": track, "title": title, "company": company,
                              "seniority": seniority, "years_min": years_min, "years_max": years_max,
                              "location": location, "work_mode": work_mode, "employment": "Full-time",
                              "salary_min": salary_min, "salary_max": salary_max, "currency": "USD",
                              "summary": summary, "description": text, "responsibilities": tasks,
                              "benefits": perks, "stack": stack, "source_type": "DEMO_CURATED", "source_url": None,
                              "fixture_version": "fixtures-v1", "groups": groups})
            assert len(groups) >= 10 and len(text) > 1300
            assert all(g["excerpt"] in text for g in groups)
    assert len(competencies) == 60 and len(vacancies) == 90 and len(questions) == 60
    assert all(len(qs) == 2 for qs in questions.values())
    assert all(sum(v["track"] == t for v in vacancies) == 30 for t in TITLES)
    write_json("competencies.json", competencies)
    write_json("vacancies.json", vacancies)
    write_json("questions.json", questions)
    print(f"Generated {len(vacancies)} vacancies, {len(competencies)} actions, {sum(map(len, questions.values()))} questions")


if __name__ == "__main__":
    build()
