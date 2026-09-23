from pathlib import Path

from ingestion import ingest_candidate


def test_successful_candidate_execution(tmp_path: Path):
    """Candidate executes successfully and returns captured output."""

    candidate = tmp_path / "candidate"
    candidate.mkdir()

    entry_point = candidate / "agent.py"
    entry_point.write_text(
        """
print("SUCCESS_CASE")
""",
        encoding="utf-8",
    )

    result = ingest_candidate(candidate)

    assert result["status"] == "success"
    assert result["selected_entry_point"] == "agent.py"
    assert result["execution"]["return_code"] == 0
    assert "SUCCESS_CASE" in result["execution"]["stdout"]
    assert result["execution"]["stderr"] == ""


def test_failed_candidate_execution(tmp_path: Path):
    """Candidate failure is captured instead of crashing the assessor."""

    candidate = tmp_path / "candidate"
    candidate.mkdir()

    entry_point = candidate / "agent.py"
    entry_point.write_text(
        """
print("FAILURE_CASE")
raise RuntimeError("Intentional candidate failure")
""",
        encoding="utf-8",
    )

    result = ingest_candidate(candidate)

    assert result["status"] == "failed"
    assert result["selected_entry_point"] == "agent.py"
    assert result["execution"]["return_code"] != 0
    assert "FAILURE_CASE" in result["execution"]["stdout"]
    assert "RuntimeError" in result["execution"]["stderr"]


def test_invalid_candidate_path(tmp_path: Path):
    """Invalid candidate paths are rejected cleanly."""

    missing_candidate = tmp_path / "does_not_exist"

    result = ingest_candidate(missing_candidate)

    assert result["status"] == "invalid_candidate"
    assert "does not exist" in result["error"]