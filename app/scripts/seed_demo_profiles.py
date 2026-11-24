"""Seed one account with finished demo interviews (several tracks and levels) through the real HTTP API.

The Interviewer and Evaluator are deterministic stubs, not a language model: questions are template text, answers
are canned persona text and the grades are derived from the persona level by a fixed hash. The data are synthetic
demo data for looking at the UI. They are not an assessment of any real person and not evidence of method quality.

Run inside the API container (it needs the product database and the backend package):
    docker compose cp scripts/seed_demo_profiles.py api:/app/scripts/seed_demo_profiles.py
    docker compose exec -e SEED_EMAIL=... -e SEED_PASSWORD=... api python scripts/seed_demo_profiles.py
"""
import hashlib
import json
import os
import re
import sys
import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.agents.prompts import INTERVIEWER_SYSTEM
from backend.main import app

SUFFIX = " (демо)"
PROFILES = [  # name, track, title, level, years, city, work mode
    ("Senior Python Backend", "python", "Senior Python Backend Developer", "senior", 8, "Київ", "remote"),
    ("Senior UX/UI Designer", "design", "Senior Product Designer", "senior", 9, "Львів", "hybrid"),
    ("Middle Marketing", "marketing", "Performance Marketing Manager", "middle", 4, "Одеса", "any"),
    ("Junior Python", "python", "Junior Python Developer", "junior", 1, "Харків", "office"),
]
LEVEL_SCORES = {"senior": (0.95, 0.9, 0.9, 0.95), "middle": (0.8, 0.7, 0.6, 0.45), "junior": (0.55, 0.4, 0.3, None)}
QUESTIONS = ["Опишіть конкретний випадок із вашої практики в цій темі: що саме ви робили?",
             "Як ви перевіряли, що результат у цій темі справді добрий?",
             "Що пішло не так у цій темі й як ви це виправили?",
             "Як би ви пояснили свій підхід у цій темі колезі, який щойно прийшов у команду?",
             "Що б ви зробили інакше в цій темі, якби починали той проєкт заново?"]
ANSWERS = {
    "senior": "Маю понад вісім років практики в цій темі. Нещодавно сам спроєктував рішення, порівняв два підходи, "
              "обрав кращий за вимірюваними метриками і розписав компроміси для команди. Після запуску відстежував показники "
              "й виправив вузьке місце, яке показали дані.",
    "middle": "Працюю з цим щодня кілька років. Зазвичай беру стандартний підхід, перевіряю результат на невеликому прикладі "
              "і радимось із старшими колегами, якщо щось незвичне. Конкретний випадок: виправляв помилку в робочому процесі й додав перевірку.",
    "junior": "Це я бачив у навчанні й трохи пробував на невеликому проєкті. Роблю за інструкцією, кожен крок перевіряю вручну; "
              "глибоко ще не розбирався.",
}


def _grade(level: str, key: str):
    pool = LEVEL_SCORES[level]
    return pool[int(hashlib.sha256(key.encode()).hexdigest(), 16) % len(pool)]


class DemoChat:
    """Deterministic stand-in for the chat model; `level` is set per interview by the driver."""

    level = "middle"

    def invoke(self, messages, *a, **k):
        system, human = messages[0].content, messages[1].content
        if system == INTERVIEWER_SYSTEM:
            asked = json.loads(re.search(r"^asked_questions: (.*)$", human, re.M).group(1))
            return SimpleNamespace(content=QUESTIONS[len(asked) % len(QUESTIONS)])
        data = {k: json.loads(v) for k, v in (line.split(": ", 1) for line in human.splitlines()
                                              if re.match(r"(action_id|rubric_version|allowed_criterion_ids|practice_criterion_ids): ", line))}
        turn_id = re.findall(r"turn_id=\"([^\"]+)\"", human)[-1]
        text = json.loads(re.findall(r">(\".*\")</candidate_answer>", human)[-1])
        crit = []
        for c in data["allowed_criterion_ids"]:
            score = _grade(self.level, data["action_id"] + c)
            crit.append({"criterion_id": c, "score": score,
                         "reason": "Оцінка за наведеним у відповіді прикладом." if score is not None else "У відповіді немає свідчень.",
                         "evidence": [{"turn_id": turn_id, "exact_excerpt": text}] if score is not None else []})
        practice = []
        for c in data.get("practice_criterion_ids", []):
            score = _grade(self.level, data["action_id"] + c)
            practice.append({"criterion_id": c, "score": score, "reason": "Оцінка за наведеним у відповіді прикладом.",
                             "evidence": [{"turn_id": turn_id, "exact_excerpt": text}] if score is not None else []})
        return SimpleNamespace(content=json.dumps({
            "action_id": data["action_id"], "rubric_version": data["rubric_version"], "off_topic": False,
            "criteria": crit, **({"practice": practice} if practice else {}), "sufficient_evidence": all(c["score"] is not None for c in crit),
            "needs_followup": False, "followup_goal": None}))


def main() -> int:
    email, password = os.environ["SEED_EMAIL"], os.environ["SEED_PASSWORD"]
    chat = DemoChat()
    import backend.api.core as core
    core.get_chat_model = lambda: chat
    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    auth = {"Authorization": "Bearer " + r.json()["token"]}
    existing = {p["name"]: p for p in client.get("/api/v1/profiles", headers=auth).json()["items"]}
    reset = set(filter(None, os.environ.get("SEED_RESET", "").split("|")))  # names to archive and redo
    for full in reset:
        if full in existing:
            client.delete(f"/api/v1/profiles/{existing.pop(full)['id']}", headers=auth)
    for name, *_ in PROFILES:  # archive earlier empty profiles with the plain name
        if name in existing and not existing[name].get("archived"):
            client.delete(f"/api/v1/profiles/{existing[name]['id']}", headers=auth)
    for name, track, title, level, years, city, mode in PROFILES:
        full = name + SUFFIX
        if full in existing and existing[full].get("latest_finished_attempt_id"):
            print("skip (already finished)", full)
            continue
        prof = existing.get(full) or client.post("/api/v1/profiles", headers=auth, json={
            "name": full, "track": track, "desired_title": title, "target_level": level, "work_mode": mode,
            "years_experience": years, "location": city}).json()
        chat.level = level
        att = client.post(f"/api/v1/profiles/{prof['id']}/attempts", headers=auth).json()
        iid, version, n = att["id"], client.get(f"/api/v1/interviews/{att['id']}", headers=auth).json().get("version", 0), 0
        while n < 80:
            q = client.post(f"/api/v1/interviews/{iid}/next-question", json={"version": version}, headers=auth).json()
            if q.get("done"):
                break
            turn, version = q["turn"], q["version"]
            a = client.post(f"/api/v1/interviews/{iid}/answers", headers=auth, json={
                "version": version, "turn_id": turn["id"], "text": f"{ANSWERS[level]} Тема: {turn['action_name']}, окремий приклад №{n + 1}.", "idempotency_key": str(uuid.uuid4())})
            a.raise_for_status()
            version = a.json().get("version", version)
            n += 1
        print(full, "answers:", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
