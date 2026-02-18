"""Benchmark: Measure compression ratios on realistic fixtures.

Usage:
    uv run python benchmarks/compression_ratio.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kompact.config import KompactConfig
from kompact.transforms import (
    json_crusher,
    log_compressor,
    toon,
)
from kompact.transforms.pipeline import run
from kompact.types import (
    ContentBlock,
    ContentType,
    Message,
    Provider,
    Request,
    Role,
)

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"
BENCH_FIXTURES_DIR = Path(__file__).parent / "fixtures"


def measure_toon(data: list[dict]) -> dict:
    """Measure TOON compression on a JSON array."""
    original = json.dumps(data, indent=2)
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TOOL_RESULT, text=original, tool_use_id="bench"),
        ]),
    ]
    result = toon.transform(messages)
    compressed = result.messages[0].content[0].text
    return {
        "original_chars": len(original),
        "compressed_chars": len(compressed),
        "ratio": len(compressed) / len(original) if original else 1.0,
        "tokens_saved": result.tokens_saved,
    }


def measure_json_crusher(data: list[dict]) -> dict:
    """Measure JSON crusher compression."""
    original = json.dumps(data, indent=2)
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TOOL_RESULT, text=original, tool_use_id="bench"),
        ]),
    ]
    result = json_crusher.transform(messages)
    compressed = result.messages[0].content[0].text
    return {
        "original_chars": len(original),
        "compressed_chars": len(compressed),
        "ratio": len(compressed) / len(original) if original else 1.0,
        "tokens_saved": result.tokens_saved,
    }


def measure_pipeline(text: str, content_type: ContentType = ContentType.TOOL_RESULT) -> dict:
    """Measure full pipeline compression."""
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=content_type, text=text, tool_use_id="bench"),
        ]),
    ]
    request = Request(
        provider=Provider.ANTHROPIC,
        messages=messages,
        model="benchmark",
    )
    config = KompactConfig()
    result = run(request, config)
    compressed = result.request.messages[0].content[0].text
    return {
        "original_chars": len(text),
        "compressed_chars": len(compressed),
        "ratio": len(compressed) / len(text) if text else 1.0,
        "tokens_saved": result.total_tokens_saved,
        "transforms": [
            {"name": r.transform_name, "saved": r.tokens_saved}
            for r in result.transform_results
        ],
    }


def main():
    print("=" * 60)
    print("Kompact Compression Benchmark")
    print("=" * 60)

    # Benchmark 1: API responses (JSON arrays)
    api_file = FIXTURES_DIR / "api_responses.json"
    if api_file.exists():
        data = json.loads(api_file.read_text())
        if isinstance(data, list):
            datasets = {"api_responses": data}
        else:
            datasets = data if isinstance(data, dict) else {"data": [data]}

        for name, arr in datasets.items():
            if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                print(f"\n--- {name} ({len(arr)} items) ---")
                toon_result = measure_toon(arr)
                print(f"  TOON:         {toon_result['ratio']:.2%} of original "
                      f"({toon_result['tokens_saved']} tokens saved)")
                crusher_result = measure_json_crusher(arr)
                print(f"  JSON Crusher: {crusher_result['ratio']:.2%} of original "
                      f"({crusher_result['tokens_saved']} tokens saved)")

    # Benchmark 2: Search results
    search_file = FIXTURES_DIR / "search_results.json"
    if search_file.exists():
        data = json.loads(search_file.read_text())
        items = data if isinstance(data, list) else data.get("results", [])
        if items:
            print(f"\n--- search_results ({len(items)} items) ---")
            toon_result = measure_toon(items)
            print(f"  TOON:         {toon_result['ratio']:.2%} of original "
                  f"({toon_result['tokens_saved']} tokens saved)")

    # Benchmark 3: Log output
    log_file = FIXTURES_DIR / "log_outputs.txt"
    if log_file.exists():
        log_text = log_file.read_text()
        print(f"\n--- log_outputs ({len(log_text)} chars) ---")
        result = measure_pipeline(log_text)
        print(f"  Pipeline:     {result['ratio']:.2%} of original "
              f"({result['tokens_saved']} tokens saved)")

    # Benchmark 4: Code file
    code_file = FIXTURES_DIR / "code_files.py"
    if code_file.exists():
        code_text = code_file.read_text()
        print(f"\n--- code_files ({len(code_text)} chars) ---")
        result = measure_pipeline(code_text)
        print(f"  Pipeline:     {result['ratio']:.2%} of original "
              f"({result['tokens_saved']} tokens saved)")

    # Synthetic benchmark: Large homogeneous array
    print("\n--- synthetic: 100-item user array ---")
    synthetic = [
        {"id": i, "name": f"User {i}", "email": f"user{i}@example.com",
         "role": "member", "status": "active", "created": "2024-01-01"}
        for i in range(100)
    ]
    toon_result = measure_toon(synthetic)
    print(f"  TOON:         {toon_result['ratio']:.2%} of original "
          f"({toon_result['tokens_saved']} tokens saved)")
    crusher_result = measure_json_crusher(synthetic)
    print(f"  JSON Crusher: {crusher_result['ratio']:.2%} of original "
          f"({crusher_result['tokens_saved']} tokens saved)")

    print("\n" + "=" * 60)
    print("Benchmark complete.")


if __name__ == "__main__":
    main()
