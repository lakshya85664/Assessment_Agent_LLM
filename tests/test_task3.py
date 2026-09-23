import json

import pytest

from task3_panel import (
    DISAGREEMENT_THRESHOLD,
    MockProvider,
    evaluate_criterion,
    reconcile_ratings,
    run_panel,
)


def test_small_disagreement_does_not_trigger_reconciliation():
    criterion = {
        "id": "working_code",
        "name": "Working code",
        "description": "Code runs successfully.",
    }

    provider_a = {
        "provider": "vendor_a",
        "rating": 0.9,
        "evidence": "Successful execution.",
    }

    provider_b = {
        "provider": "vendor_b",
        "rating": 0.8,
        "evidence": "Successful execution.",
    }

    result = reconcile_ratings(
        criterion,
        provider_a,
        provider_b,
    )

    assert result["reconciled"] is False
    assert result["difference"] == 0.1
    assert result["final_rating"] == 0.85


def test_large_disagreement_triggers_reconciliation():
    criterion = {
        "id": "robustness",
        "name": "Robustness",
        "description": "System handles failures safely.",
    }

    provider_a = {
        "provider": "vendor_a",
        "rating": 0.95,
        "evidence": "Strong robustness evidence.",
    }

    provider_b = {
        "provider": "vendor_b",
        "rating": 0.50,
        "evidence": "Limited robustness evidence.",
    }

    result = reconcile_ratings(
        criterion,
        provider_a,
        provider_b,
    )

    assert result["reconciled"] is True
    assert result["difference"] == 0.45
    assert result["final_rating"] == 0.725
    assert result["method"] == "average_after_disagreement"


def test_ratings_are_within_valid_range():
    criterion = {
        "id": "measurement",
        "name": "Measurement",
        "description": "Measurements are reported.",
    }

    provider_a = {
        "provider": "vendor_a",
        "rating": 0.7,
        "evidence": "Latency recorded.",
    }

    provider_b = {
        "provider": "vendor_b",
        "rating": 0.8,
        "evidence": "Latency recorded.",
    }

    result = reconcile_ratings(
        criterion,
        provider_a,
        provider_b,
    )

    assert 0.0 <= result["final_rating"] <= 1.0


def test_invalid_rating_is_rejected():
    criterion = {
        "id": "code_quality",
        "name": "Code quality",
        "description": "Code is maintainable.",
    }

    provider_a = {
        "provider": "vendor_a",
        "rating": 1.5,
        "evidence": "Invalid rating.",
    }

    provider_b = {
        "provider": "vendor_b",
        "rating": 0.8,
        "evidence": "Valid rating.",
    }

    with pytest.raises(
        ValueError,
        match="between 0.0 and 1.0",
    ):
        reconcile_ratings(
            criterion,
            provider_a,
            provider_b,
        )


def test_full_panel_uses_two_providers():
    rubric = {
        "criteria": [
            {
                "id": "working_code",
                "name": "Working code",
                "description": "Code works.",
            },
            {
                "id": "robustness",
                "name": "Robustness",
                "description": "System handles errors.",
            },
        ]
    }

    evidence = {
        "criteria": {
            "working_code": {
                "evidence": "Return code was zero.",
            },
            "robustness": {
                "evidence": "Timeout handling exists.",
            },
        }
    }

    provider_a = MockProvider(
        "vendor_a",
        {
            "working_code": 0.9,
            "robustness": 0.95,
        },
    )

    provider_b = MockProvider(
        "vendor_b",
        {
            "working_code": 0.8,
            "robustness": 0.50,
        },
    )

    report = run_panel(
        rubric,
        evidence,
        provider_a,
        provider_b,
    )

    assert len(report["criteria"]) == 2

    working_code = report["criteria"][0]
    robustness = report["criteria"][1]

    assert working_code["final_rating"] == 0.85
    assert working_code["reconciliation"]["reconciled"] is False

    assert robustness["final_rating"] == 0.725
    assert robustness["reconciliation"]["reconciled"] is True


def test_disagreement_threshold_is_configured():
    assert DISAGREEMENT_THRESHOLD == 0.20