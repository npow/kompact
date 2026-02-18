"""Tests for TOON (Token-Optimized Object Notation) transform."""

import json

from kompact.transforms.toon import convert_array_to_toon, transform
from kompact.types import ContentBlock, ContentType, Message, Role


def test_basic_array_conversion():
    data = [
        {"name": "Alice", "age": 30, "city": "NYC"},
        {"name": "Bob", "age": 25, "city": "LA"},
        {"name": "Charlie", "age": 35, "city": "Chicago"},
    ]
    result = convert_array_to_toon(data)
    assert result is not None
    lines = result.strip().split("\n")
    assert lines[0] == "[FIELDS: name, age, city]"
    assert lines[1] == "Alice | 30 | NYC"
    assert lines[2] == "Bob | 25 | LA"
    assert lines[3] == "Charlie | 35 | Chicago"


def test_single_field():
    data = [{"name": "Alice"}, {"name": "Bob"}]
    result = convert_array_to_toon(data)
    assert result is not None
    assert "[FIELDS: name]" in result
    assert "Alice" in result
    assert "Bob" in result


def test_missing_fields():
    data = [
        {"name": "Alice", "age": 30},
        {"name": "Bob"},
    ]
    result = convert_array_to_toon(data)
    assert result is not None
    lines = result.strip().split("\n")
    assert lines[0] == "[FIELDS: name, age]"
    assert lines[1] == "Alice | 30"
    assert lines[2].startswith("Bob |")


def test_nested_values():
    data = [
        {"name": "Alice", "tags": ["python", "rust"]},
        {"name": "Bob", "tags": ["go"]},
    ]
    result = convert_array_to_toon(data)
    assert result is not None
    assert '["python","rust"]' in result
    assert '["go"]' in result


def test_non_object_array_returns_none():
    assert convert_array_to_toon([1, 2, 3]) is None
    assert convert_array_to_toon(["a", "b"]) is None
    assert convert_array_to_toon([]) is None


def test_transform_on_messages():
    json_data = json.dumps([
        {"id": 1, "title": "First", "status": "open"},
        {"id": 2, "title": "Second", "status": "closed"},
        {"id": 3, "title": "Third", "status": "open"},
    ])
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TOOL_RESULT, text=json_data, tool_use_id="t1"),
        ]),
    ]

    result = transform(messages)
    assert result.tokens_saved > 0
    assert result.transform_name == "toon"
    assert "[FIELDS:" in result.messages[0].content[0].text


def test_user_messages_not_modified():
    """Golden rule: no transform may modify user text messages."""
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text="Hello, please help me"),
        ]),
    ]
    result = transform(messages)
    assert result.messages[0].content[0].text == "Hello, please help me"
    assert result.tokens_saved == 0


def test_min_array_length():
    json_data = json.dumps([{"name": "Alice"}])
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TOOL_RESULT, text=json_data, tool_use_id="t1"),
        ]),
    ]
    # Default min_array_length=2, single item should not be converted
    result = transform(messages)
    assert result.tokens_saved == 0


def test_custom_separator():
    data = [
        {"a": 1, "b": 2},
        {"a": 3, "b": 4},
    ]
    result = convert_array_to_toon(data, separator=" ; ")
    assert result is not None
    assert " ; " in result


def test_boolean_and_null_values():
    data = [
        {"name": "Alice", "active": True, "deleted": None},
        {"name": "Bob", "active": False, "deleted": None},
    ]
    result = convert_array_to_toon(data)
    assert result is not None
    assert "true" in result
    assert "false" in result


def test_savings_are_positive():
    """TOON should reduce tokens for typical JSON arrays."""
    large_array = [
        {"id": i, "name": f"User {i}", "email": f"user{i}@example.com", "role": "member"}
        for i in range(20)
    ]
    json_data = json.dumps(large_array)
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TOOL_RESULT, text=json_data, tool_use_id="t1"),
        ]),
    ]
    result = transform(messages)
    assert result.tokens_saved > 0
    # Verify compressed is shorter
    assert len(result.messages[0].content[0].text) < len(json_data)
