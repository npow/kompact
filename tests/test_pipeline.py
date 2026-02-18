"""Tests for the transform pipeline."""

import json

from kompact.config import KompactConfig
from kompact.transforms.pipeline import run
from kompact.types import (
    ContentBlock,
    ContentType,
    Message,
    Provider,
    Request,
    Role,
    ToolDefinition,
)


def test_pipeline_runs_all_transforms():
    """Pipeline should run enabled transforms and accumulate savings."""
    data = json.dumps([
        {"id": i, "status": "active", "name": f"Item {i}"}
        for i in range(10)
    ])
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TOOL_RESULT, text=data, tool_use_id="t1"),
        ]),
    ]
    request = Request(
        provider=Provider.ANTHROPIC,
        messages=messages,
        model="claude-sonnet-4-5-20250929",
    )
    config = KompactConfig()
    result = run(request, config)

    assert result.total_tokens_saved >= 0
    assert len(result.transform_results) > 0
    # Should have run TOON at minimum
    transform_names = {r.transform_name for r in result.transform_results}
    assert "toon" in transform_names


def test_pipeline_respects_disabled_transforms():
    data = json.dumps([
        {"id": i, "name": f"Item {i}"}
        for i in range(5)
    ])
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TOOL_RESULT, text=data, tool_use_id="t1"),
        ]),
    ]
    request = Request(
        provider=Provider.ANTHROPIC,
        messages=messages,
        model="claude-sonnet-4-5-20250929",
    )
    config = KompactConfig()
    config.toon.enabled = False
    result = run(request, config)

    transform_names = {r.transform_name for r in result.transform_results}
    assert "toon" not in transform_names


def test_pipeline_preserves_user_messages():
    """Golden rule: pipeline must never modify user text content."""
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text="Please help me with this task"),
        ]),
        Message(role=Role.ASSISTANT, content=[
            ContentBlock(type=ContentType.TEXT, text="Sure, let me look."),
        ]),
    ]
    request = Request(
        provider=Provider.ANTHROPIC,
        messages=messages,
        model="claude-sonnet-4-5-20250929",
    )
    config = KompactConfig()
    result = run(request, config)

    assert result.request.messages[0].content[0].text == "Please help me with this task"


def test_pipeline_with_tools():
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text="Read the file"),
        ]),
    ]
    tools = [
        ToolDefinition(name="read_file", description="Read a file", input_schema={}),
    ]
    request = Request(
        provider=Provider.ANTHROPIC,
        messages=messages,
        tools=tools,
        model="claude-sonnet-4-5-20250929",
    )
    config = KompactConfig()
    config.schema_optimizer.enabled = True
    config.schema_optimizer.max_tools = 10
    result = run(request, config)

    # Should still have the tool (under limit)
    assert len(result.request.tools) == 1


def test_pipeline_result_has_compression_ratio():
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text="Hello"),
        ]),
    ]
    request = Request(
        provider=Provider.ANTHROPIC,
        messages=messages,
        model="claude-sonnet-4-5-20250929",
    )
    result = run(request, KompactConfig())
    # Should return valid ratio even with no savings
    assert result.compression_ratio >= 0.0
