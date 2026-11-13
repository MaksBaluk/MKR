from backend.domain.adaptive import priorities


def _vacancy(vid, comp, kind="MANDATORY", level=1):
    return {"id": vid, "groups": [{"id": f"{vid}-g", "kind": kind, "label": "x", "excerpt": "",
                                   "alternatives": [{"competency_id": comp, "required_level": level}]}]}


def test_objective_success_does_not_drop_a_verification_need():
    vacancies = [_vacancy("a", "c1")]
    without = priorities(vacancies, {"c1": None}, successful_tasks={"c1"}, asked_counts={})
    assert without == []
    with_conflict = priorities(vacancies, {"c1": None}, successful_tasks={"c1"}, asked_counts={},
                               needs_verification={"c1"})
    assert with_conflict and with_conflict[0]["competency_id"] == "c1" and with_conflict[0]["mode"] == "VERIFY"


def test_one_repeat_allowed_only_for_verification_need():
    vacancies = [_vacancy("a", "c1")]
    assert priorities(vacancies, {"c1": 2}, set(), {"c1": 1}) == []
    repeat = priorities(vacancies, {"c1": 2}, set(), {"c1": 1}, needs_verification={"c1"})
    assert repeat and repeat[0]["competency_id"] == "c1"


def test_mandatory_ordering_tuple_is_preserved():
    vacancies = [_vacancy("a", "c1"), _vacancy("b", "c2", kind="DESIRED")]
    order = priorities(vacancies, {}, set(), {})
    assert [row["competency_id"] for row in order] == ["c1", "c2"]
