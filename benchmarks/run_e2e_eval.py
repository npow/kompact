"""End-to-end evaluation through proxy chain.

Sends requests through HTTP proxies in parallel, scores responses.

Architecture:
  Baseline:  → claude-relay (:9091) → claude -p → Anthropic
  Kompact:   → kompact (:7878) → claude-relay (:9091) → claude -p → Anthropic
  Headroom:  → headroom (:7879) → claude-relay (:9091) → claude -p → Anthropic

Usage:
    python benchmarks/run_e2e_eval.py                          # all datasets, full
    python benchmarks/run_e2e_eval.py --dataset bfcl           # single dataset
    python benchmarks/run_e2e_eval.py -n 50 --workers 20      # 50 per dataset, 20 parallel
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from suite.datasets import DATASET_LOADERS

PROXIES = {
    "Baseline": "http://localhost:8084",
    "Kompact": "http://localhost:7878",
    "Headroom": "http://localhost:7879",
    "LLMLingua-2": "http://localhost:7880",
}


def call_proxy(url: str, context: str, question: str, model: str = "haiku") -> str:
    """Send a chat completion request to a proxy and return the response."""
    if question:
        content = f"{context}\n\nQuestion: {question}\n\nAnswer concisely."
    else:
        content = context + "\n\nWhat is the key issue described above? Answer concisely."

    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": content}],
    }).encode()

    req = urllib.request.Request(
        f"{url}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[ERROR: {e}]"


def eval_one(args_tuple):
    idx, example, proxy_name, proxy_url, model = args_tuple
    context = example.get("context", "")
    question = example.get("question", "")
    response = call_proxy(proxy_url, context, question, model)
    return idx, proxy_name, response


def score_response(answer, response):
    if not answer:
        return {"f1": 1.0, "contains": 1.0, "recall": 1.0}
    if not response or response.startswith("[ERROR") or response.startswith("[TIMEOUT"):
        return {"f1": 0.0, "contains": 0.0, "recall": 0.0}

    contains = 1.0 if answer.lower() in response.lower() else 0.0

    from context_bench.metrics.quality import f1_score, recall_score
    return {
        "f1": f1_score(response, answer),
        "contains": contains,
        "recall": recall_score(response, answer),
    }


def run_system(examples, proxy_name, proxy_url, model, workers):
    """Run all examples through one proxy with N workers."""
    tasks = [(i, ex, proxy_name, proxy_url, model) for i, ex in enumerate(examples)]
    responses = [None] * len(examples)
    done = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(eval_one, t): t[0] for t in tasks}
        for future in as_completed(futures):
            idx, name, response = future.result()
            responses[idx] = response
            done += 1
            if done % 10 == 0:
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                eta = (len(examples) - done) / rate if rate > 0 else 0
                print(f"  {name}: {done}/{len(examples)} ({rate:.1f}/s, ETA {eta:.0f}s)",
                      file=sys.stderr)

    return responses


def main():
    parser = argparse.ArgumentParser(description="E2E proxy evaluation (parallel)")
    parser.add_argument("--dataset", type=str, default="all",
                        choices=list(DATASET_LOADERS.keys()) + ["all"])
    parser.add_argument("-n", type=int, default=0, help="Limit per dataset (0=full)")
    parser.add_argument("--model", type=str, default="haiku")
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--systems", type=str, nargs="+",
                        default=["Baseline", "Kompact", "Headroom"],
                        help="Systems to test")
    args = parser.parse_args()

    # Verify proxies are up
    for name in args.systems:
        url = PROXIES[name]
        try:
            req = urllib.request.Request(f"{url}/health")
            with urllib.request.urlopen(req, timeout=5) as resp:
                print(f"  {name} ({url}): ok", file=sys.stderr)
        except Exception as e:
            print(f"  {name} ({url}): UNREACHABLE - {e}", file=sys.stderr)
            sys.exit(1)

    if args.dataset == "all":
        datasets_to_run = ["bfcl", "hotpotqa", "swebench_verified"]
    else:
        datasets_to_run = [args.dataset]

    all_results = []

    for ds_name in datasets_to_run:
        n = args.n if args.n > 0 else 999_999
        print(f"\n=== {ds_name} ===", file=sys.stderr)
        t0 = time.time()
        try:
            examples = DATASET_LOADERS[ds_name](n=n)
            examples = [ex for ex in examples if ex.get("context")]
        except Exception as e:
            print(f"  Error: {e}", file=sys.stderr)
            continue

        print(f"  {len(examples)} examples, {args.workers} workers", file=sys.stderr)

        # Run each system
        system_scores = {}
        for sys_name in args.systems:
            responses = run_system(
                examples, sys_name, PROXIES[sys_name], args.model, args.workers
            )
            scores = []
            for i, ex in enumerate(examples):
                scores.append(score_response(ex.get("answer", ""), responses[i]))
            system_scores[sys_name] = scores

        elapsed = time.time() - t0

        # Print results
        def avg(scores_list, key):
            return sum(s[key] for s in scores_list) / len(scores_list) if scores_list else 0

        print(f"\n### {ds_name} ({len(examples)} examples, {elapsed:.0f}s)")
        print()
        print("| System | F1 | Contains | Recall |")
        print("|--------|----|----------|--------|")
        for sys_name in args.systems:
            sc = system_scores[sys_name]
            print(f"| {sys_name} | {avg(sc, 'f1'):.1%} | {avg(sc, 'contains'):.1%} "
                  f"| {avg(sc, 'recall'):.1%} |")
        print()

        all_results.append({
            "dataset": ds_name,
            "n": len(examples),
            **{f"{s}_contains": avg(system_scores[s], "contains") for s in args.systems},
            **{f"{s}_f1": avg(system_scores[s], "f1") for s in args.systems},
        })

    # Summary
    if len(all_results) > 1:
        print("\n### Summary")
        print()
        header = "| Dataset | N |"
        sep = "|---------|---|"
        for s in args.systems:
            header += f" {s} |"
            sep += "---|"
        print(header)
        print(sep)
        for r in all_results:
            row = f"| {r['dataset']} | {r['n']:,} |"
            for s in args.systems:
                row += f" {r[f'{s}_contains']:.1%} |"
            print(row)
        print()


if __name__ == "__main__":
    main()
