"""fixtures-v2: append 90 synthetic vacancies (30 per track), curated-template rubrics and extra questions.

Run from app/ AFTER generate_fixtures.py (which rewrites the 90 fixtures-v1 records):
    python scripts/generate_fixtures_v2.py

Deterministic (per-vacancy seeded RNG, fixed tables). Existing fixtures-v1 vacancies and existing questions are
kept byte-for-byte; only fixtures-v2 records and *-v2 questions are (re)generated. Companies and postings are
invented (source_type SYNTHETIC_GENERATED); nothing is scraped or copied from job boards.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from fixture_content_v2 import QUESTIONS_V2, RUBRICS, build_rubric

OUT = Path(__file__).resolve().parents[1] / "fixtures"
VERSION = "fixtures-v2"

# (title, seniority, archetype, domain)
TITLES = {
 "python": [
  ("Junior Python Developer (Logistics Platform)", "JUNIOR", "api", "logistics"),
  ("Python Backend Engineer — Payments", "MIDDLE", "api", "fintech"),
  ("Senior Python Engineer (Data Pipelines)", "SENIOR", "data", "retail"),
  ("Middle Django Developer — EdTech", "MIDDLE", "django", "edtech"),
  ("Lead Backend Engineer (Python)", "LEAD", "api", "insurtech"),
  ("Python Platform Engineer", "MIDDLE", "platform", "cloud"),
  ("Junior Django Developer", "JUNIOR", "django", "media"),
  ("Senior FastAPI Engineer", "SENIOR", "async", "travel"),
  ("Python Developer — Energy Analytics", "MIDDLE", "data", "energy"),
  ("Site Reliability Engineer (Python)", "SENIOR", "platform", "telecom"),
  ("Middle Python Engineer — Marketplace", "MIDDLE", "async", "marketplace"),
  ("Application Security Engineer (Python)", "SENIOR", "security", "govtech"),
  ("Junior Backend Engineer — HealthTech", "JUNIOR", "api", "healthtech"),
  ("Senior Django Engineer — B2B SaaS", "SENIOR", "django", "saas"),
  ("Python Integration Developer", "MIDDLE", "async", "hr"),
  ("Data Engineer (Python, Kafka)", "SENIOR", "data", "adtech"),
  ("Junior QA Automation Engineer (Python)", "JUNIOR", "qa", "edtech"),
  ("Middle Python Developer — AgriTech", "MIDDLE", "api", "agritech"),
  ("Lead Platform Engineer", "LEAD", "platform", "saas"),
  ("Senior Python Backend Engineer — Insurance", "SENIOR", "django", "insurtech"),
  ("Middle Async Python Developer", "MIDDLE", "async", "media"),
  ("Python Developer — Smart City", "MIDDLE", "data", "govtech"),
  ("Junior Python Engineer — Data Tools", "JUNIOR", "data", "analytics"),
  ("Senior Backend Engineer — Real-time Messaging", "SENIOR", "async", "telecom"),
  ("Python DevOps Engineer", "MIDDLE", "platform", "retail"),
  ("Head of Backend Engineering (Python)", "LEAD", "api", "marketplace"),
  ("Backend Developer — Cybersecurity Tools", "MIDDLE", "security", "cybersecurity"),
  ("Senior QA Automation Engineer (Python)", "SENIOR", "qa", "healthtech"),
  ("Python Engineer — Rental Platform", "MIDDLE", "async", "proptech"),
  ("Lead Python Engineer — FinTech Core", "LEAD", "django", "fintech"),
 ],
 "marketing": [
  ("Junior Performance Marketing Specialist", "JUNIOR", "performance", "ecommerce"),
  ("PPC Specialist (Google Ads)", "MIDDLE", "performance", "travel"),
  ("Senior Paid Social Manager", "SENIOR", "performance", "apps"),
  ("SEO Specialist — Marketplace", "MIDDLE", "seo", "marketplace"),
  ("Content Marketing Lead", "LEAD", "seo", "saas"),
  ("Junior SEO & Content Specialist", "JUNIOR", "seo", "edtech"),
  ("CRM Marketing Manager", "MIDDLE", "crm", "retail"),
  ("Lifecycle Marketing Lead", "LEAD", "crm", "fintech"),
  ("Marketing Analyst", "MIDDLE", "analytics", "saas"),
  ("Senior Web Analyst", "SENIOR", "analytics", "ecommerce"),
  ("Growth Marketing Manager", "MIDDLE", "growth", "apps"),
  ("Conversion Optimization Lead", "LEAD", "growth", "ecommerce"),
  ("Brand Marketing Manager", "MIDDLE", "brand", "foodtech"),
  ("Social Media Manager", "MIDDLE", "brand", "media"),
  ("Junior SMM Specialist", "JUNIOR", "brand", "retail"),
  ("Email Marketing Specialist", "JUNIOR", "crm", "edtech"),
  ("Marketing Automation Specialist", "MIDDLE", "crm", "saas"),
  ("Senior Performance Marketing Manager", "SENIOR", "performance", "fintech"),
  ("Junior Marketing Analyst", "JUNIOR", "analytics", "logistics"),
  ("Senior Technical SEO Specialist", "SENIOR", "seo", "travel"),
  ("Product Marketing Manager", "MIDDLE", "research", "saas"),
  ("Senior Growth Marketer", "SENIOR", "growth", "healthtech"),
  ("Digital Marketing Specialist — B2B", "MIDDLE", "performance", "manufacturing"),
  ("Senior Brand Strategist", "SENIOR", "brand", "fashion"),
  ("Junior Copywriter", "JUNIOR", "seo", "media"),
  ("Head of Performance Marketing", "LEAD", "performance", "ecommerce"),
  ("Market Research Analyst", "MIDDLE", "research", "healthtech"),
  ("Senior CRM Analyst", "SENIOR", "crm", "telecom"),
  ("Attribution & Measurement Specialist", "SENIOR", "analytics", "adtech"),
  ("Junior Paid Search Specialist", "JUNIOR", "performance", "proptech"),
 ],
 "design": [
  ("Junior Product Designer", "JUNIOR", "product", "edtech"),
  ("Product Designer — Mobile Banking", "MIDDLE", "mobile", "fintech"),
  ("Senior Product Designer — Logistics", "SENIOR", "product", "logistics"),
  ("UX Researcher", "MIDDLE", "research", "healthtech"),
  ("Lead UX Researcher", "LEAD", "research", "saas"),
  ("UI Designer", "MIDDLE", "ui", "ecommerce"),
  ("Junior UI Designer", "JUNIOR", "ui", "media"),
  ("Design System Designer", "SENIOR", "ds", "saas"),
  ("Lead Product Designer — Marketplace", "LEAD", "product", "marketplace"),
  ("Brand Designer", "MIDDLE", "brand", "foodtech"),
  ("Junior Graphic Designer", "JUNIOR", "brand", "retail"),
  ("Motion Designer", "MIDDLE", "mobile", "apps"),
  ("Senior Interaction Designer", "SENIOR", "mobile", "travel"),
  ("Accessibility Designer", "SENIOR", "ds", "govtech"),
  ("UX/UI Designer — AgriTech", "MIDDLE", "product", "agritech"),
  ("Product Designer — HR Tech", "MIDDLE", "product", "hr"),
  ("Junior UX Researcher", "JUNIOR", "research", "edtech"),
  ("Senior Visual Designer", "SENIOR", "ui", "fashion"),
  ("Web Designer", "MIDDLE", "ui", "proptech"),
  ("Design Systems Lead", "LEAD", "ds", "fintech"),
  ("Mobile UI/UX Designer", "MIDDLE", "mobile", "healthtech"),
  ("Senior UX Designer — Energy", "SENIOR", "product", "energy"),
  ("Creative Lead (Brand)", "LEAD", "brand", "media"),
  ("Information Architect", "SENIOR", "research", "insurtech"),
  ("Junior Web Designer", "JUNIOR", "ui", "travel"),
  ("Product Designer — Data Visualization", "MIDDLE", "product", "analytics"),
  ("Illustrator & Visual Designer", "MIDDLE", "brand", "gaming"),
  ("Senior Mobile Designer", "SENIOR", "mobile", "telecom"),
  ("Service Designer", "MIDDLE", "research", "cloud"),
  ("Junior Motion & UI Designer", "JUNIOR", "mobile", "apps"),
 ],
}

COMPANIES = {
 "python": ["Halyard Systems", "Quillon Labs", "Larchway Tech", "Corvid Cloud", "Stonemere Software",
            "Wrenfield Systems", "Ironleaf Labs", "Saltmarsh Tech", "Juniper Grid", "Ferncastle Software",
            "Brightwell Systems", "Cinderpath Labs", "Tallowmere Tech", "Greyhaven Cloud", "Oakhollow Software",
            "Lumenreach Systems", "Driftmark Labs", "Highcairn Tech", "Marrowgate Cloud", "Swiftbarrow Software",
            "Pinecrest Logic", "Emberline Systems", "Coldspring Labs", "Ravenmoor Tech", "Westerly Data",
            "Mistral Forge", "Thornbury Systems", "Glassridge Labs", "Quarrystone Tech", "Starling Ledger"],
 "marketing": ["Mapleleaf Commerce", "Sunhaven Group", "Copperline Media", "Velvet Harbor Retail", "Bluestem Brands",
               "Orchard Lane Commerce", "Fieldfare Group", "Hazelnut Media", "Brightmoor Retail", "Saffron Street Brands",
               "Kindling Commerce", "Merrow Group", "Paperkite Media", "Rosewater Retail", "Tumbleweed Brands",
               "Cloverfield Commerce", "Seabright Group", "Lanternfly Media", "Honeycomb Retail", "Wildthyme Brands",
               "Ashgrove Commerce", "Marigold Group", "Snowberry Media", "Pebblebrook Retail", "Goldcrest Brands",
               "Dovetail Commerce", "Larkspur Group", "Teabrook Media", "Cobblestone Retail", "Bluebell Brands"],
 "design": ["Inkwell Studio", "Papercut Digital", "Fernlight Products", "Moonwake Studio", "Palette & Pine",
            "Linden Interactive", "Quietform Studio", "Harbourlight Digital", "Sketchwell Products", "Tidepool Studio",
            "Brushfield Digital", "Northlight Interactive", "Pixelgrove Studio", "Clearwater Products",
            "Graphite Hill Digital", "Kiteflyer Studio", "Morrow Interactive", "Saltglass Products", "Openfield Studio",
            "Willowmark Digital", "Arclight Products", "Featherstone Studio", "Riverglass Interactive",
            "Lumen Lane Digital", "Quarterlight Studio", "Silkthread Products", "Halftone Interactive",
            "Cedarline Studio", "Blueprint Bay Digital", "Gridwise Products"],
}

DOMAINS = {
 "logistics": ("логістика", "{company} розробляє платформу для планування доставок і керування складами, якою користуються перевізники в Україні та Польщі."),
 "fintech": ("фінтех", "{company} створює платіжні та банківські сервіси для малого бізнесу й приватних клієнтів."),
 "retail": ("ритейл", "{company} розвиває омніканальну платформу для мережі магазинів побутових товарів."),
 "edtech": ("освітні технології", "{company} створює онлайн-платформу для навчання школярів і підготовки до іспитів."),
 "insurtech": ("страхування", "{company} переводить страхові послуги в цифровий формат: від розрахунку поліса до врегулювання збитків онлайн."),
 "cloud": ("хмарні сервіси", "{company} надає хмарну інфраструктуру та інструменти розгортання для продуктових команд."),
 "media": ("медіа", "{company} розвиває цифрове медіа з новинами, подкастами та платною підпискою."),
 "travel": ("подорожі", "{company} створює сервіс пошуку й бронювання подорожей із динамічними цінами від сотень партнерів."),
 "energy": ("енергетика", "{company} розробляє рішення для моніторингу споживання електроенергії та керування сонячними станціями."),
 "telecom": ("телеком", "{company} будує сервіси обміну повідомленнями та клієнтські кабінети для телеком-оператора."),
 "marketplace": ("маркетплейс", "{company} розвиває маркетплейс, що об'єднує тисячі продавців і покупців в одному каталозі."),
 "govtech": ("цифрові публічні сервіси", "{company} розробляє цифрові сервіси для громад і муніципальних установ."),
 "healthtech": ("медичні технології", "{company} створює сервіс онлайн-запису до лікарів і ведення медичних карток для клінік."),
 "saas": ("B2B SaaS", "{company} розробляє SaaS-платформу для керування проєктами та командної роботи в середньому бізнесі."),
 "hr": ("HR Tech", "{company} створює платформу для найму та адаптації працівників."),
 "adtech": ("рекламні технології", "{company} розробляє платформу для закупівлі медійної реклами та аналізу кампаній."),
 "analytics": ("аналітика даних", "{company} створює інструменти бізнес-аналітики для роздрібних мереж і дистриб'юторів."),
 "agritech": ("агротехнології", "{company} розробляє сервіси для агрономів: супутниковий моніторинг полів і планування польових робіт."),
 "proptech": ("нерухомість", "{company} розвиває сервіс пошуку та оренди житла з перевіреними оголошеннями."),
 "ecommerce": ("електронна комерція", "{company} розвиває інтернет-магазин електроніки та побутової техніки з власною службою доставки."),
 "apps": ("мобільні застосунки", "{company} розробляє мобільні застосунки для здорового способу життя з мільйонною аудиторією."),
 "foodtech": ("фудтех", "{company} розвиває сервіс доставки їжі та продуктів із ресторанів і магазинів."),
 "fashion": ("мода", "{company} розвиває онлайн-магазин одягу українських брендів."),
 "manufacturing": ("промисловість", "{company} постачає промислове обладнання та сервісне обслуговування для виробничих підприємств."),
 "gaming": ("ігрова індустрія", "{company} розробляє мобільні ігри та видає проєкти незалежних студій."),
 "cybersecurity": ("кібербезпека", "{company} розробляє інструменти для виявлення вразливостей і моніторингу безпеки інфраструктури."),
}

TEAM = {
 "python": [
  "Бекенд-команда з шести інженерів відповідає за API, інтеграції з партнерами та якість даних. Ми працюємо двотижневими ітераціями, кожна зміна проходить code review та автоматичні перевірки, а важливі технічні рішення фіксуємо в коротких ADR.",
  "У команді працюють бекенд-розробники, QA-інженер і продакт-менеджер. Ми самі розгортаємо свої сервіси, стежимо за метриками в продакшні та чергуємо по черзі, тому цінуємо простий і передбачуваний код.",
  "Наша платформа обробляє мільйони запитів на добу, тому ми приділяємо багато уваги надійності, спостережуваності та продуктивності. Команда відкрита до експериментів, але кожне рішення підкріплює вимірюваннями.",
 ],
 "marketing": [
  "Маркетингова команда з п'яти людей відповідає за залучення та утримання клієнтів. Ми плануємо роботу квартальними цілями, щотижня переглядаємо результати й ухвалюємо рішення на основі даних, а не інтуїції.",
  "Ви працюватимете в тісній зв'язці з продуктовою командою, аналітиками та відділом продажів. Ми цінуємо чесні висновки з експериментів, навіть якщо гіпотеза не підтвердилася.",
  "Маркетинговий бюджет розподіляється між кількома каналами, і ми постійно шукаємо, де він працює найкраще. Для нас важливі прозора звітність, акуратне відстеження та зрозуміла комунікація з командою.",
 ],
 "design": [
  "Дизайн-команда складається з продуктових дизайнерів, дослідника та дизайнера дизайн-системи. Ми працюємо в спільних файлах Figma, регулярно проводимо дизайн-рев'ю та перевіряємо рішення з користувачами.",
  "Дизайнери працюють у крос-функціональних командах разом із розробниками й продакт-менеджерами та беруть участь у роботі від дослідження проблеми до перевірки реалізації.",
  "Ми дбаємо про доступність і послідовність інтерфейсів, тому маємо власну дизайн-систему та чіткі правила передачі макетів у розробку. Рішення обговорюємо відкрито й аргументуємо даними.",
 ],
}

TEAM_SIZE = {4: "чотирьох", 5: "п'яти", 6: "шести", 7: "семи", 8: "восьми"}
SENIORITY_TEXT = {
 "JUNIOR": "Позиція підходить для фахівця на початку кар'єри: ви матимете ментора, зрозумілий план адаптації та задачі, відповідальність за які зростатиме поступово.",
 "MIDDLE": "Очікуємо, що ви самостійно доводите задачі до результату, помічаєте ризики заздалегідь і домовляєтеся із суміжними командами.",
 "SENIOR": "Ви відповідатимете за ключові рішення у своїй зоні, допомагатимете колегам професійно зростати й впливатимете на стратегію команди.",
 "LEAD": "Ви очолите команду з {n} осіб, формуватимете пріоритети й процеси, проводитимете регулярні зустрічі один на один і відповідатимете за результат команди перед керівництвом.",
}

ARCHETYPES = {
 "python": {
  "api": ["fastapi", "rest-api", "postgresql", "pytest", "docker", "python-core"],
  "django": ["django", "postgresql", "sql", "pytest", "celery", "python-core"],
  "data": ["python-core", "sql", "postgresql", "kafka", "celery", "aws"],
  "platform": ["docker", "kubernetes", "ci-cd", "linux", "observability", "aws"],
  "async": ["async-python", "fastapi", "redis", "kafka", "observability", "python-core"],
  "security": ["app-security", "rest-api", "python-core", "linux", "observability", "pytest"],
  "qa": ["pytest", "python-core", "rest-api", "ci-cd", "sql", "git"],
 },
 "marketing": {
  "performance": ["performance-marketing", "google-ads", "meta-ads", "ga4", "attribution", "excel"],
  "seo": ["seo", "content-strategy", "copywriting", "ga4", "market-research", "looker-studio"],
  "crm": ["crm", "email-marketing", "marketing-automation", "segmentation", "ab-testing", "excel"],
  "analytics": ["ga4", "gtm", "looker-studio", "attribution", "ab-testing", "excel"],
  "growth": ["cro", "ab-testing", "ga4", "segmentation", "copywriting", "performance-marketing"],
  "brand": ["brand-strategy", "social-media", "content-strategy", "copywriting", "market-research", "meta-ads"],
  "research": ["market-research", "segmentation", "excel", "looker-studio", "brand-strategy", "ga4"],
 },
 "design": {
  "product": ["figma", "ui-design", "ux-research", "prototyping", "interaction-design", "product-analytics"],
  "research": ["ux-research", "usability-testing", "information-architecture", "stakeholder-communication", "wireframing", "product-analytics"],
  "ui": ["ui-design", "visual-design", "typography", "figma", "responsive-design", "design-systems"],
  "ds": ["design-systems", "figma", "accessibility", "html-css", "ui-design", "typography"],
  "brand": ["branding", "visual-design", "illustrator", "photoshop", "typography", "motion-design"],
  "mobile": ["interaction-design", "prototyping", "motion-design", "responsive-design", "figma", "accessibility"],
 },
}

OR_OPTIONS = {
 "python": [("fastapi", "django"), ("redis", "kafka"), ("celery", "kafka", "redis"), ("aws", "kubernetes"),
            ("sqlalchemy", "django"), ("docker", "kubernetes"), ("pytest", "ci-cd"), ("postgresql", "sql")],
 "marketing": [("google-ads", "meta-ads"), ("ga4", "looker-studio"), ("seo", "content-strategy"),
               ("crm", "marketing-automation"), ("excel", "looker-studio"), ("social-media", "content-strategy"),
               ("ab-testing", "cro"), ("email-marketing", "marketing-automation", "crm")],
 "design": [("ux-research", "usability-testing"), ("ui-design", "visual-design"), ("illustrator", "photoshop"),
            ("prototyping", "wireframing"), ("motion-design", "interaction-design"), ("html-css", "responsive-design"),
            ("ux-research", "product-analytics", "usability-testing"), ("figma", "prototyping")],
}

RESPONSIBILITIES = {
 "api": ["Проєктувати та розвивати REST API для мобільних і вебклієнтів.",
         "Описувати контракти API в OpenAPI та узгоджувати зміни з командами клієнтів.",
         "Оптимізувати запити до PostgreSQL і стежити за часом відповіді сервісів.",
         "Розробляти інтеграції із зовнішніми партнерами через HTTP API та вебхуки."],
 "django": ["Розвивати вебзастосунок на Django: моделі, бізнес-логіку та адміністративну панель.",
            "Налаштовувати права доступу користувачів і ролей на рівні окремих об'єктів.",
            "Готувати безпечні міграції схеми та даних для великих таблиць.",
            "Виносити тривалі операції у фонові задачі Celery."],
 "data": ["Будувати й підтримувати конвеєри даних від джерел до аналітичного сховища.",
          "Писати складні SQL-запити та перевіряти якість даних автоматичними тестами.",
          "Обробляти потоки подій і забезпечувати їх ідемпотентну обробку.",
          "Разом з аналітиками розвивати модель даних і визначення метрик."],
 "platform": ["Підтримувати Kubernetes-кластери та шаблони розгортання сервісів.",
              "Розвивати CI/CD-pipeline і скорочувати час від коміту до релізу.",
              "Налаштовувати метрики, журнали, трасування та алерти для продуктових команд.",
              "Автоматизувати інфраструктуру за допомогою Python-скриптів і підходу «інфраструктура як код»."],
 "async": ["Розробляти асинхронні сервіси, що обслуговують тисячі одночасних з'єднань.",
           "Інтегрувати сервіси через Kafka та Redis і стежити за відставанням споживачів.",
           "Шукати вузькі місця продуктивності за допомогою профілювання та трасування.",
           "Проєктувати повторні спроби, таймаути й деградацію сервісу без втрати даних."],
 "security": ["Проводити безпекове рев'ю коду та архітектурних рішень.",
              "Впроваджувати автентифікацію, авторизацію й керування секретами в сервісах.",
              "Налаштовувати сканування залежностей і контейнерних образів у CI.",
              "Розслідувати безпекові інциденти разом із командою інфраструктури."],
 "qa": ["Розробляти автоматизовані тести API на pytest і підтримувати тестовий фреймворк.",
        "Інтегрувати автотести в CI/CD-pipeline та аналізувати нестабільні тести.",
        "Готувати тестові дані й перевіряти коректність записів у базі за допомогою SQL.",
        "Разом із розробниками визначати критерії приймання та покриття ризикових сценаріїв."],
 "performance": ["Запускати й оптимізувати кампанії в Google Ads і Meta Ads.",
                 "Керувати рекламним бюджетом і щотижня перерозподіляти його між каналами.",
                 "Аналізувати вартість залучення клієнта та рентабельність рекламних витрат.",
                 "Планувати й проводити тести креативів, аудиторій і стратегій ставок."],
 "seo": ["Проводити технічний аудит сайту та контролювати впровадження рекомендацій.",
         "Збирати семантичне ядро й готувати технічні завдання для авторів.",
         "Планувати контент для різних етапів воронки та оновлювати наявні матеріали.",
         "Відстежувати органічний трафік, індексацію та видимість у пошуку."],
 "crm": ["Розробляти тригерні сценарії та регулярні розсилки для різних сегментів клієнтів.",
         "Підтримувати якість даних у CRM і налаштовувати сегменти.",
         "Запускати кампанії утримання та повернення неактивних клієнтів.",
         "Вимірювати внесок CRM-комунікацій у дохід за допомогою контрольних груп."],
 "analytics": ["Налаштовувати відстеження подій у GA4 і Google Tag Manager.",
               "Будувати дашборди в Looker Studio для маркетингової та продуктової команд.",
               "Аналізувати воронки, когорти й ефективність каналів.",
               "Перевіряти якість даних і пояснювати розбіжності між системами."],
 "growth": ["Шукати точки зростання у воронці та формулювати гіпотези для експериментів.",
            "Планувати й аналізувати A/B-тести на сайті та в продукті.",
            "Покращувати лендинги, форми та процес оформлення замовлення.",
            "Разом із продуктовою командою працювати над активацією нових користувачів."],
 "brand": ["Розвивати позиціонування та ключові повідомлення бренду.",
           "Планувати контент для соцмереж і координувати роботу з дизайнерами.",
           "Готувати комунікаційні кампанії та запуски продуктів.",
           "Аналізувати сприйняття бренду та активність конкурентів."],
 "research": ["Проводити дослідження ринку, конкурентів і потреб клієнтів.",
              "Сегментувати клієнтську базу та описувати профілі цільових аудиторій.",
              "Готувати аналітичні звіти й презентації для керівництва.",
              "Перевіряти маркетингові гіпотези на даних опитувань і продажів."],
 "product": ["Проєктувати сценарії користувачів від проблеми до готового інтерфейсу.",
             "Створювати вайрфрейми, прототипи та фінальні макети у Figma.",
             "Перевіряти рішення з користувачами та за продуктовими метриками.",
             "Разом із продакт-менеджером і розробниками визначати пріоритети релізів."],
 "ui": ["Створювати UI-макети з увагою до ієрархії, типографіки та станів компонентів.",
        "Адаптувати інтерфейси для різних розмірів екрана.",
        "Готувати графічні матеріали та ілюстрації для продукту.",
        "Перевіряти реалізацію макетів і узгоджувати правки з розробниками."],
 "ds": ["Розвивати бібліотеку компонентів і дизайн-токени.",
        "Документувати правила використання компонентів для дизайнерів і розробників.",
        "Перевіряти компоненти на доступність і відповідність WCAG.",
        "Синхронізувати дизайн-систему з кодовою бібліотекою разом із frontend-командою."],
 "mobile": ["Проєктувати інтерфейси мобільних застосунків для iOS та Android.",
            "Створювати мікровзаємодії та анімації переходів.",
            "Готувати специфікації анімацій і станів для розробників.",
            "Враховувати рекомендації платформ і вимоги доступності."],
}
DESIGN_RESEARCH = ["Планувати та проводити інтерв'ю, юзабіліті-тести й опитування.",
                   "Синтезувати результати досліджень і формулювати інсайти для команд.",
                   "Підтримувати репозиторій досліджень і базу знань про користувачів.",
                   "Допомагати продуктовим командам формулювати дослідницькі запитання."]
DESIGN_BRAND = ["Розвивати айдентику бренду та підтримувати брендбук.",
                "Створювати графіку для рекламних кампаній, соцмереж і друку.",
                "Готувати ілюстрації, іконки та презентаційні матеріали.",
                "Контролювати візуальну послідовність матеріалів підрядників."]

GENERIC = {
 "python": ["Брати участь у code review і допомагати колегам покращувати якість коду.",
            "Писати модульні та інтеграційні тести для нової функціональності.",
            "Документувати технічні рішення й підтримувати актуальність README та runbook.",
            "Розбирати інциденти в продакшні та запобігати їх повторенню.",
            "Оцінювати задачі разом із продакт-менеджером і пропонувати простіші технічні рішення.",
            "Оновлювати залежності та стежити за технічним боргом.",
            "Брати участь у плануванні спринтів і ретроспективах.",
            "Ділитися знаннями на внутрішніх технічних зустрічах.",
            "Стежити за метриками сервісів після кожного релізу.",
            "Узгоджувати зміни в API з фронтенд- і мобільними розробниками."],
 "marketing": ["Готувати щотижневі звіти з ключовими метриками та висновками.",
               "Узгоджувати UTM-розмітку та правила іменування кампаній.",
               "Співпрацювати з дизайнерами й копірайтерами над рекламними матеріалами.",
               "Ставити задачі розробникам щодо змін на сайті та відстеження подій.",
               "Документувати результати експериментів і ділитися висновками з командою.",
               "Стежити за тенденціями ринку та практиками конкурентів.",
               "Брати участь у квартальному плануванні маркетингу.",
               "Контролювати дотримання бюджету й термінів кампаній.",
               "Разом із відділом продажів покращувати якість лідів.",
               "Пропонувати нові канали та формати для тестування."],
 "design": ["Брати участь у дизайн-рев'ю та давати колегам конструктивний зворотний зв'язок.",
            "Презентувати рішення стейкхолдерам і аргументувати їх даними.",
            "Документувати ухвалені рішення та причини змін.",
            "Аналізувати продуктові метрики після запуску змін.",
            "Разом із копірайтерами працювати над текстами інтерфейсу.",
            "Підтримувати порядок у файлах і бібліотеках Figma.",
            "Оцінювати трудомісткість дизайн-задач разом із командою.",
            "Вивчати рішення конкурентів і перевірені практики галузі.",
            "Брати участь у плануванні спринтів і ретроспективах.",
            "Допомагати команді підтримки розбиратися зі скаргами користувачів на інтерфейс."],
}

BENEFITS = ["Оплачувана щорічна відпустка тривалістю 24 робочі дні та оплачувані лікарняні.",
            "Медичне страхування після завершення випробувального терміну.",
            "Компенсація курсів, навчання та професійних конференцій.",
            "Гнучкий початок робочого дня.",
            "Ноутбук і додаткове обладнання для роботи.",
            "Щорічний перегляд компенсації за прозорими критеріями.",
            "Сесії з ментором та індивідуальний план розвитку.",
            "Заняття англійською з викладачем у робочий час.",
            "Компенсація спортзалу або психологічної підтримки.",
            "Додатковий вихідний на день народження.",
            "Внутрішні хакатони та дні для власних професійних проєктів."]

# (location, locative phrase, country) — country: UA, PL, REMOTE_UA, REMOTE_EU
CITIES = [("Kyiv", "у Києві", "UA"), ("Lviv", "у Львові", "UA"), ("Kharkiv", "у Харкові", "UA"),
          ("Dnipro", "у Дніпрі", "UA"), ("Odesa", "в Одесі", "UA"), ("Ivano-Frankivsk", "в Івано-Франківську", "UA"),
          ("Warsaw", "у Варшаві", "PL"), ("Kraków", "у Кракові", "PL"),
          ("Remote — Ukraine", "віддалено з України", "REMOTE_UA"), ("Remote — Europe", "віддалено з Європи", "REMOTE_EU")]
CITY_WEIGHTS = [5, 3, 1, 1, 1, 1, 2, 1, 4, 3]

SALARY = {"python": {"JUNIOR": (800, 1500), "MIDDLE": (2200, 3800), "SENIOR": (4000, 6200), "LEAD": (5500, 7800)},
          "marketing": {"JUNIOR": (600, 1100), "MIDDLE": (1300, 2400), "SENIOR": (2500, 3800), "LEAD": (3500, 5200)},
          "design": {"JUNIOR": (650, 1200), "MIDDLE": (1500, 2600), "SENIOR": (2700, 4100), "LEAD": (3800, 5500)}}
YEARS = {"JUNIOR": [(0, 1), (0, 2), (1, 2)], "MIDDLE": [(2, 4), (2, 5), (3, 5)],
         "SENIOR": [(4, 7), (5, 8), (4, 8)], "LEAD": [(6, None), (7, None), (5, None)]}
LEVEL = {"JUNIOR": 1, "MIDDLE": 2, "SENIOR": 3, "LEAD": 3}
MODE_UK = {"REMOTE": "віддалено", "HYBRID": "гібридно", "OFFICE": "в офісі"}
EMPLOYMENT_UK = {"Full-time": "повна", "Part-time": "часткова", "Contract": "проєктний контракт"}
SOURCE_NOTE = ("Джерело: синтетична вакансія з навчального набору CompetenceMatch (fixtures-v2). "
               "Компанія та вакансія вигадані й не є публікацією реального роботодавця.")


def _lc(text: str) -> str:
    return text[0].lower() + text[1:].rstrip(".")


def _inline(name: str) -> str:
    """Lower-case a common Ukrainian noun phrase inside a sentence; keep names and acronyms (Figma, UX-...)."""
    return name[0].lower() + name[1:] if "А" <= name[0] <= "Я" or name[0] in "ІЇЄҐ" else name


def _join_or(names: list[str]) -> str:
    names = [_inline(n) for n in names]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " або " + names[-1]


def _years(n: int) -> str:
    return "року" if n == 1 else "років"


def _years_text(lo: int, hi: int | None) -> str:
    if lo == 0:
        return f"комерційний досвід не обов'язковий, орієнтир — до {hi} {_years(hi)}"
    return f"від {lo} до {hi} {_years(hi)}" if hi else f"від {lo} {_years(lo)}"


def _groups(slug: str, track: str, seniority: str, archetype: str, comps: dict, rng: random.Random) -> list[dict]:
    level = LEVEL[seniority]
    core = list(ARCHETYPES[track][archetype])
    pool = [c for c in comps if comps[c]["track"] == track]
    options = list(OR_OPTIONS[track])
    rng.shuffle(options)
    used: set[str] = set()

    def take_or(prefer_core: bool):
        for opt in options:
            if used.isdisjoint(opt) and (not prefer_core or set(opt) & set(core)):
                options.remove(opt)
                used.update(opt)
                return list(opt)
        return None

    mand_or = [take_or(True)]
    if rng.random() < 0.35:
        mand_or.append(take_or(False))
    mand_or = [o for o in mand_or if o]
    singles = [c for c in core if c not in used]
    n_single = rng.choice([4, 5]) if level > 1 else rng.choice([3, 4])
    rest = [c for c in pool if c not in used and c not in singles]
    rng.shuffle(rest)
    singles = (singles + rest)[:n_single]
    used.update(singles)
    desired_or = take_or(False) if rng.random() < 0.4 else None
    remaining = [c for c in pool if c not in used]
    rng.shuffle(remaining)
    desired = remaining[:rng.choice([2, 3])]
    while len(singles) + len(mand_or) + len(desired) + bool(desired_or) < 8:
        desired.append(remaining[len(desired)])

    groups: list[dict] = []

    def add(kind: str, label: str, alts: list[str], lvl: int):
        groups.append({"id": f"{slug}-g{len(groups) + 1:02d}", "kind": kind, "label": label, "excerpt": label,
                       "alternatives": [{"competency_id": a, "required_level": lvl,
                                         "normalization_status": "ACCEPTED_CURATED"} for a in alts]})

    for j, c in enumerate(singles):
        lvl = level if j < 3 else max(1, level - rng.choice([0, 1]))
        add("MANDATORY", f"Вміння {_lc(comps[c]['summary'])} ({comps[c]['label_uk']}, рівень від {lvl}/3).", [c], lvl)
    for opt in mand_or:
        lvl = min(level, 2)
        names = _join_or([comps[c]["label_uk"] for c in opt])
        add("MANDATORY", f"Практичний досвід принаймні з одним із варіантів: {names} (рівень від {lvl}/3).", opt, lvl)
    for c in desired:
        add("DESIRED", f"Буде перевагою: вміння {_lc(comps[c]['summary'])} ({comps[c]['label_uk']}).", [c],
            max(1, level - 1))
    if desired_or:
        names = _join_or([comps[c]["label_uk"] for c in desired_or])
        add("DESIRED", f"Буде перевагою досвід роботи з одним із варіантів: {names}.", desired_or, max(1, level - 1))
    return groups


def build_vacancy(track: str, index: int, spec: tuple, comps: dict) -> dict:
    title, seniority, archetype, domain = spec
    slug = f"{track}-{31 + index:02d}"
    rng = random.Random(f"{VERSION}:{slug}")
    company = COMPANIES[track][index]
    location, loc_phrase, country = rng.choices(CITIES, weights=CITY_WEIGHTS)[0]
    work_mode = "REMOTE" if country.startswith("REMOTE") else rng.choice(["HYBRID", "HYBRID", "OFFICE"])
    currency = "EUR" if country in ("PL", "REMOTE_EU") else "USD"
    employment = "Full-time"
    if seniority == "JUNIOR" and track != "python" and rng.random() < 0.3:
        employment = "Part-time"
    elif seniority in ("MIDDLE", "SENIOR") and rng.random() < 0.08:
        employment = "Contract"
    years_min, years_max = rng.choice(YEARS[seniority])
    lo, hi = SALARY[track][seniority]
    salary_min, salary_max = lo + rng.choice([0, 100, 200, 300]), hi + rng.choice([0, 200, 400])
    if currency == "EUR":
        salary_min, salary_max = (round(x * 0.9 / 50) * 50 for x in (salary_min, salary_max))
    if employment == "Part-time":
        salary_min, salary_max = (round(x * 0.6 / 50) * 50 for x in (salary_min, salary_max))
    groups = _groups(slug, track, seniority, archetype, comps, rng)

    specific = DESIGN_RESEARCH if (track, archetype) == ("design", "research") else \
        DESIGN_BRAND if (track, archetype) == ("design", "brand") else RESPONSIBILITIES[archetype]
    tasks = rng.sample(specific, 3) + rng.sample(GENERIC[track], 3)
    perks = rng.sample(BENEFITS, 4)
    if country == "UA" and work_mode != "REMOTE":
        perks.append(f"Офіс {loc_phrase} з укриттям, генератором і резервним інтернетом.")
    elif country == "PL":
        perks.append(f"Офіс {loc_phrase}, а також допомога з оформленням документів для роботи в Польщі.")
    else:
        perks.append("Компенсація коворкінгу або облаштування домашнього робочого місця.")

    domain_short, domain_text = DOMAINS[domain]
    about = " ".join([domain_text.format(company=company), TEAM[track][rng.randrange(3)],
                      SENIORITY_TEXT[seniority].format(n=TEAM_SIZE[rng.choice(list(TEAM_SIZE))])])
    mode_phrase = {"REMOTE": f"віддалена робота {loc_phrase.split(' ', 1)[1]}",
                   "HYBRID": f"гібридний формат {loc_phrase}",
                   "OFFICE": f"робота в офісі {loc_phrase}"}[work_mode]
    summary = f"{company} шукає фахівця на позицію {title}. Сфера: {domain_short}; {mode_phrase}."
    description = "\n".join([
        f"{title} | {company}", "", "Про компанію", about,
        "", "Чим ви займатиметеся", *[f"- {t}" for t in tasks],
        "", "Обов'язкові вимоги", *[f"- {g['label']}" for g in groups if g["kind"] == "MANDATORY"],
        "", "Буде перевагою", *[f"- {g['label']}" for g in groups if g["kind"] == "DESIRED"],
        "", "Що ми пропонуємо", *[f"- {p}" for p in perks],
        "", f"Досвід: {_years_text(years_min, years_max)}.",
        f"Локація: {location}. Формат роботи: {MODE_UK[work_mode]}. Зайнятість: {EMPLOYMENT_UK[employment]}.",
        f"Зарплатна вилка: {salary_min}–{salary_max} {currency} на місяць.",
        "", SOURCE_NOTE,
    ])
    stack = list(dict.fromkeys(comps[a["competency_id"]]["label"] for g in groups for a in g["alternatives"]))
    assert 8 <= len(groups) <= 12 and len(description) > 1300, slug
    return {"id": slug, "track": track, "title": title, "company": company, "seniority": seniority,
            "years_min": years_min, "years_max": years_max, "location": location, "work_mode": work_mode,
            "employment": employment, "salary_min": salary_min, "salary_max": salary_max, "currency": currency,
            "summary": summary, "description": description, "responsibilities": tasks, "benefits": perks,
            "stack": stack, "source_type": "SYNTHETIC_GENERATED", "source_url": None, "fixture_version": VERSION,
            "groups": groups}


def write_json(name: str, content) -> None:
    (OUT / name).write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build() -> None:
    comps = {c["id"]: c for c in json.loads((OUT / "competencies.json").read_text(encoding="utf-8"))}
    assert set(RUBRICS) == set(comps) == set(QUESTIONS_V2)
    old = [v for v in json.loads((OUT / "vacancies.json").read_text(encoding="utf-8"))
           if v["fixture_version"] != VERSION]
    assert len(old) == 90
    new = [build_vacancy(track, i, spec, comps) for track, specs in TITLES.items() for i, spec in enumerate(specs)]
    assert all(len(TITLES[t]) == 30 and len(COMPANIES[t]) == 30 for t in TITLES)
    write_json("vacancies.json", old + new)

    bank = json.loads((OUT / "questions.json").read_text(encoding="utf-8"))
    for action, texts in QUESTIONS_V2.items():
        kept = [q for q in bank[action] if not q["id"].endswith("-v2")]
        bank[action] = kept + [{"id": f"{action}-ft-{n}-v2", "kind": "FREE_TEXT", "text": text, "options": [],
                                "correct_option": None, "rubric_version": "v1"} for n, text in enumerate(texts, 1)]
    write_json("questions.json", bank)

    rubrics = {"_note": ("Unreviewed starter rubrics generated from curated per-action templates "
                         "(source CURATED_TEMPLATE). They require independent expert review before any claim of "
                         "validity; scores against them are assessments of supplied answers, not certifications."),
               "rubrics": [build_rubric(c) for c in comps]}
    write_json("rubrics.json", rubrics)
    print(f"Generated {len(new)} fixtures-v2 vacancies (total {len(old) + len(new)}), "
          f"{sum(len(r['criteria']) for r in rubrics['rubrics'])} rubric criteria for {len(rubrics['rubrics'])} actions, "
          f"{sum(map(len, QUESTIONS_V2.values()))} new questions")


if __name__ == "__main__":
    build()
