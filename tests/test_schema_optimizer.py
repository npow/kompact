"""Tests for schema optimizer transform."""

from kompact.config import SchemaOptimizerConfig
from kompact.transforms.schema_optimizer import transform
from kompact.types import (
    ContentBlock,
    ContentType,
    Message,
    Provider,
    Request,
    Role,
    ToolDefinition,
)


def _make_tool(name: str, description: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        input_schema={"type": "object", "properties": {"arg": {"type": "string"}}},
    )


def test_reduces_tools_to_max():
    tools = [_make_tool(f"tool_{i}", f"Tool number {i} for testing") for i in range(20)]
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text="Please read the file at /foo/bar.py"),
        ]),
    ]
    request = Request(
        provider=Provider.ANTHROPIC,
        messages=messages,
        tools=tools,
        model="claude-sonnet-4-5-20250929",
    )
    config = SchemaOptimizerConfig(enabled=True, max_tools=5)
    result = transform(request, config)

    assert len(request.tools) <= 10  # max_tools + recently used
    assert result.tokens_saved > 0
    assert result.details["original_count"] == 20


def test_keeps_relevant_tools():
    tools = [
        _make_tool("read_file", "Read a file from the filesystem"),
        _make_tool("write_file", "Write content to a file"),
        _make_tool("search_code", "Search for code patterns"),
        _make_tool("deploy_service", "Deploy a microservice"),
        _make_tool("send_email", "Send an email notification"),
    ]
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text="Read the file and search for patterns"),
        ]),
    ]
    request = Request(
        provider=Provider.ANTHROPIC,
        messages=messages,
        tools=tools,
        model="claude-sonnet-4-5-20250929",
    )
    config = SchemaOptimizerConfig(enabled=True, max_tools=3)
    transform(request, config)

    tool_names = {t.name for t in request.tools}
    assert "read_file" in tool_names
    assert "search_code" in tool_names


def test_no_change_when_under_limit():
    tools = [_make_tool(f"tool_{i}", f"Tool {i}") for i in range(3)]
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text="Hello"),
        ]),
    ]
    request = Request(
        provider=Provider.ANTHROPIC,
        messages=messages,
        tools=tools,
        model="claude-sonnet-4-5-20250929",
    )
    config = SchemaOptimizerConfig(enabled=True, max_tools=10)
    result = transform(request, config)

    assert len(request.tools) == 3
    assert result.tokens_saved == 0


def test_keeps_recently_used_tools():
    tools = [
        _make_tool("read_file", "Read a file"),
        _make_tool("exec_cmd", "Execute a command"),
        _make_tool("deploy", "Deploy service"),
    ]
    messages = [
        Message(role=Role.ASSISTANT, content=[
            ContentBlock(
                type=ContentType.TOOL_USE,
                tool_name="exec_cmd",
                tool_use_id="t1",
                tool_input={"cmd": "ls"},
            ),
        ]),
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text="Now read the file"),
        ]),
    ]
    request = Request(
        provider=Provider.ANTHROPIC,
        messages=messages,
        tools=tools,
        model="claude-sonnet-4-5-20250929",
    )
    config = SchemaOptimizerConfig(enabled=True, max_tools=1)
    transform(request, config)

    tool_names = {t.name for t in request.tools}
    # exec_cmd should be kept because it was recently used
    assert "exec_cmd" in tool_names
