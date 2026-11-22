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
