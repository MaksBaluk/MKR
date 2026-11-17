import json
import re
from pathlib import Path

from backend.api.common import source_label
from backend.models import Vacancy

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "vacancies.json"
LEVEL_WORDS = {"junior": "JUNIOR", "middle": "MIDDLE", "senior": "SENIOR", "lead": "LEAD"}


def test_all_vacancies_are_labelled_djinni_per_owner():
    assert source_label(Vacancy(id="x", source_type="SYNTHETIC_GENERATED")) == "Djinni"
    assert source_label(Vacancy(id="y", source_type="DEMO_CURATED")) == "Djinni"


def test_fixture_titles_match_seniority_field():
    bad = []
    for v in json.loads(FIXTURES.read_text(encoding="utf-8")):
        for word, level in LEVEL_WORDS.items():
            if re.search(rf"\b{word}\b", v["title"], re.IGNORECASE) and v["seniority"] != level:
                bad.append(v["id"])
                break
    assert bad == []
