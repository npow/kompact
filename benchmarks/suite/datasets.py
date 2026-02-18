"""Download and load real datasets from HuggingFace for benchmarking.

Supported datasets:
  QA (prose context — baseline comparison):
    - HotpotQA (distractor split) — multi-hop QA, Wikipedia paragraphs
    - LongBench v2 — long-context understanding, diverse domains

  Agentic / tool-calling (Kompact's target domain):
    - BFCL (Berkeley Function Calling Leaderboard) — real API schemas + user queries
    - Glaive Function Calling v2 — 113K tool-calling conversations with schemas

Requires: pip install datasets
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _check_datasets_installed() -> None:
    try:
        import datasets  # noqa: F401
    except ImportError:
        raise ImportError(
            "The 'datasets' package is required for dataset-backed evaluation.\n"
            "Install it with: uv pip install datasets"
        )


# ---------------------------------------------------------------------------
# QA datasets (prose context)
# ---------------------------------------------------------------------------

def load_hotpotqa(n: int = 100) -> list[dict[str, Any]]:
    """Load HotpotQA distractor split examples."""
    _check_datasets_installed()
    from datasets import load_dataset

    ds = load_dataset("hotpot_qa", "distractor", split="validation")

    examples = []
    for item in ds.select(range(min(n, len(ds)))):
        paragraphs = []
        for title, sentences in zip(item["context"]["title"], item["context"]["sentences"]):
            paragraphs.append(f"## {title}\n{''.join(sentences)}")
        context = "\n\n".join(paragraphs)

        examples.append({
            "id": item.get("id", len(examples)),
            "context": context,
            "question": item["question"],
            "answer": item["answer"],
        })

    return examples


def load_longbench(n: int = 100, subset: str | None = None) -> list[dict[str, Any]]:
    """Load LongBench v2 examples."""
    _check_datasets_installed()
    from datasets import load_dataset

    ds = load_dataset("THUDM/LongBench-v2", split="train")

    if subset:
        ds = ds.filter(lambda x: subset.lower() in x["domain"].lower())

    examples = []
    for item in ds.select(range(min(n, len(ds)))):
        question_with_choices = (
            f"{item['question']}\n"
            f"A) {item['choice_A']}\n"
            f"B) {item['choice_B']}\n"
            f"C) {item['choice_C']}\n"
            f"D) {item['choice_D']}"
        )

        examples.append({
            "id": len(examples),
            "context": item["context"],
            "question": question_with_choices,
            "answer": item["answer"],
        })

    return examples


# ---------------------------------------------------------------------------
# Agentic / tool-calling datasets
# ---------------------------------------------------------------------------

def load_bfcl(n: int = 100) -> list[dict[str, Any]]:
    """Load BFCL (Berkeley Function Calling Leaderboard) examples.

    Uses multiple subsets: live_multiple, live_simple, rest, exec_multiple.
    Context = JSON tool schemas. Answer = ground truth function call (needle).
    """
    _check_datasets_installed()
    from huggingface_hub import snapshot_download

    local_dir = snapshot_download(
        "gorilla-llm/Berkeley-Function-Calling-Leaderboard",
        repo_type="dataset",
    )
    snap = Path(local_dir)

    data: list[dict] = []
    for filename in [
        "BFCL_v3_live_multiple.json",
        "BFCL_v3_live_simple.json",
        "BFCL_v3_rest.json",
        "BFCL_v3_exec_multiple.json",
    ]:
        f = snap / filename
        if f.exists():
            with open(f) as fh:
                for line in fh:
                    try:
                        data.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    examples = []
    for item in data[:n]:
        functions = item.get("function", [])
        if not functions:
            continue

        context = json.dumps(functions, indent=2)

        question_parts = []
        q = item.get("question", [])
        if isinstance(q, list):
            for turn in q:
                if isinstance(turn, list):
                    for msg in turn:
                        if isinstance(msg, dict) and msg.get("content"):
                            question_parts.append(msg["content"])
                elif isinstance(turn, dict) and turn.get("content"):
                    question_parts.append(turn["content"])
        question = "\n".join(question_parts) if question_parts else str(q)

        gt = item.get("ground_truth", [])
        if isinstance(gt, list) and gt:
            answer = gt[0] if isinstance(gt[0], str) else json.dumps(gt[0])
        else:
            answer = functions[0].get("name", "") if functions else ""

        examples.append({
            "id": item.get("id", len(examples)),
            "context": context,
            "question": question,
            "answer": answer,
        })

    return examples


def load_glaive(n: int = 100) -> list[dict[str, Any]]:
    """Load Glaive Function Calling v2 examples.

    Context = system prompt with JSON tool schemas. Answer = function name (needle).
    """
    _check_datasets_installed()
    from datasets import load_dataset

    ds = load_dataset("glaiveai/glaive-function-calling-v2", split="train")

    examples = []
    count = 0
    for item in ds:
        if count >= n:
            break

        system = item.get("system", "")
        chat = item.get("chat", "")

        if '"name"' not in system or "{" not in system:
            continue

        # Extract function call from chat as needle
        func_call = ""
        for line in chat.split("\n"):
            if "FUNCTION CALL:" in line or '"name"' in line:
                idx = line.find("{")
                if idx >= 0:
                    try:
                        call = json.loads(line[idx:])
                        func_call = json.dumps(call, separators=(",", ":"))
                        break
                    except json.JSONDecodeError:
                        pass
            if "<functioncall>" in line.lower():
                idx = line.find("{")
                if idx >= 0:
                    try:
                        call = json.loads(line[idx:])
                        func_call = json.dumps(call, separators=(",", ":"))
                        break
                    except json.JSONDecodeError:
                        pass

        if not func_call:
            continue

        idx = system.find("{")
        if idx < 0:
            continue
        context = system[idx:]

        # Extract function name as needle
        import re
        func_name = ""
        try:
            schema = json.loads(context)
            if isinstance(schema, dict):
                func_name = schema.get("name", "")
            elif isinstance(schema, list) and schema:
                func_name = schema[0].get("name", "")
        except json.JSONDecodeError:
            m = re.search(r'"name"\s*:\s*"([^"]+)"', context)
            if m:
                func_name = m.group(1)

        if not func_name:
            continue

        question = ""
        for line in chat.split("\n"):
            if line.startswith("USER:"):
                question = line[5:].strip()
                break

        examples.append({
            "id": f"glaive_{count}",
            "context": context,
            "question": question,
            "answer": func_name,
        })
        count += 1

    return examples


def load_swebench(n: int = 999_999) -> list[dict[str, Any]]:
    """Load SWE-bench full dataset (2,294 examples) via context-bench."""
    from context_bench.datasets.agent_traces import swebench
    return swebench(n=n)


def load_swebench_verified(n: int = 999_999) -> list[dict[str, Any]]:
    """Load SWE-bench Verified (500 human-validated examples) via context-bench."""
    from context_bench.datasets.agent_traces import swebench_verified
    return swebench_verified(n=n)


def load_swebench_lite(n: int = 999_999) -> list[dict[str, Any]]:
    """Load SWE-bench Lite (300 examples) via context-bench."""
    from context_bench.datasets.agent_traces import swebench_lite
    return swebench_lite(n=n)


DATASET_LOADERS = {
    "hotpotqa": load_hotpotqa,
    "longbench": load_longbench,
    "bfcl": load_bfcl,
    "glaive": load_glaive,
    "swebench": load_swebench,
    "swebench_verified": load_swebench_verified,
    "swebench_lite": load_swebench_lite,
}

AGENTIC_DATASETS = ["bfcl", "glaive"]
QA_DATASETS = ["hotpotqa", "longbench"]
CODING_DATASETS = ["swebench", "swebench_verified", "swebench_lite"]
