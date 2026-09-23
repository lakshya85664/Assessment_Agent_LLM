import json
from pathlib import Path

import pytest

from rubric_engine import grade_rubric, load_json, validate_rubric


RUBRIC_PATH = Path("rubric.json")
EVIDENCE_PATH = Path("outputs/task2_evidence.json")


def load_test_data():
    rubric = load_json(RUBRIC_PATH)
    evidence = load_json(EVIDENCE_PATH)
    return rubric, evidence


def test_valid_rubric_grading():
    """Valid rubric and evidence produce the expected score."""

    rubric, evidence = load_test_data()

    report = grade_rubric(rubric, evidence)

    assert report["total_marks"] == 100
    assert report["awarded_marks"] == 88.5
    assert report["percentage"] == 88.5
    assert len(report["criteria"]) == 7


def test_invalid_rating_is_rejected():
    """Ratings outside 0.0 to 1.0 must be rejected."""

    rubric, evidence = load_test_data()

    evidence["criteria"]["working_code"]["rating"] = 1.5

    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        grade_rubric(rubric, evidence)


def test_missing_criterion_is_rejected():
    """Evidence must contain every rubric criterion."""

    rubric, evidence = load_test_data()

    del evidence["criteria"]["traceability"]

    with pytest.raises(ValueError, match="Missing evidence"):
        grade_rubric(rubric, evidence)


def test_unknown_criterion_is_rejected():
    """Evidence cannot contain criteria absent from the rubric."""

    rubric, evidence = load_test_data()

    evidence["criteria"]["unknown_criterion"] = {
        "rating": 1.0,
        "evidence": "Invalid criterion",
        "remediation": ""
    }

    with pytest.raises(ValueError, match="unknown criteria"):
        grade_rubric(rubric, evidence)


def test_rubric_weight_mismatch_is_rejected():
    """Criterion weights must sum to the declared total."""

    rubric, _ = load_test_data()

    rubric["criteria"][0]["marks"] = 30

    with pytest.raises(
        ValueError,
        match="do not sum to rubric total_marks",
    ):
        validate_rubric(rubric)