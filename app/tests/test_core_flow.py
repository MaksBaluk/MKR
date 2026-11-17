from backend.domain.core_flow import eval_group, rank_vacancy, planner_state


def A(c, lvl=2):
    return {"competency_id": c, "required_level": lvl}


def test_or_group_satisfied_by_one_alternative():
    ev = eval_group([A("a"), A("b")], {"a": 0.9, "b": None}, {})
    assert ev.status == "SATISFIED"


def test_or_group_failed_only_when_all_fail():
    assert eval_group([A("a"), A("b")], {"a": 0.0, "b": 0.0}, {}).status == "FAILED"
    assert eval_group([A("a"), A("b")], {"a": 0.0, "b": None}, {}).status == "UNRESOLVED"


def test_unknown_score_is_unresolved_not_satisfied():
    assert eval_group([A("a")], {}, {}).status == "UNRESOLVED"


def test_no_evidence_gives_low_information():
    v = {"id": "v1", "years_min": 2, "groups": [{"kind": "MANDATORY", "alternatives": [A("a")]}]}
    assert rank_vacancy(v, {}, {}, 5).label == "LOW_INFORMATION"


def test_no_groups_not_evaluable():
    v = {"id": "v1", "years_min": 0, "groups": []}
    assert rank_vacancy(v, {}, {}, None).label == "NOT_EVALUABLE"


def test_met_mandatory_gives_z2():
    v = {"id": "v1", "years_min": 2, "groups": [{"kind": "MANDATORY", "alternatives": [A("a")]}]}
    r = rank_vacancy(v, {"a": 0.9}, {}, 5)
    assert r.z == 2 and r.x == 2 and r.label == "RANKED"


def test_failed_mandatory_gives_z0():
    v = {"id": "v1", "years_min": 2, "groups": [{"kind": "MANDATORY", "alternatives": [A("a")]}]}
    assert rank_vacancy(v, {"a": 0.0}, {}, 5).z == 0


def test_planner_state_closes_satisfied_group():
    revs = [{"id": "v1", "groups": [{"kind": "MANDATORY", "alternatives": [A("a")]},
                                    {"kind": "DESIRED", "alternatives": [A("b")]}]}]
    st, w = planner_state(revs, {"a": 0.9}, {})
    assert ("v1", 0) not in st.open_groups and ("v1", 1) in st.open_groups
    assert abs(sum(w.values()) - 1.0) < 1e-12
