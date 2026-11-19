"""Chapter-4 Stage 4: seeded property checks of the mathematical core (scripts/chapter4/math_checks.py) and the
hand-worked control examples (scripts/chapter4/math_validation.py). Source of artifacts/chapter4/mathematical_validation.csv.
Two rows are expected non-PASS and pinned: H01 (H is a track filter only: PARTIAL) and R01 (results screen sorts by
percent first, owner decision: DEVIATION)."""
import pytest

from scripts.chapter4 import math_validation
from scripts.chapter4.math_checks import CHECKS

EXPECTED_NON_PASS = {"H01": "PARTIAL", "R01": "DEVIATION"}


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.__name__)
def test_property(check):
    row = check()
    assert row["cases"] > 0
    assert row["status"] == EXPECTED_NON_PASS.get(row["id"], "PASS"), row


@pytest.mark.parametrize("row", math_validation.ROWS, ids=lambda r: r["id"])
def test_control_example(row):
    assert row["status"] == "PASS", row
