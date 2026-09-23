import argparse
import json
import time
from pathlib import Path
from typing import Any


TRACE_DIR = Path("traces")
TRACE_FILE = TRACE_DIR / "task2_rubric.jsonl"

MIN_RATING = 0.0
MAX_RATING = 1.0


def write_trace(event: str, **data: Any) -> None:
    """Write one structured JSONL trace event."""
    TRACE_DIR.mkdir(parents=True, exist_ok=True)

    record = {
        "event": event,
        "timestamp": time.time(),
        **data,
    }

    with TRACE_FILE.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def clear_trace() -> None:
    """Clear the Task 2 trace."""
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    TRACE_FILE.write_text("", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""
    if not path.exists():
        raise FileNotFoundError(f"File does not exist: {path}")

    if not path.is_file():
        raise ValueError(f"Expected a file: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in {path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}")

    return data


def validate_rubric(rubric: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate the machine-readable rubric."""
    if rubric.get("version") != "1.0":
        raise ValueError("Unsupported rubric version.")

    criteria = rubric.get("criteria")

    if not isinstance(criteria, list) or not criteria:
        raise ValueError("Rubric must contain a non-empty criteria list.")

    total_marks = rubric.get("total_marks")

    if not isinstance(total_marks, (int, float)) or total_marks <= 0:
        raise ValueError("Rubric total_marks must be positive.")

    seen_ids: set[str] = set()
    calculated_total = 0.0

    for criterion in criteria:
        if not isinstance(criterion, dict):
            raise ValueError("Each criterion must be a JSON object.")

        required = ["id", "name", "marks", "description"]

        for field in required:
            if field not in criterion:
                raise ValueError(
                    f"Criterion is missing required field: {field}"
                )

        criterion_id = criterion["id"]

        if not isinstance(criterion_id, str) or not criterion_id:
            raise ValueError("Criterion id must be a non-empty string.")

        if criterion_id in seen_ids:
            raise ValueError(
                f"Duplicate criterion id: {criterion_id}"
            )

        seen_ids.add(criterion_id)

        marks = criterion["marks"]

        if not isinstance(marks, (int, float)) or marks <= 0:
            raise ValueError(
                f"Criterion marks must be positive: {criterion_id}"
            )

        calculated_total += float(marks)

    if abs(calculated_total - float(total_marks)) > 1e-9:
        raise ValueError(
            "Criterion marks do not sum to rubric total_marks: "
            f"{calculated_total} != {total_marks}"
        )

    write_trace(
        "rubric_validated",
        criterion_count=len(criteria),
        total_marks=total_marks,
    )

    return criteria


def validate_evidence(
    evidence: dict[str, Any],
    criteria: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Validate evidence for every rubric criterion."""
    evidence_items = evidence.get("criteria")

    if not isinstance(evidence_items, dict):
        raise ValueError(
            "Evidence must contain a 'criteria' object."
        )

    criterion_ids = {criterion["id"] for criterion in criteria}

    evidence_ids = set(evidence_items.keys())

    missing = criterion_ids - evidence_ids
    unknown = evidence_ids - criterion_ids

    if missing:
        raise ValueError(
            "Missing evidence for criteria: "
            + ", ".join(sorted(missing))
        )

    if unknown:
        raise ValueError(
            "Evidence contains unknown criteria: "
            + ", ".join(sorted(unknown))
        )

    validated: dict[str, dict[str, Any]] = {}

    for criterion in criteria:
        criterion_id = criterion["id"]
        item = evidence_items[criterion_id]

        if not isinstance(item, dict):
            raise ValueError(
                f"Evidence for {criterion_id} must be an object."
            )

        if "rating" not in item:
            raise ValueError(
                f"Evidence for {criterion_id} is missing rating."
            )

        rating = item["rating"]

        if (
            not isinstance(rating, (int, float))
            or isinstance(rating, bool)
            or not MIN_RATING <= float(rating) <= MAX_RATING
        ):
            raise ValueError(
                f"Rating for {criterion_id} must be between "
                "0.0 and 1.0."
            )

        evidence_text = item.get("evidence", "")

        if not isinstance(evidence_text, str):
            raise ValueError(
                f"Evidence text for {criterion_id} must be a string."
            )

        remediation = item.get("remediation", "")

        if not isinstance(remediation, str):
            raise ValueError(
                f"Remediation for {criterion_id} must be a string."
            )

        validated[criterion_id] = {
            "rating": float(rating),
            "evidence": evidence_text,
            "remediation": remediation,
        }

    write_trace(
        "evidence_validated",
        criterion_count=len(validated),
    )

    return validated


def grade_rubric(
    rubric: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Apply validated ratings to the weighted rubric."""
    criteria = validate_rubric(rubric)
    validated_evidence = validate_evidence(evidence, criteria)

    results = []
    total_score = 0.0

    for criterion in criteria:
        criterion_id = criterion["id"]
        max_marks = float(criterion["marks"])

        item = validated_evidence[criterion_id]
        rating = item["rating"]

        awarded_marks = round(max_marks * rating, 2)

        result = {
            "id": criterion_id,
            "name": criterion["name"],
            "max_marks": max_marks,
            "rating": rating,
            "awarded_marks": awarded_marks,
            "evidence": item["evidence"],
            "remediation": item["remediation"],
        }

        results.append(result)
        total_score += awarded_marks

        write_trace(
            "criterion_graded",
            criterion_id=criterion_id,
            rating=rating,
            awarded_marks=awarded_marks,
            max_marks=max_marks,
        )

    total_score = round(total_score, 2)

    report = {
        "rubric_name": rubric["rubric_name"],
        "rubric_version": rubric["version"],
        "total_marks": rubric["total_marks"],
        "awarded_marks": total_score,
        "percentage": round(
            (total_score / float(rubric["total_marks"])) * 100,
            2,
        ),
        "criteria": results,
    }

    write_trace(
        "rubric_grading_completed",
        awarded_marks=total_score,
        total_marks=rubric["total_marks"],
        percentage=report["percentage"],
    )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Topic 17 Task 2 — Rubric engine"
    )

    parser.add_argument(
        "rubric",
        help="Path to rubric JSON",
    )

    parser.add_argument(
        "evidence",
        help="Path to evidence JSON",
    )

    parser.add_argument(
        "--output",
        default="outputs/task2_rubric_result.json",
        help="Output report path",
    )

    args = parser.parse_args()

    clear_trace()

    try:
        rubric_path = Path(args.rubric)
        evidence_path = Path(args.evidence)

        write_trace(
            "rubric_engine_started",
            rubric=str(rubric_path),
            evidence=str(evidence_path),
        )

        rubric = load_json(rubric_path)
        evidence = load_json(evidence_path)

        report = grade_rubric(
            rubric=rubric,
            evidence=evidence,
        )

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )

        print(json.dumps(report, indent=2))
        print(f"\nSaved report: {output_path}")
        print(f"Trace: {TRACE_FILE}")

        return 0

    except (FileNotFoundError, ValueError) as exc:
        write_trace(
            "rubric_engine_failed",
            error=str(exc),
        )

        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": str(exc),
                },
                indent=2,
            )
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())