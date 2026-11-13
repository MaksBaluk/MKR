import pytest

from backend.domain.matching import evaluate_vacancy, presentation_summary, rank_snapshot


def _group(gid, kind, alts):
    return {"id": gid, "kind": kind, "label": gid, "excerpt": "",
            "alternatives": [{"competency_id": c, "required_level": lvl,
                              "normalization_status": "ACCEPTED_CURATED"} for c, lvl in alts]}


def _vacancy(vid, groups):
    return {"id": vid, "groups": groups, "years_min": 0}


def test_3_0_8_with_unknown_mandatory_is_E1_and_conditional_match_is_one():
    mandatory = [_group(f"m{i}", "MANDATORY", [(f"c{i}", 1)]) for i in range(4)]
    desired = [_group(f"d{i}", "DESIRED", [(f"x{i}", 1)]) for i in range(7)]
    row = evaluate_vacancy(_vacancy("v", mandatory + desired), {"c0": 2, "c1": 2, "c2": 2})
    assert (row["s"], row["f"], row["u"]) == (3, 0, 8)
    assert row["match"] == 1
    assert row["coverage"] == pytest.approx(3 / 11)
    assert row["r_score"] == pytest.approx(3 / 11)
    assert row["required_class"] == 1


def test_3_0_8_all_mandatory_satisfied_is_E2():
    groups = [_group(f"m{i}", "MANDATORY", [(f"c{i}", 1)]) for i in range(3)]
    groups += [_group(f"d{i}", "DESIRED", [(f"x{i}", 1)]) for i in range(8)]
    row = evaluate_vacancy(_vacancy("v", groups), {f"c{i}": 2 for i in range(3)})
    assert row["required_class"] == 2


def test_zero_assessed_gives_null_match_and_no_evidence_headline():
    row = evaluate_vacancy(_vacancy("v", [_group("g1", "DESIRED", [("c1", 1)])]), {})
    assert row["match"] is None
    assert row["coverage"] == 0
    assert row["r_score"] == 0
    summary = presentation_summary(row)
    assert summary["headline_kind"] == "NOT_ENOUGH_EVIDENCE"
    assert summary["match_label"] is None


def test_no_groups_gives_null_coverage_and_r():
    row = evaluate_vacancy(_vacancy("v", []), {})
    assert row["coverage"] is None and row["r_score"] is None and row["match"] is None
    assert row["required_class"] == 2
    assert row["note"] == "No mandatory groups were declared"


def test_complete_fit_is_100_percent_of_evaluated_and_E2():
    groups = [_group("m1", "MANDATORY", [("c1", 1)]), _group("d1", "DESIRED", [("c2", 1)])]
    row = evaluate_vacancy(_vacancy("v", groups), {"c1": 2, "c2": 2})
    assert (row["s"], row["f"], row["u"]) == (2, 0, 0)
    assert row["match"] == 1 and row["coverage"] == 1 and row["r_score"] == 1
    assert row["required_class"] == 2


def test_one_failed_mandatory_gives_E0():
    groups = [_group("m1", "MANDATORY", [("c1", 2)]), _group("d1", "DESIRED", [("c2", 1)])]
    row = evaluate_vacancy(_vacancy("v", groups), {"c1": 1, "c2": 3})
    assert row["f"] == 1
    assert row["required_class"] == 0
    assert presentation_summary(row)["mandatory_status"] == "FAILED"


def test_or_group_one_satisfied_is_S_even_if_other_unknown():
    groups = [_group("g", "MANDATORY", [("c1", 2), ("c2", 2)])]
    row = evaluate_vacancy(_vacancy("v", groups), {"c1": 2})
    assert row["groups"][0]["state"] == "S"


def test_or_group_all_known_failed_is_F():
    groups = [_group("g", "MANDATORY", [("c1", 2), ("c2", 2)])]
    row = evaluate_vacancy(_vacancy("v", groups), {"c1": 0, "c2": 1})
    assert row["groups"][0]["state"] == "F"


def test_or_group_one_unknown_remaining_is_U_not_F():
    groups = [_group("g", "MANDATORY", [("c1", 2), ("c2", 2)])]
    row = evaluate_vacancy(_vacancy("v", groups), {"c1": 0})
    assert row["groups"][0]["state"] == "U"


def test_tie_break_by_stable_vacancy_id():
    groups = [_group("g", "DESIRED", [("c1", 1)])]
    ranked = rank_snapshot([_vacancy("b", groups), _vacancy("a", groups)], {"levels": {"c1": 2}})
    assert [row["vacancy_id"] for row in ranked] == ["a", "b"]
    assert [row["rank_position"] for row in ranked] == [1, 2]


def test_unknown_required_status_is_not_counted_as_satisfied():
    group = {"id": "g", "kind": "MANDATORY", "label": "g", "excerpt": "",
             "alternatives": [{"competency_id": "c1", "required_level": 1,
                               "normalization_status": "UNRESOLVED"}]}
    row = evaluate_vacancy(_vacancy("v", [group]), {"c1": 3})
    assert row["groups"][0]["state"] == "U"


def test_presentation_summary_for_3_of_11_matches_spec_wording():
    mandatory = [_group(f"m{i}", "MANDATORY", [(f"c{i}", 1)]) for i in range(4)]
    desired = [_group(f"d{i}", "DESIRED", [(f"x{i}", 1)]) for i in range(7)]
    row = evaluate_vacancy(_vacancy("v", mandatory + desired), {"c0": 2, "c1": 2, "c2": 2})
    summary = presentation_summary(row)
    assert summary["headline_kind"] == "EVALUATED_SHARE"
    assert (summary["known_count"], summary["total_count"], summary["unknown_count"]) == (3, 11, 8)
    assert summary["mandatory_status"] == "PENDING"
    assert summary["match_label"] == "Серед оцінених вимог: 100% (3/3)"
