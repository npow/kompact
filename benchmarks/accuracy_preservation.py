"""Benchmark: NIAH (Needle In A Haystack) accuracy preservation.

Verifies that critical items survive compression through the pipeline.

Usage:
    uv run python benchmarks/accuracy_preservation.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kompact.config import KompactConfig
from kompact.transforms.pipeline import run
from kompact.types import (
    ContentBlock,
    ContentType,
    Message,
    Provider,
    Request,
    Role,
)


def niah_test(needle: str, haystack_items: int = 100) -> dict:
    """Insert a needle into a haystack and verify it survives compression."""
    # Build haystack: many similar items
    haystack = [
        {"id": i, "type": "result", "title": f"Regular item {i}",
         "description": f"This is a normal search result number {i}",
         "url": f"https://example.com/{i}", "score": 0.5}
        for i in range(haystack_items)
    ]

    # Insert needle at random position
    needle_pos = haystack_items // 3
    haystack.insert(needle_pos, {
        "id": 9999,
        "type": "CRITICAL",
        "title": needle,
        "description": f"IMPORTANT: {needle}",
        "url": "https://critical.example.com/needle",
        "score": 1.0,
    })

    json_text = json.dumps(haystack)

    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TOOL_RESULT, text=json_text, tool_use_id="search"),
        ]),
    ]

    request = Request(
        provider=Provider.ANTHROPIC,
        messages=messages,
        model="benchmark",
    )

    config = KompactConfig()
    result = run(request, config)

    compressed_text = result.request.messages[0].content[0].text

    return {
        "needle": needle,
        "found": needle in compressed_text,
        "haystack_items": haystack_items,
        "original_chars": len(json_text),
        "compressed_chars": len(compressed_text),
        "ratio": len(compressed_text) / len(json_text),
        "tokens_saved": result.total_tokens_saved,
    }


def main():
    print("=" * 60)
    print("NIAH (Needle In A Haystack) Accuracy Test")
    print("=" * 60)

    needles = [
        "The secret API key is sk-1234567890abcdef",
        "Deploy to production at 3pm PST",
        "Bug: users cannot login when password contains unicode",
        "Revenue increased 47% in Q3 2024",
        "CRITICAL: memory leak in worker process 7",
    ]

    total = 0
    found = 0

    for needle in needles:
        result = niah_test(needle, haystack_items=100)
        total += 1
        if result["found"]:
            found += 1
            status = "PASS"
        else:
            status = "FAIL"

        print(f"\n  [{status}] Needle: \"{needle[:50]}...\"")
        print(f"         Compression: {result['ratio']:.2%} "
              f"({result['tokens_saved']} tokens saved)")

    print(f"\n{'=' * 60}")
    print(f"Results: {found}/{total} needles preserved ({found/total:.0%})")

    if found == total:
        print("ALL CRITICAL ITEMS SURVIVED COMPRESSION")
    else:
        print("WARNING: Some critical items were lost!")
        sys.exit(1)


if __name__ == "__main__":
    main()
