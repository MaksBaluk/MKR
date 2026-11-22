import importlib.util
import math
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "scripts/chapter4/annotation_merge.py"
spec = importlib.util.spec_from_file_location("annotation_merge", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_kappa_perfect_and_chance():
    assert math.isclose(m.kappa([0, 1, 2, 3], [0, 1, 2, 3], [0, 1, 2, 3], m.quad), 1.0)
    assert math.isclose(m.kappa([0, 0, 1, 1], [0, 1, 0, 1], [0, 1]), 0.0, abs_tol=1e-9)


def test_weighted_penalises_far_more():
    near = m.kappa([0, 1, 2, 3], [1, 2, 3, 3], [0, 1, 2, 3], m.quad)
    far = m.kappa([0, 1, 2, 3], [3, 3, 0, 0], [0, 1, 2, 3], m.quad)
    assert near > far


def _w(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    m.write(path, header, rows)


def test_third_pass_becomes_adjudicated_and_rerun_is_idempotent(tmp_path):
    hr = ["candidate_id", "vacancy_id", "annotator_id", "relevance", "rationale", "scale_version"]
    hs = ["candidate_id", "annotator_id", "level", "rationale", "evidence_refs"]
    hc = ["candidate_id", "criterion_id", "question_id", "annotator_id", "score", "evidence_status", "rubric_version", "comment"]
    src, out = tmp_path / "src", tmp_path / "out"
    for sub, aid, rels, lvl in (("annotator_1", m.A1, (2, 1), "JUNIOR"), ("annotator_2", m.A2, (3, 2), "UNKNOWN")):
        _w(src / sub / m.FILES["rel"], hr, [{"candidate_id": "C01", "vacancy_id": v, "annotator_id": aid, "relevance": r,
                                            "rationale": aid, "scale_version": "rel-0-3/v1"} for v, r in zip(("v1", "v2"), rels)])
        _w(src / sub / m.FILES["sen"], hs, [{"candidate_id": "C01", "annotator_id": aid, "level": lvl, "rationale": aid,
                                            "evidence_refs": ""}])
        _w(src / sub / m.FILES["crit"], hc, [{"candidate_id": "C01", "criterion_id": "x.a", "question_id": "q1",
                                             "annotator_id": aid, "score": "0.5", "evidence_status": "EVIDENCED",
                                             "rubric_version": "v1", "comment": ""}])
    _w(src / "annotator_3" / "decisions.csv", ["kind", "candidate_id", "vacancy_or_criterion_id", "decision", "rationale", "annotator_id"],
       [{"kind": "relevance", "candidate_id": "C01", "vacancy_or_criterion_id": "v2", "decision": "1", "rationale": "t3",
         "annotator_id": m.A3},
        {"kind": "level", "candidate_id": "C01", "vacancy_or_criterion_id": "", "decision": "UNKNOWN", "rationale": "t3",
         "annotator_id": m.A3}])
    for k, h in (("rel", hr), ("sen", hs), ("crit", hc)):
        _w(out / m.FILES[k], h, [])
    res = m.merge(src, out, tmp_path)
    assert res["n"] == {"sen": 1, "crit": 1, "rel": 2}
    assert dict(res["followed"]) == {"A1": 1, "A2": 1}
    rel = {(r["vacancy_id"], r["annotator_id"]): r for r in m.read(out / m.FILES["rel"])[1]}
    assert rel[("v1", m.ADJ)]["relevance"] == "2" and rel[("v2", m.ADJ)]["relevance"] == "1"
    assert rel[("v2", m.ADJ)]["rationale"].endswith("t3") and ("v2", m.A3) in rel
    snapshot = [(out / f).read_text() for f in m.FILES.values()]
    m.merge(tmp_path / "missing", out, tmp_path)  # rerun from the stored raw rows only
    assert [(out / f).read_text() for f in m.FILES.values()] == snapshot
