import json
import time
from pathlib import Path

import pytest

from task3_panel import MockProvider, run_panel

from guardrails import (
    GuardrailViolation,
    TokenBudget,
    StepLimiter,
    retry_with_backoff,
    validate_timeout,
    validate_no_secrets,
    validate_candidate_path,
    quarantine_candidate,
    network_policy_description,
)


def test_token_budget_allows_usage_within_limit():
    budget = TokenBudget(limit=100)

    budget.consume(40)
    budget.consume(30)

    assert budget.used == 70
    assert budget.remaining == 30


def test_token_budget_blocks_overuse():
    budget = TokenBudget(limit=100)

    budget.consume(80)

    with pytest.raises(
        GuardrailViolation,
        match="Token budget exceeded",
    ):
        budget.consume(21)

    assert budget.used == 80


def test_step_limiter_blocks_excess_steps():
    limiter = StepLimiter(limit=2)

    assert limiter.next_step("step_1") == 1
    assert limiter.next_step("step_2") == 2

    with pytest.raises(
        GuardrailViolation,
        match="Step limit exceeded",
    ):
        limiter.next_step("step_3")


def test_timeout_validation():
    assert validate_timeout(5) == 5.0

    with pytest.raises(
        ValueError,
        match="Timeout must be greater than zero",
    ):
        validate_timeout(0)


def test_retry_with_backoff_retries_then_succeeds():
    attempts = {"count": 0}

    def flaky_operation():
        attempts["count"] += 1

        if attempts["count"] < 3:
            raise RuntimeError("temporary failure")

        return "success"

    result = retry_with_backoff(
        flaky_operation,
        max_retries=2,
        backoff_base=0,
        operation_name="test_operation",
    )

    assert result == "success"
    assert attempts["count"] == 3


def test_retry_with_backoff_stops_after_limit():
    attempts = {"count": 0}

    def failing_operation():
        attempts["count"] += 1
        raise RuntimeError("permanent failure")

    with pytest.raises(
        RuntimeError,
        match="permanent failure",
    ):
        retry_with_backoff(
            failing_operation,
            max_retries=2,
            backoff_base=0,
            operation_name="failing_operation",
        )

    assert attempts["count"] == 3


def test_secret_detection_blocks_candidate_content():
    secret_text = (
        "OPENAI_API_KEY="
        "sk-test123456789012345678901234"
    )

    with pytest.raises(
        GuardrailViolation,
        match="Potential secret detected",
    ):
        validate_no_secrets(
            secret_text,
            source="test_candidate",
        )


def test_secret_free_content_passes():
    validate_no_secrets(
        "This is ordinary candidate code.",
        source="test_candidate",
    )


def test_candidate_path_validation(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    result = validate_candidate_path(candidate)

    assert result == candidate


def test_invalid_candidate_is_rejected(tmp_path):
    missing = tmp_path / "missing"

    with pytest.raises(
        GuardrailViolation,
        match="does not exist",
    ):
        validate_candidate_path(missing)


def test_quarantine_records_reason(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    result = quarantine_candidate(
        candidate,
        "Unsafe candidate",
    )

    assert result["status"] == "quarantined"
    assert result["candidate"] == str(candidate)
    assert result["reason"] == "Unsafe candidate"


def test_network_policy_disables_network():
    policy = network_policy_description()

    assert policy["network_allowed"] is False
    assert policy["enforcement"] == "python_socket_block"
    assert policy["security_level"] == "defense_in_depth"

def test_panel_step_limit_is_enforced():
    rubric = {
        "criteria": [
            {
                "id": "criterion_1",
                "name": "Criterion 1",
            },
            {
                "id": "criterion_2",
                "name": "Criterion 2",
            },
        ]
    }

    evidence = {
        "criteria": {
            "criterion_1": {
                "evidence": "Evidence one.",
            },
            "criterion_2": {
                "evidence": "Evidence two.",
            },
        }
    }

    provider_a = MockProvider(
        "vendor_a",
        {
            "criterion_1": 0.8,
            "criterion_2": 0.8,
        },
    )

    provider_b = MockProvider(
        "vendor_b",
        {
            "criterion_1": 0.8,
            "criterion_2": 0.8,
        },
    )

    with pytest.raises(
        GuardrailViolation,
        match="Step limit exceeded",
    ):
        run_panel(
            rubric,
            evidence,
            provider_a,
            provider_b,
            step_limit=2,
        )


def test_panel_token_budget_is_enforced():
    rubric = {
        "criteria": [
            {
                "id": "criterion_1",
                "name": "Criterion 1",
            },
        ]
    }

    evidence = {
        "criteria": {
            "criterion_1": {
                "evidence": "A" * 400,
            },
        }
    }

    provider_a = MockProvider(
        "vendor_a",
        {
            "criterion_1": 0.8,
        },
    )

    provider_b = MockProvider(
        "vendor_b",
        {
            "criterion_1": 0.8,
        },
    )

    with pytest.raises(
        GuardrailViolation,
        match="Token budget exceeded",
    ):
        run_panel(
            rubric,
            evidence,
            provider_a,
            provider_b,
            token_budget=10,
        )


def test_panel_guardrails_allow_normal_execution():
    rubric = {
        "criteria": [
            {
                "id": "criterion_1",
                "name": "Criterion 1",
            },
        ]
    }

    evidence = {
        "criteria": {
            "criterion_1": {
                "evidence": "Normal evidence.",
            },
        }
    }

    provider_a = MockProvider(
        "vendor_a",
        {
            "criterion_1": 0.8,
        },
    )

    provider_b = MockProvider(
        "vendor_b",
        {
            "criterion_1": 0.9,
        },
    )

    result = run_panel(
        rubric,
        evidence,
        provider_a,
        provider_b,
        step_limit=10,
        token_budget=1000,
    )

    assert len(result["criteria"]) == 1
    assert result["criteria"][0]["final_rating"] == 0.85
    assert result["step_limit"]["used"] == 2
    assert result["token_budget"]["used"] > 0