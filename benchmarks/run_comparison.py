"""Synthetic scenario benchmark using context-bench.

Runs all compression approaches against 6 synthetic fixture scenarios
(search-heavy, code-heavy, log-heavy, schema-heavy, conversation-heavy, mixed-realistic).

Usage:
    uv run python benchmarks/run_comparison.py                    # Full suite
    uv run python benchmarks/run_comparison.py --scenario search  # Single scenario
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from context_bench import EvalResult, evaluate
from context_bench.metrics import CompressionRatio, CostOfPass, MeanScore
from context_bench.reporters import to_markdown

from suite.baselines import _extract_all_text
from suite.custom_metrics import EffectiveRatio, MeanNIAH
from suite.evaluators import NeedleEvaluator
from suite.fixture_generators import ALL_GENERATORS, ScenarioFixture
from suite.metrics import PRICING, estimate_monthly_cost
from suite.systems import ALL_SYSTEMS

REPORTS_DIR = Path(__file__).parent / "reports"


def fixture_to_example(fixture: ScenarioFixture) -> dict:
    """Convert a ScenarioFixture into a context-bench example dict."""
    context = _extract_all_text(fixture.messages)
    # Use the first needle as the answer (primary preservation target)
    answer = fixture.needles[0] if fixture.needles else ""
    return {
        "id": fixture.name,
        "context": context,
        "question": "",
        "answer": answer,
    }


def fixture_to_examples(fixture: ScenarioFixture) -> list[dict]:
    """Convert a fixture into one example per needle for richer scoring."""
    context = _extract_all_text(fixture.messages)
    examples = []
    for i, needle in enumerate(fixture.needles):
        examples.append({
            "id": f"{fixture.name}_needle_{i}",
            "context": context,
            "question": "",
            "answer": needle,
        })
    return examples


def print_cost_impact(combined: EvalResult) -> None:
    """Print monthly cost impact from combined results."""
    summary = combined.summary
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
    parser = argparse.ArgumentParser(description="Kompact Benchmark Comparison Suite")
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="Filter to scenarios containing this string (e.g., 'search', 'code', 'log')",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(REPORTS_DIR),
        help="Directory for report output",
    )
    args = parser.parse_args()

    print("Running Kompact benchmark comparison suite...\n")

    evaluators = [NeedleEvaluator()]
    metrics = [
        CompressionRatio(),
        MeanScore(score_field="answer_recall"),
        MeanNIAH(),
        EffectiveRatio(),
        CostOfPass(threshold=0.7, score_field="answer_recall"),
    ]

    all_md_parts: list[str] = []
    combined_results: list[EvalResult] = []

    for gen in ALL_GENERATORS:
        fixture = gen()
        if args.scenario and args.scenario not in fixture.name:
            continue

        print(f"--- {fixture.name} ---")
        print(f"    {fixture.description}\n")

        # Convert fixture into per-needle examples
        examples = fixture_to_examples(fixture)

        result = evaluate(
            systems=ALL_SYSTEMS,
            dataset=examples,
            evaluators=evaluators,
            metrics=metrics,
            text_fields=["context"],
        )

        md = to_markdown(result)
        print(md)
        print()

        all_md_parts.append(f"### {fixture.name}\n\n{fixture.description}\n\n{md}")
        combined_results.append(result)

    # Combined run across all scenarios for overall summary
    if combined_results:
        all_examples = []
        for gen in ALL_GENERATORS:
            fixture = gen()
            if args.scenario and args.scenario not in fixture.name:
                continue
            all_examples.extend(fixture_to_examples(fixture))

        combined = evaluate(
            systems=ALL_SYSTEMS,
            dataset=all_examples,
            evaluators=evaluators,
            metrics=metrics,
            text_fields=["context"],
            progress=False,
        )

        print("=" * 80)
        print("  OVERALL COMPARISON")
        print("=" * 80)
        overall_md = to_markdown(combined)
        print(overall_md)
        print_cost_impact(combined)

        # Save report
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        full_md = (
            "# Kompact Benchmark Comparison Report\n\n"
            "## Results by Scenario\n\n"
            + "\n\n".join(all_md_parts)
            + "\n\n## Overall Comparison\n\n"
            + overall_md
        )
        md_path = output_dir / "comparison_report.md"
        md_path.write_text(full_md)
        print(f"\nMarkdown report saved to: {md_path}")


if __name__ == "__main__":
    main()
