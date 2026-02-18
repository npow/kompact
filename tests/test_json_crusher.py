"""Tests for JSON crusher transform."""

import json

from kompact.config import JsonCrusherConfig
from kompact.transforms.json_crusher import crush_array, transform
from kompact.types import ContentBlock, ContentType, Message, Role


def test_factors_out_constants():
    data = [
        {"status": "active", "role": "member", "name": "Alice", "id": 1},
        {"status": "active", "role": "member", "name": "Bob", "id": 2},
        {"status": "active", "role": "member", "name": "Charlie", "id": 3},
    ]
    result = crush_array(data, JsonCrusherConfig())
    assert result is not None
    assert "[CONSTANTS:" in result
    assert "status=active" in result
    assert "role=member" in result
    # Variable fields should still be in data
    assert "Alice" in result
    assert "Bob" in result


def test_preserves_anomalies():
    # Need enough items (>=5) and >90% with same value for anomaly detection
    data = [
        {"status": "active", "name": "Alice"},
        {"status": "active", "name": "Bob"},
        {"status": "active", "name": "Charlie"},
        {"status": "active", "name": "Dave"},
        {"status": "active", "name": "Eve"},
        {"status": "active", "name": "Frank"},
        {"status": "active", "name": "Grace"},
        {"status": "active", "name": "Heidi"},
        {"status": "active", "name": "Ivan"},
        {"status": "active", "name": "Judy"},
        {"status": "BANNED", "name": "Mallory"},  # Anomaly — 1 out of 11 = ~9%
    ]
    result = crush_array(data, JsonCrusherConfig())
    assert result is not None
    assert "!ANOMALY:" in result
    assert "Mallory" in result


def test_no_optimization_returns_none():
    data = [
        {"a": 1, "b": 2},
        {"a": 3, "b": 4},
        {"a": 5, "b": 6},
    ]
    # All fields are unique, no constants to factor out
    result = crush_array(data, JsonCrusherConfig())
    assert result is None


def test_transform_on_messages():
    data = [
        {"type": "file", "lang": "python", "path": "/a.py"},
        {"type": "file", "lang": "python", "path": "/b.py"},
        {"type": "file", "lang": "python", "path": "/c.py"},
    ]
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(
                type=ContentType.TOOL_RESULT,
                text=json.dumps(data),
                tool_use_id="t1",
            ),
        ]),
    ]
    result = transform(messages)
    assert result.tokens_saved > 0
    assert "[CONSTANTS:" in result.messages[0].content[0].text


def test_user_messages_not_modified():
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text="Hello world"),
        ]),
    ]
    result = transform(messages)
    assert result.messages[0].content[0].text == "Hello world"
    assert result.tokens_saved == 0


def test_min_array_length():
    data = [{"x": 1, "y": "same"}, {"x": 2, "y": "same"}]
    config = JsonCrusherConfig(min_array_length=5)
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(
                type=ContentType.TOOL_RESULT,
                text=json.dumps(data),
                tool_use_id="t1",
            ),
        ]),
    ]
    result = transform(messages, config)
    # Below threshold, no crushing
    assert result.tokens_saved == 0
