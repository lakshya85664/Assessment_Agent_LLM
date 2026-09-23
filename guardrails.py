import json
import re
import time
from pathlib import Path
from typing import Any, Callable


DEFAULT_TOKEN_BUDGET = 2000
DEFAULT_STEP_LIMIT = 10
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_BASE_SECONDS = 0.25

TRACE_PATH = Path("traces/task5_guardrails.jsonl")


class GuardrailViolation(Exception):
    """Raised when a configured guardrail is violated."""


def _write_trace(event: str, **data: Any) -> None:
    """Write one structured guardrail event to JSONL."""
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": time.time(),
        "event": event,
        **data,
    }

    with TRACE_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


class TokenBudget:
    """Track estimated token usage against a fixed budget."""

    def __init__(self, limit: int = DEFAULT_TOKEN_BUDGET):
        if limit <= 0:
            raise ValueError("Token budget must be greater than zero.")

        self.limit = limit
        self.used = 0

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    def consume(self, tokens: int) -> None:
        if tokens < 0:
            raise ValueError("Token usage cannot be negative.")

        if self.used + tokens > self.limit:
            _write_trace(
                "token_budget_exceeded",
                limit=self.limit,
                used=self.used,
                requested=tokens,
            )
            raise GuardrailViolation(
                f"Token budget exceeded: limit={self.limit}, "
                f"used={self.used}, requested={tokens}"
            )

        self.used += tokens

        _write_trace(
            "token_budget_consumed",
            limit=self.limit,
            used=self.used,
            remaining=self.remaining,
            consumed=tokens,
        )


class StepLimiter:
    """Limit the number of agent/tool execution steps."""

    def __init__(self, limit: int = DEFAULT_STEP_LIMIT):
        if limit <= 0:
            raise ValueError("Step limit must be greater than zero.")

        self.limit = limit
        self.steps = 0

    def next_step(self, name: str = "") -> int:
        if self.steps >= self.limit:
            _write_trace(
                "step_limit_exceeded",
                limit=self.limit,
                steps=self.steps,
                attempted_step=name,
            )
            raise GuardrailViolation(
                f"Step limit exceeded: limit={self.limit}, "
                f"attempted_step={name}"
            )

        self.steps += 1

        _write_trace(
            "step_started",
            step=self.steps,
            limit=self.limit,
            name=name,
        )

        return self.steps


def validate_timeout(timeout_seconds: float) -> float:
    """Validate and normalize a timeout value."""
    if timeout_seconds <= 0:
        raise ValueError("Timeout must be greater than zero.")

    _write_trace(
        "timeout_validated",
        timeout_seconds=timeout_seconds,
    )

    return float(timeout_seconds)


def retry_with_backoff(
    operation: Callable[[], Any],
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_base: float = DEFAULT_BACKOFF_BASE_SECONDS,
    operation_name: str = "operation",
) -> Any:
    """
    Retry an operation after failures using exponential backoff.

    max_retries means additional attempts after the initial attempt.
    """
    if max_retries < 0:
        raise ValueError("max_retries cannot be negative.")

    if backoff_base < 0:
        raise ValueError("backoff_base cannot be negative.")

    attempt = 0

    while True:
        try:
            result = operation()

            _write_trace(
                "operation_succeeded",
                operation=operation_name,
                attempt=attempt + 1,
            )

            return result

        except Exception as exc:
            if attempt >= max_retries:
                _write_trace(
                    "operation_failed",
                    operation=operation_name,
                    attempts=attempt + 1,
                    error=str(exc),
                )
                raise

            delay = backoff_base * (2 ** attempt)

            _write_trace(
                "operation_retry",
                operation=operation_name,
                attempt=attempt + 1,
                next_attempt=attempt + 2,
                delay_seconds=delay,
                error=str(exc),
            )

            if delay > 0:
                time.sleep(delay)

            attempt += 1


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}"),
]


def find_secrets(text: str) -> list[str]:
    """Return redacted indicators for strings matching known secret patterns."""
    findings = []

    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            findings.append(pattern.pattern)

    return findings


def validate_no_secrets(text: str, *, source: str = "unknown") -> None:
    """Reject text containing patterns that look like credentials."""
    findings = find_secrets(text)

    if findings:
        _write_trace(
            "secret_detected",
            source=source,
            pattern_count=len(findings),
        )

        raise GuardrailViolation(
            f"Potential secret detected in {source}; content quarantined."
        )

    _write_trace(
        "secret_scan_passed",
        source=source,
    )


def validate_candidate_path(candidate_path: str | Path) -> Path:
    """Validate that the candidate exists and is a directory."""
    path = Path(candidate_path)

    if not path.exists():
        _write_trace(
            "candidate_validation_failed",
            reason="path_not_found",
            candidate=str(path),
        )
        raise GuardrailViolation(
            f"Candidate path does not exist: {path}"
        )

    if not path.is_dir():
        _write_trace(
            "candidate_validation_failed",
            reason="not_a_directory",
            candidate=str(path),
        )
        raise GuardrailViolation(
            f"Candidate path is not a directory: {path}"
        )

    _write_trace(
        "candidate_validation_passed",
        candidate=str(path),
    )

    return path


def quarantine_candidate(
    candidate_path: str | Path,
    reason: str,
) -> dict[str, Any]:
    """
    Record a quarantine decision without executing or modifying the candidate.
    """
    path = Path(candidate_path)

    record = {
        "status": "quarantined",
        "candidate": str(path),
        "reason": reason,
        "timestamp": time.time(),
    }

    _write_trace(
        "candidate_quarantined",
        **record,
    )

    return record


def network_policy_description() -> dict[str, Any]:
    """
    Describe the network policy used by the assessment agent.

    The actual Python-level socket blocking is applied by the candidate
    execution wrapper in ingestion.py.
    """
    policy = {
        "network_allowed": False,
        "enforcement": "python_socket_block",
        "security_level": "defense_in_depth",
        "note": (
            "This is not a kernel-level sandbox. Production deployments "
            "should use a container, VM, or OS-level network isolation."
        ),
    }

    _write_trace(
        "network_policy_declared",
        **policy,
    )

    return policy