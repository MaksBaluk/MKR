"""Expert label tests. All labels are in-test fixtures, not annotations."""

import csv
from pathlib import Path

import pytest

from backend.experiments.expert_labels import (
    DataStatus, ExpertRelevanceLabel, LabelError, ReviewStatus, SyntheticDataError, adjudicate,
    agreement_report, load_criterion_labels, load_relevance_labels, relevance_map,
    require_expert_data, split_by_annotator, validate_label_set,
)

REL = ["candidate_id", "vacancy_id", "grade", "rationale", "annotator_id", "label_version", "data_status", "review_status"]
CRIT = ["candidate_id", "action_id", "criterion_id", "rubric_version", "expert_score", "evidence_reference",
        "annotator_id", "label_version", "data_status", "review_status"]
TEMPLATES = Path(__file__).resolve().parents[1] / "experiments" / "templates"


def rel_row(**kw):
    d = dict(candidate_id="c1", vacancy_id="v1", grade="2", rationale="long enough text", annotator_id="a1",
             label_version="t1", data_status="SYNTHETIC_TEST_DATA", review_status="PENDING")
    d.update(kw)
    return d


def crit_row(**kw):
    d = dict(candidate_id="c1", action_id="x", criterion_id="k", rubric_version="r1", expert_score="0.5",
             evidence_reference="quote", annotator_id="a1", label_version="t1",
             data_status="SYNTHETIC_TEST_DATA", review_status="PENDING")
    d.update(kw)
    return d


def write(tmp_path, header, rows, name="f.csv"):
    p = tmp_path / name
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header)
        w.writeheader()
        w.writerows(rows)
    return p


def lab(cand, vac, grade, ann, status="SYNTHETIC_TEST_DATA"):
    return ExpertRelevanceLabel(**rel_row(candidate_id=cand, vacancy_id=vac, grade=grade, annotator_id=ann,
                                          data_status=status))


def test_valid_load(tmp_path):
    r = load_relevance_labels(write(tmp_path, REL, [rel_row(), rel_row(vacancy_id="v2", grade="3")]))
    assert [x.grade for x in r] == [2, 3] and r[0].review_status is ReviewStatus.PENDING
    c = load_criterion_labels(write(tmp_path, CRIT, [crit_row(), crit_row(criterion_id="k2", expert_score="")],
                                    "c.csv"))
    assert c[0].expert_score == 0.5 and c[1].expert_score is None


@pytest.mark.parametrize("bad", ["4", "-1", "1.5", "abc"])
def test_bad_grade_row_numbered(tmp_path, bad):
    p = write(tmp_path, REL, [rel_row(), rel_row(vacancy_id="v2", grade=bad)])
    with pytest.raises(LabelError) as e:
        load_relevance_labels(p)
    assert len(e.value.errors) == 1 and e.value.errors[0].startswith("row 3:")


def test_collects_all_errors(tmp_path):
    p = write(tmp_path, REL, [rel_row(grade="9"), rel_row(annotator_id=""), rel_row(rationale="short")])
    with pytest.raises(LabelError) as e:
        load_relevance_labels(p)
    assert [m[:6] for m in e.value.errors] == ["row 2:", "row 3:", "row 4:"]


@pytest.mark.parametrize("bad", ["1.2", "nan", "-0.1"])
def test_bad_score(tmp_path, bad):
    with pytest.raises(LabelError) as e:
        load_criterion_labels(write(tmp_path, CRIT, [crit_row(expert_score=bad)]))
    assert e.value.errors[0].startswith("row 2:")


def test_score_needs_evidence(tmp_path):
    with pytest.raises(LabelError):
        load_criterion_labels(write(tmp_path, CRIT, [crit_row(evidence_reference="")]))
    load_criterion_labels(write(tmp_path, CRIT, [crit_row(expert_score="", evidence_reference="")], "n.csv"))


def test_json_load(tmp_path):
    import json
    p = tmp_path / "r.json"
    p.write_text(json.dumps([rel_row(grade=3)]))
    assert load_relevance_labels(p)[0].grade == 3


def test_validate_label_set():
    validate_label_set([lab("c", "v1", 1, "a"), lab("c", "v1", 2, "b")])
    with pytest.raises(LabelError, match="duplicate"):
        validate_label_set([lab("c", "v1", 1, "a"), lab("c", "v1", 1, "a")])
    with pytest.raises(LabelError, match="mixed"):
        validate_label_set([lab("c", "v1", 1, "a"), lab("c", "v2", 1, "b", "EXPERT")])


def test_split_and_map():
    ls = [lab("c", "v1", 1, "a"), lab("c", "v2", 3, "b"), lab("d", "v1", 0, "a")]
    assert set(split_by_annotator(ls)) == {"a", "b"}
    assert relevance_map(ls, "c") == {"v1": 1, "v2": 3}


def sets(grades_a, grades_b):
    a = [lab("c", f"v{i}", g, "a") for i, g in enumerate(grades_a)]
    b = [lab("c", f"v{i}", g, "b") for i, g in enumerate(grades_b)]
    return a, b


def test_adjudicate():
    a, b = sets([3, 2], [3, 1])
    final = [lab("c", "v0", 3, "j"), lab("c", "v1", 2, "j")]
    out = adjudicate(a, b, final, "j")
    assert all(x.review_status is ReviewStatus.ADJUDICATED for x in out)
    assert final[0].review_status is ReviewStatus.PENDING  # copies
    with pytest.raises(LabelError, match="distinct"):
        adjudicate(a, [lab("c", f"v{i}", 1, "a") for i in range(2)], final, "j")
    with pytest.raises(LabelError, match="missing"):
        adjudicate(a, b, final[:1], "j")
    with pytest.raises(LabelError, match="extra"):
        adjudicate(a, b, final + [lab("c", "v9", 1, "j")], "j")
    with pytest.raises(LabelError, match="adjudicator_id"):
        adjudicate(a, b, [lab("c", "v0", 3, "j"), lab("c", "v1", 2, "z")], "j")
    with pytest.raises(LabelError, match="different keys"):
        adjudicate(a, b[:1], final, "j")


def test_agreement_hand_computed():
    a, b = sets([3, 2, 0, 3], [3, 2, 1, 2])
    r = agreement_report(a, b)
    assert r["n_pairs"] == 4 and r["exact_agreement"] == 0.5
    # observed disagreement = (0+0+1+1)/9/4 = 1/18
    # marginals a: {0:.25,2:.25,3:.5}, b: {1:.25,2:.5,3:.25}
    # expected = sum pa_i*pb_j*(i-j)^2/9 = (1.125+0.125+0.75)/9 = 2/9
    # kappa = 1 - (1/18)/(2/9) = 0.75
    assert r["quadratic_weighted_kappa"] == pytest.approx(0.75)
    assert r["confusion"][0][1] == 1 and r["confusion"][3][2] == 1


def test_kappa_undefined():
    a, b = sets([2, 2], [2, 2])
    assert agreement_report(a, b)["quadratic_weighted_kappa"] is None
    assert agreement_report([], [])["exact_agreement"] is None


def test_require_expert_data():
    """Fixture labels built in-test (not annotations) to exercise the EXPERT path."""
    with pytest.raises(SyntheticDataError):
        require_expert_data([lab("c", "v", 1, "a"), lab("c", "w", 1, "a", "EXPERT")])
    require_expert_data([lab("c", "v", 1, "a", "EXPERT")])
    assert issubclass(SyntheticDataError, ValueError)


def test_templates_header_only():
    for name, loader, header in (("relevance_labels.csv", load_relevance_labels, REL),
                                 ("criterion_labels.csv", load_criterion_labels, CRIT)):
        p = TEMPLATES / name
        assert p.read_text().strip().split(",") == header
        assert loader(p) == []
    assert (TEMPLATES / "README.md").exists()
