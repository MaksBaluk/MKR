import pytest

from backend.domain.candidate_level import candidate_level


@pytest.mark.parametrize("years,expected", [(0, "junior"), (1, "junior"), (2, "middle"), (4, "middle"),
                                            (5, "senior"), (12, "senior"), (None, None)])
def test_level_from_years(years, expected):
    assert candidate_level("Python Developer", years) == expected


@pytest.mark.parametrize("title,years,expected", [
    ("Junior Python Developer", 6, "junior"), ("Senior QA Engineer", 1, "senior"), ("Team Lead", 1, "senior"),
    ("Middle Designer", None, "middle"), ("Trainee", None, "junior"), ("", None, None), (None, 3, "middle"),
])
def test_explicit_title_words_override_years(title, years, expected):
    assert candidate_level(title, years) == expected


def test_explicit_target_level_wins_over_title_and_years():
    from backend.domain.candidate_level import resolve_level
    assert resolve_level("middle", "Senior Python Developer", 10) == "middle"
    assert resolve_level("junior", None, 8) == "junior"
    assert resolve_level("lead", None, None) == "senior"  # the interviewer prompt has junior/middle/senior depths


def test_level_falls_back_to_title_then_years_when_not_chosen():
    from backend.domain.candidate_level import resolve_level
    assert resolve_level(None, "Junior QA", 9) == "junior"
    assert resolve_level(None, "", 3) == "middle"
    assert resolve_level(None, None, None) is None
