import pytest

from backend.domain.rubric import RUBRIC, RUBRIC_VERSION, parse_grade


def _grade(level, quote="логи", confidence="MEDIUM", uncertainty="", followup=None):
    return ('{"level": %s, "evidence_quote": "%s", "confidence": "%s", "uncertainty": "%s", "followup": %s}'
            % ("null" if level is None else level, quote, confidence, uncertainty,
               "null" if followup is None else f'"{followup}"'))


def test_rubric_covers_levels_0_to_3():
    assert RUBRIC_VERSION == "rubric-v1"
    assert set(RUBRIC) == {0, 1, 2, 3}


def test_valid_grade_parses_with_quote_from_answer():
    result = parse_grade(_grade(2), answer="Перевіряю логи та метрики")
    assert result["level"] == 2
    assert result["evidence_quote"] == "логи"


@pytest.mark.parametrize("raw", [
    _grade(4),
    _grade(-1),
    '{"level": "expert", "evidence_quote": "логи", "confidence": "HIGH", "uncertainty": "", "followup": null}',
    'Це чудова відповідь, рівень 3.',
    '{"level": 3}',
    '{"level": 2, "evidence_quote": "логи", "confidence": "SURE", "uncertainty": "", "followup": null}',
])
def test_invalid_grade_rejected(raw):
    with pytest.raises(ValueError):
        parse_grade(raw, answer="Перевіряю логи")


def test_quote_not_in_answer_makes_level_unknown():
    result = parse_grade(_grade(3, quote="ніде не написано"), answer="Я читаю логи")
    assert result["level"] is None
    assert result["uncertainty"] == "NO_SUPPORTING_QUOTE"
