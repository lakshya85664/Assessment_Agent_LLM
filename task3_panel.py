import json
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from guardrails import (
    DEFAULT_BACKOFF_BASE_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_STEP_LIMIT,
    DEFAULT_TOKEN_BUDGET,
    GuardrailViolation,
    StepLimiter,
    TokenBudget,
    retry_with_backoff,
    validate_no_secrets,
)


TRACE_PATH = Path("traces/task3_panel.jsonl")

DISAGREEMENT_THRESHOLD = 0.20
MAX_HOPS = DEFAULT_STEP_LIMIT
TOKEN_BUDGET = DEFAULT_TOKEN_BUDGET
MAX_RETRIES = DEFAULT_MAX_RETRIES
BACKOFF_BASE_SECONDS = DEFAULT_BACKOFF_BASE_SECONDS


class ModelProvider(ABC):
    """
    Common interface for assessment model providers.
    """

    name = "abstract_provider"

    @abstractmethod
    def evaluate(
        self,
        criterion: dict[str, Any],
        evidence: str,
    ) -> float:
        raise NotImplementedError


class MockProvider(ModelProvider):
    """
    Deterministic provider used for testing and offline assessment.
    """

    def __init__(
        self,
        name: str,
        ratings: dict[str, float],
    ):
        self.name = name
        self.ratings = ratings

    def evaluate(
        self,
        criterion: dict[str, Any],
        evidence: str,
    ) -> float:
        criterion_id = criterion["id"]

        if criterion_id not in self.ratings:
            raise ValueError(
                f"Provider {self.name} has no rating for "
                f"criterion {criterion_id}."
            )

        return float(
            self.ratings[criterion_id]
        )


class OpenAIProvider(ModelProvider):
    """
    Optional OpenAI provider adapter.

    API credentials are read only from the environment and are
    never written into traces or assessment output.
    """

    name = "openai"

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        timeout: float = 20.0,
    ):
        self.model = model
        self.timeout = timeout

    def evaluate(
        self,
        criterion: dict[str, Any],
        evidence: str,
    ) -> float:
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured."
            )

        validate_no_secrets(
            evidence,
            source="openai_provider_evidence",
        )

        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            timeout=self.timeout,
        )

        prompt = (
            "You are evaluating a software project criterion.\n\n"
            f"Criterion: {criterion['name']}\n"
            f"Maximum marks: {criterion.get('marks', 100)}\n\n"
            f"Evidence:\n{evidence}\n\n"
            "Return only a decimal rating from 0.0 to 1.0."
        )

        response = client.responses.create(
            model=self.model,
            input=prompt,
            max_output_tokens=20,
        )

        text = response.output_text.strip()
        rating = float(text)

        if not 0.0 <= rating <= 1.0:
            raise ValueError(
                f"Provider returned invalid rating: {rating}"
            )

        return rating


def write_trace(event: str, **data: Any) -> None:
    """
    Write one structured Task 3 event to JSONL.
    """
    TRACE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    record = {
        "timestamp": time.time(),
        "event": event,
        **data,
    }

    with TRACE_PATH.open(
        "a",
        encoding="utf-8",
    ) as file:
        file.write(
            json.dumps(
                record,
                ensure_ascii=False,
            )
            + "\n"
        )


def validate_rating(
    rating: float,
    provider: str,
    criterion_id: str,
) -> float:
    """
    Validate a model rating.

    Ratings must be between 0.0 and 1.0 inclusive.
    """
    rating = float(rating)

    if not 0.0 <= rating <= 1.0:
        raise ValueError(
            f"Rating for {criterion_id} from {provider} "
            f"must be between 0.0 and 1.0; got {rating}"
        )

    return rating


def reconcile_ratings(
    criterion: dict[str, Any],
    provider_a: dict[str, Any],
    provider_b: dict[str, Any],
    threshold: float = DISAGREEMENT_THRESHOLD,
) -> dict[str, Any]:
    """
    Reconcile two provider results.

    This preserves the original Task 3 API:
        reconcile_ratings(
            criterion,
            provider_a,
            provider_b,
        )

    If the difference exceeds the threshold, the result is marked
    as requiring reconciliation. Both ratings are retained and
    averaged.
    """

    criterion_id = criterion["id"]

    rating_a = validate_rating(
        provider_a["rating"],
        provider_a["provider"],
        criterion_id,
    )

    rating_b = validate_rating(
        provider_b["rating"],
        provider_b["provider"],
        criterion_id,
    )

    difference = abs(
        rating_a - rating_b
    )

    if difference > threshold:
        write_trace(
            "reconciliation_required",
            criterion_id=criterion_id,
            provider_a=provider_a["provider"],
            provider_b=provider_b["provider"],
            rating_a=rating_a,
            rating_b=rating_b,
            difference=difference,
            threshold=threshold,
        )

        return {
            "reconciled": True,
            "final_rating": round(
                (rating_a + rating_b) / 2,
                4,
            ),
            "difference": round(
                difference,
                4,
            ),
            "method": "average_after_disagreement",
            "reason": (
                "Ratings exceeded the disagreement "
                "threshold; both panel ratings were "
                "retained and averaged."
            ),
        }

    return {
        "reconciled": False,
        "final_rating": round(
            (rating_a + rating_b) / 2,
            4,
        ),
        "difference": round(
            difference,
            4,
        ),
        "method": "average",
        "reason": (
            "Ratings were within the disagreement "
            "threshold."
        ),
    }


def evaluate_provider_with_retry(
    provider: ModelProvider,
    criterion: dict[str, Any],
    evidence: str,
) -> float:
    """
    Evaluate one criterion with centralized retry/backoff.
    """

    operation_name = (
        f"{provider.name}:{criterion['id']}"
    )

    def operation():
        return provider.evaluate(
            criterion,
            evidence,
        )

    return retry_with_backoff(
        operation,
        max_retries=MAX_RETRIES,
        backoff_base=BACKOFF_BASE_SECONDS,
        operation_name=operation_name,
    )


def evaluate_criterion(
    criterion: dict[str, Any],
    evidence: str,
    provider_a: ModelProvider,
    provider_b: ModelProvider,
    disagreement_threshold: float = DISAGREEMENT_THRESHOLD,
) -> dict[str, Any]:
    """
    Evaluate one rubric criterion with two providers.

    This preserves the original Task 3 public API.
    """

    write_trace(
        "criterion_evaluation_started",
        criterion_id=criterion["id"],
        provider_a=provider_a.name,
        provider_b=provider_b.name,
    )

    rating_a = evaluate_provider_with_retry(
        provider_a,
        criterion,
        evidence,
    )

    rating_a = validate_rating(
        rating_a,
        provider_a.name,
        criterion["id"],
    )

    rating_b = evaluate_provider_with_retry(
        provider_b,
        criterion,
        evidence,
    )

    rating_b = validate_rating(
        rating_b,
        provider_b.name,
        criterion["id"],
    )

    provider_result_a = {
        "provider": provider_a.name,
        "rating": rating_a,
        "evidence": evidence,
    }

    provider_result_b = {
        "provider": provider_b.name,
        "rating": rating_b,
        "evidence": evidence,
    }

    reconciliation = reconcile_ratings(
        criterion,
        provider_result_a,
        provider_result_b,
        threshold=disagreement_threshold,
    )

    result = {
        "criterion_id": criterion["id"],
        "provider_results": [
            provider_result_a,
            provider_result_b,
        ],
        "final_rating": reconciliation["final_rating"],
        "reconciliation": reconciliation,
    }

    write_trace(
        "criterion_evaluation_completed",
        criterion_id=criterion["id"],
        final_rating=reconciliation["final_rating"],
        reconciled=reconciliation["reconciled"],
    )

    return result


def run_panel(
    rubric: dict[str, Any],
    evidence: dict[str, Any],
    provider_a: ModelProvider,
    provider_b: ModelProvider,
    disagreement_threshold: float = DISAGREEMENT_THRESHOLD,
    token_budget: int = TOKEN_BUDGET,
    step_limit: int = MAX_HOPS,
) -> dict[str, Any]:
    """
    Run the complete two-provider assessment panel.

    This preserves the original Task 3 API:
        run_panel(
            rubric,
            evidence,
            provider_a,
            provider_b,
        )

    Additional optional arguments provide Task 5 guardrails.
    """

    write_trace(
        "panel_started",
        provider_a=provider_a.name,
        provider_b=provider_b.name,
        disagreement_threshold=disagreement_threshold,
        token_budget=token_budget,
        step_limit=step_limit,
    )

    budget = TokenBudget(
        limit=token_budget
    )

    step_limiter = StepLimiter(
        limit=step_limit
    )

    criteria = rubric.get(
        "criteria",
        [],
    )

    # The original tests pass evidence in this structure:
    #
    # {
    #     "criteria": {
    #         "working_code": {
    #             "evidence": "..."
    #         }
    #     }
    # }
    #
    # The actual project evidence file is also supported if it uses
    # a list of criterion objects.
    evidence_container = evidence.get(
        "criteria",
        {},
    )

    results = []

    for criterion in criteria:
        criterion_id = criterion["id"]

        if isinstance(
            evidence_container,
            dict,
        ):
            evidence_item = evidence_container.get(
                criterion_id,
                {},
            )

            criterion_evidence = evidence_item.get(
                "evidence",
                "",
            )

        elif isinstance(
            evidence_container,
            list,
        ):
            criterion_evidence = ""

            for item in evidence_container:
                if item.get("criterion_id") == criterion_id:
                    criterion_evidence = item.get(
                        "evidence",
                        "",
                    )
                    break

        else:
            raise ValueError(
                "Evidence criteria must be a dictionary or list."
            )

        # Estimate token usage conservatively.
        estimated_tokens = max(
            1,
            (
                len(criterion_evidence)
                + len(
                    criterion.get(
                        "name",
                        "",
                    )
                )
            )
            // 4,
        )

        # Two provider evaluations consume the estimated
        # input budget.
        budget.consume(
            estimated_tokens
        )

        step_limiter.next_step(
            f"{provider_a.name}:{criterion_id}"
        )

        budget.consume(
            estimated_tokens
        )

        step_limiter.next_step(
            f"{provider_b.name}:{criterion_id}"
        )

        result = evaluate_criterion(
            criterion=criterion,
            evidence=criterion_evidence,
            provider_a=provider_a,
            provider_b=provider_b,
            disagreement_threshold=disagreement_threshold,
        )

        results.append(result)

    report = {
        "provider_a": provider_a.name,
        "provider_b": provider_b.name,
        "disagreement_threshold": disagreement_threshold,
        "token_budget": {
            "limit": budget.limit,
            "used": budget.used,
            "remaining": budget.remaining,
        },
        "step_limit": {
            "limit": step_limiter.limit,
            "used": step_limiter.steps,
            "remaining": (
                step_limiter.limit
                - step_limiter.steps
            ),
        },
        "criteria": results,
    }

    write_trace(
        "panel_completed",
        criteria_count=len(results),
        token_budget_used=budget.used,
        steps_used=step_limiter.steps,
    )

    return report


def evaluate_panel(
    rubric: dict[str, Any],
    evidence_map: dict[str, str],
    provider_a: ModelProvider,
    provider_b: ModelProvider,
    disagreement_threshold: float = DISAGREEMENT_THRESHOLD,
    token_budget: int = TOKEN_BUDGET,
    step_limit: int = MAX_HOPS,
) -> dict[str, Any]:
    """
    Compatibility wrapper for the newer internal API.

    Converts an evidence map into the original run_panel format.
    """

    evidence = {
        "criteria": {
            criterion_id: {
                "evidence": criterion_evidence,
            }
            for criterion_id, criterion_evidence
            in evidence_map.items()
        }
    }

    return run_panel(
        rubric,
        evidence,
        provider_a,
        provider_b,
        disagreement_threshold=disagreement_threshold,
        token_budget=token_budget,
        step_limit=step_limit,
    )


def default_mock_providers():
    """
    Return the deterministic two-provider configuration used
    by the offline assessment.
    """

    ratings_a = {
        "working_code": 0.90,
        "core_technique": 0.85,
        "testing_evidence": 0.80,
        "robustness": 0.75,
        "measurement": 0.70,
        "traceability": 0.95,
        "code_quality": 0.85,
    }

    ratings_b = {
        "working_code": 1.00,
        "core_technique": 0.85,
        "testing_evidence": 0.80,
        "robustness": 0.75,
        "measurement": 0.80,
        "traceability": 0.95,
        "code_quality": 0.85,
    }

    return (
        MockProvider(
            "mock_vendor_a",
            ratings_a,
        ),
        MockProvider(
            "mock_vendor_b",
            ratings_b,
        ),
    )


def main():
    with open(
        "rubric.json",
        encoding="utf-8",
    ) as file:
        rubric = json.load(file)

    with open(
        "outputs/task2_evidence.json",
        encoding="utf-8",
    ) as file:
        evidence_data = json.load(file)

    provider_a, provider_b = (
        default_mock_providers()
    )

    result = run_panel(
        rubric,
        evidence_data,
        provider_a,
        provider_b,
    )

    output_path = Path(
        "outputs/task3_panel_result.json"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            result,
            file,
            indent=2,
        )

    print(
        json.dumps(
            result,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()