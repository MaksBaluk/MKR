from backend.domain.core_flow import eval_alternative, eval_group, planner_state

R = {"pg": [("pg.tx", 1), ("pg.idx", 1), ("pg.opt", 1), ("pg.conc", 1), ("pg.repl", 1)]}
IDS = [c for c, _ in R["pg"]]
ALT = {"competency_id": "pg", "required_level": 3}


def test_one_of_five_unresolved():
    ev = eval_alternative(ALT, {"pg.tx": 0.95}, R)
    assert ev.status == "UNRESOLVED" and ev.lower == 0.2 and ev.upper == 1.0


def test_all_five_satisfied():
    ev = eval_alternative(ALT, {c: 0.95 for c in IDS}, R)
    assert ev.status == "SATISFIED" and ev.lower == 1.0


def test_one_definite_fail():
    assert eval_alternative(ALT, {"pg.tx": 0.95, "pg.idx": 0.2}, R).status == "FAILED"


def test_vacancy_specific_subset():
    alt = {**ALT, "criterion_ids": ["pg.tx"]}
    assert eval_alternative(alt, {"pg.tx": 0.95}, R).status == "SATISFIED"


def test_or_group_max_not_sum():
    alts = [ALT, {"competency_id": "x", "required_level": 3}]
    ev = eval_group(alts, {"pg.tx": 0.95, "pg.idx": 0.95, "x": 0.45}, R)
    assert ev.lower == 0.5 and ev.upper == 1.0


def test_legacy_action_without_rubric():
    assert eval_alternative({"competency_id": "pg", "required_level": 2}, {"pg": 0.8}, {}).status == "SATISFIED"


def test_null_is_not_zero():
    ev = eval_alternative(ALT, {}, R)
    assert (ev.lower, ev.upper, ev.status) == (0.0, 1.0, "UNRESOLVED")


def test_planner_state_keeps_group_open_until_all_criteria():
    revs = [{"id": "v1", "groups": [{"kind": "MANDATORY", "alternatives": [ALT]}]}]
    st, _ = planner_state(revs, {"pg.tx": 0.95}, R)
    assert ("v1", 0) in st.open_groups
    st, _ = planner_state(revs, {c: 0.95 for c in IDS}, R)
    assert ("v1", 0) not in st.open_groups
