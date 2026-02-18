"""Kompact-specific metrics for context-bench integration.

MeanNIAH: average NIAH score across examples.
EffectiveRatio: retry-adjusted compression ratio.
"""

from __future__ import annotations

from dataclasses import dataclass

from context_bench.results import EvalRow


@dataclass
class MeanNIAH:
    """Average NIAH (needle-in-a-haystack) score across examples."""

    @property
    def name(self) -> str:
        return "mean_niah"

    def compute(self, rows: list[EvalRow]) -> dict[str, float]:
        if not rows:
            return {"mean_niah": 0.0}
        values = [r.scores.get("niah", 0.0) for r in rows]
        return {"mean_niah": sum(values) / len(values)}


@dataclass
class EffectiveRatio:
    """Retry-adjusted compression ratio.

    If NIAH == 1.0: effective_tokens = output_tokens (compression worked)
    If NIAH < 1.0: effective_tokens = output_tokens + input_tokens (wasted attempt + retry)

    effective_ratio = 1 - sum(effective_tokens) / sum(input_tokens)
    """

    @property
    def name(self) -> str:
        return "effective_ratio"

    def compute(self, rows: list[EvalRow]) -> dict[str, float]:
        if not rows:
            return {"effective_ratio": 0.0}

        total_input = 0
        total_effective = 0
        for r in rows:
            total_input += r.input_tokens
            if r.scores.get("niah", 0.0) >= 1.0:
                total_effective += r.output_tokens
            else:
                total_effective += r.output_tokens + r.input_tokens

        ratio = 1.0 - (total_effective / total_input) if total_input > 0 else 0.0
        return {"effective_ratio": ratio}
