import json
import re
from pathlib import Path

from backend.api.common import source_is_example, source_label
from backend.models import Vacancy

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "vacancies.json"
LEVEL_WORDS = {"junior": "JUNIOR", "middle": "MIDDLE", "senior": "SENIOR", "lead": "LEAD"}


def test_only_imported_vacancies_are_labelled_djinni():
    assert source_label(Vacancy(id="x", source_type="SYNTHETIC_GENERATED")) == "Приклад"
    assert source_label(Vacancy(id="y", source_type="DEMO_CURATED")) == "Приклад"
    assert source_label(Vacancy(id="z", source_type="REAL_IMPORTED")) == "Djinni"
    assert source_label(Vacancy(id="w", source_type="DEMO_CURATED", source_name="robota.ua")) == "robota.ua"
    assert source_is_example(Vacancy(id="w", source_type="DEMO_CURATED", source_name="robota.ua"))
    assert not source_is_example(Vacancy(id="z", source_type="REAL_IMPORTED"))


def test_fixture_titles_match_seniority_field():
    bad = []
    for v in json.loads(FIXTURES.read_text(encoding="utf-8")):
        for word, level in LEVEL_WORDS.items():
            if re.search(rf"\b{word}\b", v["title"], re.IGNORECASE) and v["seniority"] != level:
                bad.append(v["id"])
                break
    assert bad == []
