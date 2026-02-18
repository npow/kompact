"""Benchmark on real industry-standard datasets using context-bench.

Runs all compression approaches against BFCL, Glaive, HotpotQA, and LongBench.

Measures:
  - Compression ratio (1 - output_tokens/input_tokens)
  - NIAH (needle-in-a-haystack: does the answer survive?)
  - Answer recall (substring + token recall fallback)
  - Effective ratio (retry-adjusted compression)
  - Cost-of-Pass (tokens per successful task, arXiv:2504.13359)

Usage:
    uv run python benchmarks/run_dataset_eval.py                          # All datasets
    uv run python benchmarks/run_dataset_eval.py --dataset bfcl           # Single dataset
    uv run python benchmarks/run_dataset_eval.py --dataset bfcl -n 50 --exclude llmlingua headroom
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from context_bench import evaluate
from context_bench.metrics import CompressionRatio, CostOfPass, MeanScore
from context_bench.reporters import to_markdown

from suite.custom_metrics import EffectiveRatio, MeanNIAH
from suite.datasets import AGENTIC_DATASETS, DATASET_LOADERS, QA_DATASETS
from suite.evaluators import NeedleEvaluator
from suite.metrics import PRICING, estimate_monthly_cost
from suite.systems import ALL_SYSTEMS

REPORTS_DIR = Path(__file__).parent / "reports"


def print_cost_impact(result) -> None:
    """Print monthly cost impact table from an EvalResult."""
    summary = result.summary
    terse = summary.get("Kompact Pipeline", {})
    nocomp = summary.get("No Compression", {})

    if not terse or not nocomp:
        return

    avg_orig = nocomp.get("mean_input_tokens", 0)
    avg_comp = terse.get("mean_output_tokens", 0)
    if not avg_orig or not avg_comp:
        return

    print(f"\n  Cost impact (1,000 requests/day, avg {avg_orig:,.0f} -> {avg_comp:,.0f} tokens):")
    print(f"  {'Model':<22} {'Before/mo':>12} {'After/mo':>12} {'Savings/mo':>12}")
    print(f"  {'-'*22} {'-'*12} {'-'*12} {'-'*12}")
    for model in PRICING:
        before = estimate_monthly_cost(int(avg_orig), 1000, model)
        after = estimate_monthly_cost(int(avg_comp), 1000, model)
        print(f"  {model:<22} ${before:>10,.2f} ${after:>10,.2f} ${before - after:>10,.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Real dataset benchmark evaluation")
    parser.add_argument(
        "--dataset",
        type=str,
        choices=list(DATASET_LOADERS.keys()) + ["all", "agentic", "qa"],
        default="all",
        help="Dataset to evaluate",
    )
    parser.add_argument(
        "-n",
        type=int,
        default=100,
        help="Number of examples per dataset (default: 100, 0 = all available)",
    )
    parser.add_argument(
        "--exclude",
        type=str,
        nargs="+",
        default=[],
        help="Systems to exclude (e.g., --exclude llmlingua truncation)",
    )
    args = parser.parse_args()

    # Filter systems based on --exclude
    systems = ALL_SYSTEMS
    if args.exclude:
        exclude_lower = [e.lower() for e in args.exclude]
        systems = [
            s for s in ALL_SYSTEMS
            if not any(ex in s.name.lower() for ex in exclude_lower)
        ]
        print(f"Excluded: {args.exclude}")
        print(f"Running systems: {[s.name for s in systems]}")

    if args.dataset == "all":
        datasets_to_run = list(DATASET_LOADERS.keys())
    elif args.dataset == "agentic":
        datasets_to_run = AGENTIC_DATASETS
    elif args.dataset == "qa":
        datasets_to_run = QA_DATASETS
    else:
        datasets_to_run = [args.dataset]

    all_md_parts: list[str] = []

    for ds_name in datasets_to_run:
        n_label = "all" if args.n == 0 else str(args.n)
        print(f"\nLoading {ds_name} ({n_label} examples)...")
        try:
            loader = DATASET_LOADERS[ds_name]
            examples = loader(n=args.n if args.n > 0 else 999_999)
        except ImportError as e:
            print(f"  Skipping: {e}")
            continue
        except Exception as e:
            print(f"  Error loading {ds_name}: {e}")
            continue

        # Filter to examples with context
        examples = [ex for ex in examples if ex.get("context")]
        if not examples:
            print("  No examples with context, skipping")
            continue

        print(f"  Loaded {len(examples)} examples. Running evaluation...")

        result = evaluate(
            systems=systems,
            dataset=examples,
            evaluators=[NeedleEvaluator()],
            metrics=[
                CompressionRatio(),
                MeanScore(score_field="answer_recall"),
                MeanNIAH(),
                EffectiveRatio(),
                CostOfPass(threshold=0.7, score_field="answer_recall"),
            ],
            text_fields=["context"],
        )

        print(f"\n{'=' * 80}")
        print(f"  DATASET: {ds_name} ({len(examples)} examples)")
        print(f"{'=' * 80}")
        md = to_markdown(result)
        print(md)
        print_cost_impact(result)

        all_md_parts.append(f"## {ds_name}\n\n{md}")

    # Save combined report
    if all_md_parts:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        full_md = "# Kompact — Real Dataset Benchmark Report\n\n" + "\n\n".join(all_md_parts)
        md_path = REPORTS_DIR / "dataset_eval_report.md"
        md_path.write_text(full_md)
        print(f"\nMarkdown report saved to: {md_path}")


if __name__ == "__main__":
    main()
