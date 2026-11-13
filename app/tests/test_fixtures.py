from collections import Counter
from backend.seed import read_fixture


def test_fixture_catalog_completeness_and_unique_job_text():
    rows = read_fixture('vacancies.json')
    skills = read_fixture('competencies.json')
    questions = read_fixture('questions.json')
    assert len(rows) == 90
    assert Counter(v['track'] for v in rows) == {'python':30,'marketing':30,'design':30}
    assert len(skills) == 60
    assert len(questions) == 60 and sum(map(len,questions.values())) == 120
    assert len({v['description'] for v in rows}) == 90
    assert all(v['source_type'] == 'DEMO_CURATED' and not v['source_url'] for v in rows)
    assert all(len(v['description']) > 1300 and len(v['groups']) >= 10 for v in rows)
    assert all(any(len(g['alternatives']) > 1 for g in v['groups']) for v in rows)


def test_question_bank_keys_and_correct_answers():
    bank = read_fixture('questions.json')
    ids = {c['id'] for c in read_fixture('competencies.json')}
    assert set(bank) == ids
    for skill, questions in bank.items():
        assert {q['kind'] for q in questions} == {'MULTIPLE_CHOICE','FREE_TEXT'}, skill
        mcq = questions[0]
        assert any(option['id'] == mcq['correct_option'] for option in mcq['options'])
