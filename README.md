# Topic 17 — Capstone Assessment Agent

## Project Overview

This project implements an automated **Assessment Agent** for evaluating a candidate repository against a machine-readable rubric.

The system is designed to ingest and execute candidate code safely, evaluate the implementation against weighted criteria, run a model-based assessment panel, generate a final assessment report, and enforce practical guardrails around execution and model usage.

The implementation focuses on five core areas:

1. Candidate ingestion and sandboxed execution
2. Machine-readable rubric evaluation
3. Multi-provider assessment panel with disagreement reconciliation
4. Final assessment report generation
5. Execution and model guardrails

---

## Project Structure

```text
Assessment_Agent_LLM/
├── candidate/
│   └── agent.py
├── ingestion.py
├── rubric.json
├── rubric_engine.py
├── task3_panel.py
├── report_generator.py
├── guardrails.py
├── requirements.txt
├── .gitignore
├── tests/
│   ├── test_task1.py
│   ├── test_task2.py
│   ├── test_task3.py
│   ├── test_task4.py
│   └── test_task5.py
├── traces/
│   ├── task1_ingestion.jsonl
│   ├── task2_rubric.jsonl
│   ├── task3_panel.jsonl
│   ├── task4_report.jsonl
│   └── task5_guardrails.jsonl
└── outputs/
    ├── task2_evidence.json
    ├── task2_rubric_result.json
    ├── task3_panel_result.json
    ├── final_assessment.json
    └── final_assessment.md
```

---

## Environment

- Python: 3.13.9
- OpenAI Python SDK: 1.109.1
- Pydantic: 2.13.5
- Pytest: 8.4.2
- Operating system used for development: Windows
- Candidate execution uses the active Python interpreter
- Optional hosted-model integration is available through the OpenAI provider adapter

---

# Task 1 — Candidate Ingestion

The ingestion system accepts a candidate project directory and detects likely Python entry points.

Preferred entry points are:

```text
agent.py
main.py
app.py
run.py
```

If these are not available, the implementation can fall back to Python files in the candidate directory.

The ingestion process:

- validates the candidate path
- detects entry points
- limits the number of entry points
- executes the selected entry point
- captures stdout
- captures stderr
- records the return code
- applies a timeout
- records execution latency
- handles execution failures
- scans candidate source for common secrets
- quarantines invalid candidates
- records structured JSONL evidence

The candidate used for the assessment is:

```python
def main():
    print("Candidate agent executed successfully.")
    print("Assessment agent ingestion test passed.")


if __name__ == "__main__":
    main()
```

### Run

```cmd
python ingestion.py
```

### Tests

```cmd
python -m pytest tests\test_task1.py -q
```

Verified result:

```text
3 passed
```

The ingestion trace is written to:

```text
traces/task1_ingestion.jsonl
```

---

# Task 2 — Rubric Engine

The assessment uses a machine-readable rubric stored in:

```text
rubric.json
```

The rubric contains seven weighted criteria:

| Criterion | Weight |
|---|---:|
| Working Code | 25 |
| Core Technique | 20 |
| Testing Evidence | 15 |
| Robustness | 15 |
| Measurement | 10 |
| Traceability | 10 |
| Code Quality | 5 |
| **Total** | **100** |

The rubric engine evaluates the supplied evidence and produces a criterion-level result.

The generated evidence and rubric result are stored in:

```text
outputs/task2_evidence.json
outputs/task2_rubric_result.json
```

The rubric trace is stored in:

```text
traces/task2_rubric.jsonl
```

The resulting rubric assessment was:

```text
Score: 88.5 / 100
Percentage: 88.5%
```

### Tests

```cmd
python -m pytest tests\test_task2.py -q
```

Verified result:

```text
5 passed
```

---

# Task 3 — Multi-Model Assessment Panel

Task 3 implements a model-provider abstraction for assessment.

The panel contains:

- a provider interface
- deterministic mock providers
- an optional OpenAI provider adapter
- rating validation
- token budgeting
- step limiting
- retry and backoff handling
- disagreement detection
- reconciliation
- structured tracing

The disagreement threshold is:

```text
0.20
```

When the difference between provider ratings exceeds the threshold, the disagreement is explicitly recorded and the panel reconciles the ratings using the implemented averaging strategy.

The current project uses **deterministic mock providers for reproducible assessment tests**. The OpenAI provider adapter is available, but the project does not claim that two live external vendors were called during the verified run.

The panel trace is written to:

```text
traces/task3_panel.jsonl
```

The panel result is written to:

```text
outputs/task3_panel_result.json
```

### Tests

```cmd
python -m pytest tests\test_task3.py -q
```

Verified result:

```text
6 passed
```

---

# Task 4 — Final Assessment Report

The report generator combines:

- the rubric definition
- Task 2 evidence
- Task 3 panel results
- criterion-level marks
- provider results
- reconciliation information
- remediation information

The final generated assessment is:

```text
Score: 85.25 / 100
Percentage: 85.25%
```

Criterion results:

| Criterion | Score | Marks |
|---|---:|---:|
| Working Code | 0.95 | 23.75 / 25 |
| Core Technique | 0.85 | 17.00 / 20 |
| Testing Evidence | 0.80 | 12.00 / 15 |
| Robustness | 0.75 | 11.25 / 15 |
| Measurement | 0.75 | 7.50 / 10 |
| Traceability | 0.95 | 9.50 / 10 |
| Code Quality | 0.85 | 4.25 / 5 |
| **Total** | | **85.25 / 100** |

Generated files:

```text
outputs/final_assessment.json
outputs/final_assessment.md
```

The report trace is:

```text
traces/task4_report.jsonl
```

### Tests

```cmd
python -m pytest tests\test_task4.py -q
```

Verified result:

```text
8 passed
```

---

# Task 5 — Guardrails

The guardrail layer provides controls around candidate execution and assessment-panel operations.

Implemented controls include:

- token budget
- step limit
- timeout validation
- retry with backoff
- secret detection
- candidate path validation
- candidate quarantine
- structured guardrail tracing
- candidate network policy enforcement

Default configuration includes:

```text
Token budget: 2000
Step limit: 10
Timeout: 10 seconds
Maximum retries: 2
Backoff base: 0.25 seconds
```

Candidate source is checked for common secret patterns before execution.

Invalid candidates can be quarantined instead of being executed.

The ingestion layer also applies a Python-level network restriction to candidate execution. This is a **defense-in-depth Python-level control**, not a claim of kernel-level isolation.

Guardrail events are recorded in:

```text
traces/task5_guardrails.jsonl
```

### Tests

```cmd
python -m pytest tests\test_task5.py -q
```

Verified result:

```text
15 passed
```

---

# Complete Testing Evidence

Run the complete test suite with:

```cmd
python -m pytest -q
```

Final verified result:

```text
37 passed in 0.30s
```

Test breakdown:

| Task | Tests Passed |
|---|---:|
| Task 1 — Ingestion | 3 |
| Task 2 — Rubric Engine | 5 |
| Task 3 — Assessment Panel | 6 |
| Task 4 — Report | 8 |
| Task 5 — Guardrails | 15 |
| **Total** | **37** |

---

# Setup

Open Windows CMD and move to the project directory:

```cmd
cd /d "E:\Tayana_Projects\LLMs for Agent Development\Assessment_Agent_LLM"
```

Create the virtual environment:

```cmd
python -m venv .venv
```

Activate it:

```cmd
.venv\Scripts\activate
```

Install the pinned dependencies:

```cmd
pip install -r requirements.txt
```

---

# Running the Complete Assessment Pipeline

Run Task 1:

```cmd
python ingestion.py
```

Run Task 2:

```cmd
python rubric_engine.py
```

Run Task 3:

```cmd
python task3_panel.py
```

Run Task 4:

```cmd
python report_generator.py
```

Run the complete automated test suite:

```cmd
python -m pytest -q
```

---

# Structured Evidence

The project maintains structured JSONL traces for each major stage:

```text
traces/task1_ingestion.jsonl
traces/task2_rubric.jsonl
traces/task3_panel.jsonl
traces/task4_report.jsonl
traces/task5_guardrails.jsonl
```

These traces provide machine-readable evidence of execution, evaluation, panel activity, report generation, and guardrail behavior.

Generated assessment artifacts are stored under:

```text
outputs/
```

---

# Secret and GitHub Safety

The project includes a `.gitignore` that excludes:

- `.env`
- virtual environments
- Python cache files
- test caches
- build artifacts
- logs
- temporary files
- local model binaries
- temporary candidate directories

API keys and other secrets must never be committed to GitHub.

Before publishing the repository, verify that no `.env` file, API key, or other credential is included in tracked files.

---

# Submission Artifacts

The Topic 17 submission contains:

- Candidate assessment implementation
- Task 1 ingestion implementation
- Task 2 rubric engine
- Task 3 assessment panel
- Task 4 report generator
- Task 5 guardrails
- Automated tests
- Pinned `requirements.txt`
- `.gitignore`
- Structured JSONL traces
- Assessment output files
- README
- Final submission PDF
- Loom presentation script

The optional stretch task was not implemented.

---

# Reflection

This project gave me practical experience in designing an automated assessment system rather than simply running an LLM and accepting its output. The first task helped me understand the importance of controlled candidate ingestion. Detecting entry points, capturing stdout and stderr, handling failures, applying timeouts, and recording structured traces made the execution process observable and repeatable.

The rubric engine showed how an assessment can be converted into a machine-readable structure. Instead of producing only a general evaluation, the system evaluates separate criteria with explicit weights and evidence. This makes the final score easier to inspect and reproduce.

The assessment panel introduced another important concept: model outputs can disagree. The implementation therefore validates ratings, detects disagreements using a defined threshold, and records how the disagreement is reconciled. I also learned the importance of keeping deterministic mock providers for reliable automated testing while maintaining an adapter for a real model provider.

The report-generation task connected the earlier components into a complete assessment pipeline. Finally, the guardrails task reinforced that an agentic system needs operational controls in addition to core functionality. Token budgets, step limits, timeouts, retries, secret detection, candidate validation, quarantine, and structured traces make the system more controlled and easier to debug.

Overall, this capstone helped me understand how individual LLM and agent-development techniques can be combined into a practical, testable, and observable assessment system. The final implementation contains five connected tasks, structured evidence, automated tests, and reproducible outputs rather than relying only on manually observed behavior.
