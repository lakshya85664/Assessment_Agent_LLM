# Topic 16 — Implement Open Source Models in Code

## Project Overview

This project implements open-source/local LLM inference behind an OpenAI-compatible interface and adds practical reliability mechanisms around models that do not provide all hosted-model features natively.

The implementation uses **Ollama** with **Qwen 2.5 3B Instruct** locally and the **OpenAI API** as the hosted fallback/benchmark model.

### Environment
- Local server: Ollama
- Local model: `qwen2.5:3b-instruct`
- OpenAI-compatible endpoint: `http://localhost:11434/v1`
- Python: 3.13.9
- Hosted benchmark model: `gpt-4o-mini`

## Project Structure

```text
Open_Source_Model_In_Code/
├── local_models.py
├── task2_json.py
├── task3_tool_shim.py
├── task4_benchmark.py
├── task5_fallback_router.py
├── requirements.txt
├── .gitignore
├── tests/
│   ├── test_task1.py
│   ├── test_task2.py
│   ├── test_task3.py
│   ├── test_task4.py
│   └── test_task5.py
├── traces/
│   ├── task1_local_serving.jsonl
│   ├── task2_json.jsonl
│   ├── task3_tool_shim.jsonl
│   ├── task4_benchmark.jsonl
│   └── task5_fallback_router.jsonl
└── outputs/
    └── task4_benchmark_results.json
```

## Setup

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
ollama --version
ollama pull qwen2.5:3b-instruct
ollama list
```

Create `.env` in the project root:

```text
OPENAI_API_KEY=your_key_here
```

The `.env` file is excluded by `.gitignore` and must never be committed.

Verify without displaying the key:

```cmd
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(bool(os.getenv('OPENAI_API_KEY')))"
```

## Task 1 — Local Serving

Ollama serves Qwen 2.5 3B Instruct and the Python OpenAI SDK communicates with the OpenAI-compatible local endpoint. The implementation includes timeout handling, bounded retries, exponential backoff, input token budget, response validation, hop limit, and JSONL tracing.

Run:

```cmd
python local_models.py --live
```

Tests:

```cmd
python -m pytest tests\test_task1.py -q
```

Verified result: **7 passed in 4.60s**

## Task 2 — Grammar-Constrained JSON

Native structured output was disabled. The model is instructed to return one JSON object, followed by JSON parsing and Pydantic validation. Markdown fences, malformed JSON, invalid enum values, and unexpected fields are rejected.

Run:

```cmd
python task2_json.py --live
```

Tests:

```cmd
python -m pytest tests\test_task2.py -q
```

Verified result: **8 passed in 7.23s**

## Task 3 — Tool Calling Shim

A strict prompt-based protocol supports an allowlisted `word_count` tool. Tool requests are parsed and validated before execution, the tool result is returned to the model, and the final response is validated.

Run:

```cmd
python task3_tool_shim.py --live
```

Tests:

```cmd
python -m pytest tests\test_task3.py -q
```

Verified result: **9 passed in 6.35s**

## Task 4 — Benchmark

Twenty fixed prompts were evaluated by both the local model and `gpt-4o-mini`. Measurements include latency, input/output/total tokens, output tokens/sec, deterministic keyword-rubric quality, and hosted API cost.

Run:

```cmd
python task4_benchmark.py --live
```

| Metric | Local | Hosted |
|---|---:|---:|
| Prompts | 20 | 20 |
| Successful | 20/20 | 20/20 |
| Success rate | 100% | 100% |
| Average latency | 0.9104 s | 1.6633 s |
| Output tokens/sec | 52.0808 | 24.0783 |
| Average rubric quality | 0.8917 | 0.9583 |
| Input tokens | 1,050 | 983 |
| Output tokens | 444 | 858 |
| Total tokens | 1,494 | 1,841 |
| API cost | $0 | $0.00066225 |

The local API cost is zero because local inference has no API charge; hardware/electricity costs are excluded. The quality score is a deterministic keyword rubric for this 20-prompt workload, not a human preference score.

Evidence:
- `outputs/task4_benchmark_results.json`
- `traces/task4_benchmark.jsonl`

## Task 5 — Fallback Router

The router attempts the local model first. A deterministic confidence score is calculated from expected keywords. If local confidence is below `0.75` or the local request/validation fails, the hosted model is invoked as fallback.

```text
Request
   ↓
Local Qwen 2.5 3B
   ↓
Validate + confidence
   ├── >= 0.75 → local result
   └── < 0.75 → hosted fallback
```

Normal live route:

```text
Status: success
Source: local
Fallback used: False
Confidence: 1.0
```

Controlled fallback route:

```text
Status: success
Source: hosted_fallback
Fallback used: True
Fallback reason: Local confidence below threshold.
```

The forced test deliberately used impossible expected keywords; its zero confidence therefore reflects the test condition, not an independent quality assessment of the hosted response.

Run:

```cmd
python task5_fallback_router.py --live
python task5_fallback_router.py --force-fallback
```

Tests:

```cmd
python -m pytest tests\test_task5.py -q
```

Verified result: **12 passed in 1.46s**

Evidence: `traces/task5_fallback_router.jsonl`

## Guardrails

- **Step limit:** bounded loops/API hops with trace evidence.
- **Timeout:** 20-second per-call timeout.
- **Retry:** maximum 3 attempts with exponential backoff.
- **Token budget:** conservative input estimation and rejection above the configured budget.
- **Validation:** model output is validated before being returned; invalid output is quarantined.
- **Secret hygiene:** API keys are loaded from environment/`.env` and are not written into source, results, or traces.
- `.gitignore` excludes `.env` and related secret files.

## Testing Evidence

Complete suite:

```cmd
python -m pytest tests -q
```

Final verified result:

```text
46 passed in 14.23s
```

Breakdown:
- Task 1: 7
- Task 2: 8
- Task 3: 9
- Task 4: 10
- Task 5: 12
- **Total: 46**

## Submission Artifacts

The submission contains source code for Tasks 1–5, automated tests, pinned dependencies, `.gitignore`, structured traces, benchmark results, README, PDF, and presentation material. The optional stretch task was not implemented.

## Reflection

This project gave me practical experience with running open-source language models locally and building reliability layers around them. The first task helped me understand how Ollama can expose a local model through an OpenAI-compatible API, allowing existing SDK-based application code to interact with a local model without changing the overall client pattern.

The JSON task showed the difference between requesting structured output and actually validating it. Because the local model was not treated as inherently reliable, the implementation used strict prompting, JSON parsing, Pydantic validation, and quarantine behavior. The tool-calling task extended the same idea into an explicit protocol, where a model-generated tool request had to be validated before the allowlisted tool was executed.

The benchmark was useful for understanding that model comparison depends heavily on the measurement method. In the 20-prompt experiment, the local model had lower measured latency and higher output-token throughput, while the hosted model achieved a higher score on the project's deterministic keyword rubric. The benchmark therefore became evidence for this specific workload rather than a general model ranking.

Finally, the fallback router demonstrated how a local model can be used as the first inference path while retaining a hosted model as a recovery mechanism. The project also reinforced the importance of operational safeguards: timeouts, bounded retries, token budgets, validation, step limits, traces, and secret hygiene. Overall, the work moved the implementation from simply calling a model toward designing a more controlled and observable LLM system.
