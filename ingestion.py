import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from guardrails import (
    DEFAULT_TIMEOUT_SECONDS,
    GuardrailViolation,
    _write_trace,
    find_secrets,
    network_policy_description,
    quarantine_candidate,
    validate_candidate_path,
    validate_timeout,
)


TRACE_PATH = Path("traces/task1_ingestion.jsonl")

PREFERRED_ENTRY_POINTS = [
    "agent.py",
    "main.py",
    "app.py",
    "run.py",
]

MAX_ENTRY_POINTS = 5
MAX_OUTPUT_CHARS = 4000
MAX_TIMEOUT_SECONDS = 30


def write_trace(event, **data):
    """
    Write one structured Task 1 ingestion event to JSONL.
    """
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": time.time(),
        "event": event,
        **data,
    }

    with TRACE_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def detect_entry_points(candidate_path):
    """
    Detect preferred Python entry points first.

    If none of the preferred names exist, fall back to
    root-level Python files.
    """
    preferred = [
        name
        for name in PREFERRED_ENTRY_POINTS
        if (candidate_path / name).is_file()
    ]

    if preferred:
        return preferred[:MAX_ENTRY_POINTS]

    fallback = sorted(
        path.name
        for path in candidate_path.glob("*.py")
        if path.is_file()
    )

    return fallback[:MAX_ENTRY_POINTS]


def create_network_blocker():
    """
    Create a temporary Python sitecustomize module that blocks
    Python socket creation for the candidate process.

    This is defense-in-depth only and is NOT a kernel-level sandbox.
    """
    temp_dir = Path(
        tempfile.mkdtemp(
            prefix="assessment_network_guard_"
        )
    )

    sitecustomize = temp_dir / "sitecustomize.py"

    sitecustomize.write_text(
        """
import socket


def _blocked(*args, **kwargs):
    raise RuntimeError(
        "Network access is disabled for candidate execution."
    )


socket.socket = _blocked
socket.create_connection = _blocked
socket.create_server = _blocked
socket.socketpair = _blocked
""".strip()
        + "\n",
        encoding="utf-8",
    )

    return temp_dir


def build_candidate_environment(network_guard_dir):
    """
    Build a restricted environment for candidate execution.

    Common API credentials are removed so candidate code does not
    inherit them from the assessment-agent environment.
    """
    environment = os.environ.copy()

    existing_pythonpath = environment.get(
        "PYTHONPATH",
        "",
    )

    if existing_pythonpath:
        environment["PYTHONPATH"] = (
            str(network_guard_dir)
            + os.pathsep
            + existing_pythonpath
        )
    else:
        environment["PYTHONPATH"] = str(
            network_guard_dir
        )

    secret_names = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AZURE_OPENAI_API_KEY",
    ]

    for name in secret_names:
        environment.pop(name, None)

    environment[
        "ASSESSMENT_AGENT_NETWORK"
    ] = "disabled"

    return environment


def scan_candidate_for_secrets(candidate_path):
    """
    Scan Python source files for obvious credential patterns.
    """
    findings = []

    for python_file in candidate_path.glob("*.py"):
        try:
            content = python_file.read_text(
                encoding="utf-8"
            )
        except UnicodeDecodeError:
            continue

        matches = find_secrets(content)

        if matches:
            findings.append(
                {
                    "file": str(python_file),
                    "pattern_count": len(matches),
                }
            )

    if findings:
        _write_trace(
            "candidate_secret_scan_failed",
            candidate=str(candidate_path),
            findings=findings,
        )

        raise GuardrailViolation(
            "Potential secret detected in candidate source."
        )

    _write_trace(
        "candidate_secret_scan_passed",
        candidate=str(candidate_path),
    )


def execute_entry_point(
    candidate_path,
    entry_point,
    timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
):
    """
    Execute one candidate entry point with:

    - timeout protection
    - Python-level network blocking
    - secret removal from candidate environment
    - stdout/stderr capture
    """

    timeout_seconds = validate_timeout(
        timeout_seconds
    )

    if timeout_seconds > MAX_TIMEOUT_SECONDS:
        raise ValueError(
            f"Timeout cannot exceed "
            f"{MAX_TIMEOUT_SECONDS} seconds."
        )

    network_guard_dir = create_network_blocker()

    environment = build_candidate_environment(
        network_guard_dir
    )

    command = [
        sys.executable,
        "-B",
        entry_point,
    ]

    write_trace(
        "candidate_execution_started",
        entry_point=entry_point,
        timeout_seconds=timeout_seconds,
    )

    started = time.perf_counter()

    try:
        completed = subprocess.run(
            command,
            cwd=candidate_path,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=environment,
        )

        latency = round(
            time.perf_counter() - started,
            4,
        )

        stdout = completed.stdout[
            :MAX_OUTPUT_CHARS
        ]

        stderr = completed.stderr[
            :MAX_OUTPUT_CHARS
        ]

        status = (
            "success"
            if completed.returncode == 0
            else "failed"
        )

        result = {
            "status": status,
            "return_code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "latency_seconds": latency,
        }

        write_trace(
            "candidate_execution_completed",
            entry_point=entry_point,
            status=status,
            return_code=completed.returncode,
            latency_seconds=latency,
        )

        return result

    except subprocess.TimeoutExpired as exc:
        latency = round(
            time.perf_counter() - started,
            4,
        )

        stdout = (
            exc.stdout.decode(
                errors="replace"
            )
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )

        stderr = (
            exc.stderr.decode(
                errors="replace"
            )
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )

        result = {
            "status": "timeout",
            "return_code": None,
            "stdout": stdout[
                :MAX_OUTPUT_CHARS
            ],
            "stderr": stderr[
                :MAX_OUTPUT_CHARS
            ],
            "latency_seconds": latency,
        }

        write_trace(
            "candidate_execution_timeout",
            entry_point=entry_point,
            timeout_seconds=timeout_seconds,
            latency_seconds=latency,
        )

        return result

    finally:
        try:
            for child in network_guard_dir.iterdir():
                child.unlink()

            network_guard_dir.rmdir()

        except OSError:
            pass


def run_candidate(
    candidate_path,
    timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
):
    """
    Main guarded candidate-ingestion pipeline.

    Returns a stable result structure for both successful
    and rejected candidates.
    """

    write_trace(
        "ingestion_started",
        candidate=str(candidate_path),
    )

    # ---------------------------------------------------------
    # Candidate path validation
    # ---------------------------------------------------------
    try:
        candidate_path = validate_candidate_path(
            candidate_path
        )

    except GuardrailViolation as exc:
        error_message = str(exc)

        quarantine = quarantine_candidate(
            candidate_path,
            error_message,
        )

        write_trace(
            "ingestion_completed",
            status="invalid_candidate",
            error=error_message,
            quarantine=quarantine,
        )

        return {
            "status": "invalid_candidate",
            "entry_points": [],
            "selected_entry_point": None,
            "execution": None,
            "error": error_message,
            "quarantine": quarantine,
        }

    # ---------------------------------------------------------
    # Network policy
    # ---------------------------------------------------------
    network_policy = network_policy_description()

    write_trace(
        "network_policy_applied",
        **network_policy,
    )

    # ---------------------------------------------------------
    # Secret scanning
    # ---------------------------------------------------------
    try:
        scan_candidate_for_secrets(
            candidate_path
        )

    except GuardrailViolation as exc:
        error_message = str(exc)

        quarantine = quarantine_candidate(
            candidate_path,
            error_message,
        )

        write_trace(
            "ingestion_completed",
            status="quarantined",
            error=error_message,
            quarantine=quarantine,
        )

        return {
            "status": "quarantined",
            "entry_points": [],
            "selected_entry_point": None,
            "execution": None,
            "error": error_message,
            "quarantine": quarantine,
        }

    # ---------------------------------------------------------
    # Entry-point detection
    # ---------------------------------------------------------
    entry_points = detect_entry_points(
        candidate_path
    )

    write_trace(
        "entry_points_detected",
        entry_points=entry_points,
    )

    if not entry_points:
        error_message = (
            "No Python entry point detected."
        )

        quarantine = quarantine_candidate(
            candidate_path,
            error_message,
        )

        write_trace(
            "ingestion_completed",
            status="no_entry_point",
            error=error_message,
            quarantine=quarantine,
        )

        return {
            "status": "no_entry_point",
            "entry_points": [],
            "selected_entry_point": None,
            "execution": None,
            "error": error_message,
            "quarantine": quarantine,
        }

    # ---------------------------------------------------------
    # Candidate execution
    # ---------------------------------------------------------
    selected_entry_point = entry_points[0]

    execution = execute_entry_point(
        candidate_path=candidate_path,
        entry_point=selected_entry_point,
        timeout_seconds=timeout_seconds,
    )

    error_message = None

    if execution["status"] != "success":
        error_message = execution.get(
            "stderr",
            "",
        )

    write_trace(
        "ingestion_completed",
        status=execution["status"],
        selected_entry_point=selected_entry_point,
        error=error_message,
    )

    return {
        "status": execution["status"],
        "entry_points": entry_points,
        "selected_entry_point": selected_entry_point,
        "execution": execution,
        "error": error_message,
        "quarantine": None,
    }


def ingest_candidate(
    candidate_path,
    timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
):
    """
    Backward-compatible public API used by the
    existing Task 1 tests.

    Delegates to the guarded candidate execution pipeline.
    """
    return run_candidate(
        candidate_path=candidate_path,
        timeout_seconds=timeout_seconds,
    )


def main():
    candidate_path = Path("candidate")

    result = run_candidate(
        candidate_path
    )

    print(
        f"status: {result['status']}"
    )

    print(
        f"entry_points: "
        f"{result['entry_points']}"
    )

    print(
        "selected_entry_point:",
        result["selected_entry_point"],
    )

    execution = result.get(
        "execution"
    )

    if execution:
        print(
            "execution status:",
            execution["status"],
        )

        print(
            "return_code:",
            execution["return_code"],
        )

        print(
            "stdout:",
            execution["stdout"],
        )

        print(
            "stderr:",
            execution["stderr"],
        )

        print(
            "latency_seconds:",
            execution[
                "latency_seconds"
            ],
        )

    if result.get("error"):
        print(
            "error:",
            result["error"],
        )

    if result.get("quarantine"):
        print(
            "quarantine:",
            json.dumps(
                result["quarantine"],
                indent=2,
            ),
        )


if __name__ == "__main__":
    main()