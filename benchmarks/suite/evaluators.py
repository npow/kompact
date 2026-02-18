"""Evaluators for context-bench integration.

NeedleEvaluator: scores each (original, processed) pair for needle preservation.
"""

from __future__ import annotations

from typing import Any

from .metrics import answer_recall


class NeedleEvaluator:
    """Score whether answer/needle survives in compressed context."""

    @property
    def name(self) -> str:
        return "needle"

    def score(
        self, original: dict[str, Any], processed: dict[str, Any]
    ) -> dict[str, float]:
        answer = original.get("answer", "")
        context = processed.get("context", "")

        # NIAH: binary — did the answer substring survive?
        if not answer:
            niah = 1.0
        else:
            niah = 1.0 if answer.lower() in context.lower() else 0.0

        # Answer recall: substring check + token recall fallback
        recall = answer_recall(answer, context)

        return {"niah": niah, "answer_recall": recall}
