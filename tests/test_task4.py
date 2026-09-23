import copy
import json

import pytest

from report_generator import build_report, markdown_report


def load_data():
    with open("rubric.json", encoding="utf-8") as file:
        rubric = json.load(file)

    with open(
        "outputs/task2_evidence.json",
        encoding="utf-8",
    ) as file:
        evidence = json.load(file)

    with open(
        "outputs/task3_panel_result.json",
        encoding="utf-8",
    ) as file:
        panel = json.load(file)

    return rubric, evidence, panel


def test_build_final_report():
    """Valid rubric, evidence and panel produce a final report."""

    rubric, evidence, panel = load_data()

    report = build_report(
        rubric,
        evidence,
        panel,
    )

    assert report["report_version"] == "1.0"
    assert report["total_marks"] == 100
    assert report["awarded_marks"] == 85.25
    assert report["percentage"] == 85.25
    assert len(report["criteria"]) == 7


def test_report_contains_all_required_criteria():
    """Every rubric criterion appears in the final report."""

    rubric, evidence, panel = load_data()

    report = build_report(
        rubric,
        evidence,
        panel,
    )

    rubric_ids = {
        item["id"]
        for item in rubric["criteria"]
    }

    report_ids = {
        item["id"]
        for item in report["criteria"]
    }

    assert report_ids == rubric_ids


def test_report_contains_evidence_and_remediation():
    """Every criterion contains evidence and remediation fields."""

    rubric, evidence, panel = load_data()

    report = build_report(
        rubric,
        evidence,
        panel,
    )

    for criterion in report["criteria"]:
        assert "evidence" in criterion
        assert "remediation" in criterion
        assert isinstance(
            criterion["evidence"],
            str,
        )
        assert isinstance(
            criterion["remediation"],
            str,
        )


def test_report_contains_provider_results():
    """Every criterion contains both provider results."""

    rubric, evidence, panel = load_data()

    report = build_report(
        rubric,
        evidence,
        panel,
    )

    for criterion in report["criteria"]:
        providers = criterion["providers"]

        assert len(providers) == 2

        provider_names = {
            provider["provider"]
            for provider in providers
        }

        assert provider_names == {
            "mock_vendor_a",
            "mock_vendor_b",
        }


def test_markdown_report_contains_required_sections():
    """Markdown report contains the major reviewer sections."""

    rubric, evidence, panel = load_data()

    report = build_report(
        rubric,
        evidence,
        panel,
    )

    markdown = markdown_report(report)

    assert "# Topic 17 Assessment Agent" in markdown
    assert "## Overall Result" in markdown
    assert "## Model Panel" in markdown
    assert "## Criterion Results" in markdown
    assert "## Provider Results" in markdown
    assert "Working code" in markdown
    assert "Robustness" in markdown


def test_missing_panel_criterion_is_rejected():
    """A panel missing a rubric criterion must be rejected."""

    rubric, evidence, panel = load_data()

    broken_panel = copy.deepcopy(panel)

    broken_panel["criteria"] = [
        item
        for item in broken_panel["criteria"]
        if item["criterion_id"] != "robustness"
    ]

    with pytest.raises(
        ValueError,
        match="Panel result missing criterion",
    ):
        build_report(
            rubric,
            evidence,
            broken_panel,
        )


def test_invalid_panel_rating_is_rejected():
    """Panel ratings outside 0.0 to 1.0 are rejected."""

    rubric, evidence, panel = load_data()

    broken_panel = copy.deepcopy(panel)

    broken_panel["criteria"][0]["final_rating"] = 1.5

    with pytest.raises(
        ValueError,
        match="Invalid final rating",
    ):
        build_report(
            rubric,
            evidence,
            broken_panel,
        )


def test_rubric_weight_mismatch_is_rejected():
    """The report rejects an invalid rubric total."""

    rubric, evidence, panel = load_data()

    broken_rubric = copy.deepcopy(rubric)

    broken_rubric["criteria"][0]["marks"] = 30

    with pytest.raises(
        ValueError,
        match="Rubric criterion marks do not match",
    ):
        build_report(
            broken_rubric,
            evidence,
            panel,
        )