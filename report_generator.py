import argparse
import json
import time
from pathlib import Path
from typing import Any


TRACE_DIR = Path("traces")
TRACE_FILE = TRACE_DIR / "task4_report.jsonl"

MAX_REPORT_CHARS = 20000


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
    """Clear the Task 4 trace."""
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    TRACE_FILE.write_text("", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    """Load and validate a JSON object."""
    if not path.exists():
        raise FileNotFoundError(f"File does not exist: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")

    return data


def validate_panel_report(panel: dict[str, Any]) -> None:
    """Validate the minimum structure required from Task 3."""
    if "panel" not in panel:
        raise ValueError("Panel report is missing 'panel'.")

    if "criteria" not in panel:
        raise ValueError("Panel report is missing 'criteria'.")

    if not isinstance(panel["criteria"], list):
        raise ValueError("Panel criteria must be a list.")

    for item in panel["criteria"]:
        required = [
            "criterion_id",
            "criterion_name",
            "providers",
            "reconciliation",
            "final_rating",
        ]

        for field in required:
            if field not in item:
                raise ValueError(
                    f"Panel criterion missing field: {field}"
                )

        rating = item["final_rating"]

        if (
            isinstance(rating, bool)
            or not isinstance(rating, (int, float))
            or not 0.0 <= float(rating) <= 1.0
        ):
            raise ValueError(
                f"Invalid final rating for "
                f"{item['criterion_id']}"
            )


def validate_rubric(rubric: dict[str, Any]) -> None:
    """Validate the rubric used to construct the report."""
    criteria = rubric.get("criteria")

    if not isinstance(criteria, list) or not criteria:
        raise ValueError("Rubric must contain criteria.")

    total = sum(
        float(item["marks"])
        for item in criteria
    )

    if abs(total - float(rubric["total_marks"])) > 1e-9:
        raise ValueError(
            "Rubric criterion marks do not match total_marks."
        )


def build_report(
    rubric: dict[str, Any],
    evidence: dict[str, Any],
    panel: dict[str, Any],
) -> dict[str, Any]:
    """Build the final machine-readable assessment report."""
    validate_rubric(rubric)
    validate_panel_report(panel)

    panel_by_id = {
        item["criterion_id"]: item
        for item in panel["criteria"]
    }

    evidence_by_id = evidence.get("criteria", {})

    if not isinstance(evidence_by_id, dict):
        raise ValueError("Evidence criteria must be an object.")

    criteria = []
    total_awarded = 0.0

    for rubric_item in rubric["criteria"]:
        criterion_id = rubric_item["id"]

        if criterion_id not in panel_by_id:
            raise ValueError(
                f"Panel result missing criterion: {criterion_id}"
            )

        if criterion_id not in evidence_by_id:
            raise ValueError(
                f"Evidence missing criterion: {criterion_id}"
            )

        panel_item = panel_by_id[criterion_id]
        evidence_item = evidence_by_id[criterion_id]

        max_marks = float(rubric_item["marks"])
        final_rating = float(panel_item["final_rating"])

        awarded_marks = round(
            max_marks * final_rating,
            2,
        )

        total_awarded += awarded_marks

        criterion_result = {
            "id": criterion_id,
            "name": rubric_item["name"],
            "max_marks": max_marks,
            "final_rating": final_rating,
            "awarded_marks": awarded_marks,
            "evidence": evidence_item.get(
                "evidence",
                "",
            ),
            "remediation": evidence_item.get(
                "remediation",
                "",
            ),
            "providers": panel_item["providers"],
            "reconciliation": panel_item["reconciliation"],
        }

        criteria.append(criterion_result)

        write_trace(
            "criterion_report_generated",
            criterion_id=criterion_id,
            final_rating=final_rating,
            awarded_marks=awarded_marks,
        )

    total_awarded = round(total_awarded, 2)

    percentage = round(
        (total_awarded / float(rubric["total_marks"])) * 100,
        2,
    )

    report = {
        "report_version": "1.0",
        "rubric_name": rubric["rubric_name"],
        "rubric_version": rubric["version"],
        "total_marks": rubric["total_marks"],
        "awarded_marks": total_awarded,
        "percentage": percentage,
        "panel": panel["panel"],
        "criteria": criteria,
    }

    encoded = json.dumps(report)

    if len(encoded) > MAX_REPORT_CHARS:
        raise ValueError("Final report exceeds size limit.")

    write_trace(
        "final_report_generated",
        total_marks=rubric["total_marks"],
        awarded_marks=total_awarded,
        percentage=percentage,
        criterion_count=len(criteria),
    )

    return report


def markdown_report(report: dict[str, Any]) -> str:
    """Convert the final JSON report into reviewer-friendly Markdown."""
    lines = [
        f"# {report['rubric_name']}",
        "",
        f"**Report version:** {report['report_version']}",
        "",
        "## Overall Result",
        "",
        f"- **Awarded:** {report['awarded_marks']} / "
        f"{report['total_marks']}",
        f"- **Percentage:** {report['percentage']}%",
        "",
        "## Model Panel",
        "",
        f"- Provider A: `{report['panel']['provider_a']}`",
        f"- Provider B: `{report['panel']['provider_b']}`",
        f"- Disagreement threshold: "
        f"`{report['panel']['disagreement_threshold']}`",
        "",
        "## Criterion Results",
        "",
        "| Criterion | Rating | Marks | Evidence | Remediation |",
        "|---|---:|---:|---|---|",
    ]

    for criterion in report["criteria"]:
        evidence = criterion["evidence"].replace(
            "\n",
            " ",
        )
        remediation = criterion["remediation"].replace(
            "\n",
            " ",
        )

        lines.append(
            f"| {criterion['name']} | "
            f"{criterion['final_rating']:.4f} | "
            f"{criterion['awarded_marks']:.2f} / "
            f"{criterion['max_marks']:.2f} | "
            f"{evidence} | "
            f"{remediation or 'None'} |"
        )

    lines.extend(
        [
            "",
            "## Provider Results",
            "",
        ]
    )

    for criterion in report["criteria"]:
        lines.append(
            f"### {criterion['name']}"
        )
        lines.append("")

        for provider in criterion["providers"]:
            lines.append(
                f"- `{provider['provider']}`: "
                f"rating `{provider['rating']}`"
            )

        reconciliation = criterion["reconciliation"]

        lines.append(
            f"- Reconciled: `{reconciliation['reconciled']}`"
        )
        lines.append(
            f"- Method: `{reconciliation['method']}`"
        )
        lines.append(
            f"- Difference: `{reconciliation['difference']}`"
        )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Topic 17 Task 4 — Report generator"
    )

    parser.add_argument(
        "--rubric",
        default="rubric.json",
    )

    parser.add_argument(
        "--evidence",
        default="outputs/task2_evidence.json",
    )

    parser.add_argument(
        "--panel",
        default="outputs/task3_panel_result.json",
    )

    parser.add_argument(
        "--json-output",
        default="outputs/final_assessment.json",
    )

    parser.add_argument(
        "--markdown-output",
        default="outputs/final_assessment.md",
    )

    args = parser.parse_args()

    clear_trace()

    try:
        write_trace(
            "report_generation_started",
            rubric=args.rubric,
            evidence=args.evidence,
            panel=args.panel,
        )

        rubric = load_json(Path(args.rubric))
        evidence = load_json(Path(args.evidence))
        panel = load_json(Path(args.panel))

        report = build_report(
            rubric=rubric,
            evidence=evidence,
            panel=panel,
        )

        json_path = Path(args.json_output)
        md_path = Path(args.markdown_output)

        json_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        json_path.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )

        md_path.write_text(
            markdown_report(report),
            encoding="utf-8",
        )

        print(json.dumps(report, indent=2))
        print(f"\nJSON report: {json_path}")
        print(f"Markdown report: {md_path}")
        print(f"Trace: {TRACE_FILE}")

        return 0

    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        write_trace(
            "report_generation_failed",
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