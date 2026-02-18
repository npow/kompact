"""Tests for cache aligner transform."""

from kompact.config import CacheAlignerConfig
from kompact.transforms.cache_aligner import transform
from kompact.types import ContentBlock, ContentType, Message, Role


def test_normalizes_uuids():
    messages = [
        Message(role=Role.SYSTEM, content=[
            ContentBlock(
                type=ContentType.TEXT,
                text="Session: 550e8400-e29b-41d4-a716-446655440000. User ID: abc.",
            ),
        ]),
    ]
    result = transform(messages, CacheAlignerConfig())
    text = result.messages[0].content[0].text
    assert "550e8400-e29b-41d4-a716-446655440000" not in text
    assert "{UUID_0}" in text
    assert result.details["dynamic_count"] >= 1


def test_normalizes_timestamps():
    messages = [
        Message(role=Role.SYSTEM, content=[
            ContentBlock(
                type=ContentType.TEXT,
                text="Request at 2024-01-15T10:30:00Z from server.",
            ),
        ]),
    ]
    result = transform(messages, CacheAlignerConfig())
    text = result.messages[0].content[0].text
    assert "2024-01-15T10:30:00Z" not in text
    assert "{TS_" in text


def test_normalizes_user_paths():
    messages = [
        Message(role=Role.SYSTEM, content=[
            ContentBlock(
                type=ContentType.TEXT,
                text="Working directory: /Users/npow/code/myproject",
            ),
        ]),
    ]
    result = transform(messages, CacheAlignerConfig())
    text = result.messages[0].content[0].text
    assert "/Users/npow/code/myproject" not in text
    assert "{PATH_" in text


def test_does_not_normalize_non_user_paths():
    messages = [
        Message(role=Role.SYSTEM, content=[
            ContentBlock(
                type=ContentType.TEXT,
                text="Config at /etc/nginx/nginx.conf",
            ),
        ]),
    ]
    result = transform(messages, CacheAlignerConfig())
    text = result.messages[0].content[0].text
    # Non-user paths should not be normalized
    assert "/etc/nginx/nginx.conf" in text


def test_does_not_modify_non_system_messages():
    messages = [
        Message(role=Role.SYSTEM, content=[
            ContentBlock(type=ContentType.TEXT, text="UUID: 550e8400-e29b-41d4-a716-446655440000"),
        ]),
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text="Help me"),
        ]),
        Message(role=Role.ASSISTANT, content=[
            ContentBlock(
                type=ContentType.TEXT,
                text="Session: 660e8400-e29b-41d4-a716-446655440000",
            ),
        ]),
    ]
    result = transform(messages, CacheAlignerConfig())
    # System message should be normalized
    assert "{UUID_0}" in result.messages[0].content[0].text
    # User message preserved
    assert result.messages[1].content[0].text == "Help me"
    # Assistant message (not early) should not be modified
    assert "660e8400" in result.messages[2].content[0].text


def test_dynamic_values_captured():
    messages = [
        Message(role=Role.SYSTEM, content=[
            ContentBlock(
                type=ContentType.TEXT,
                text="ID: 550e8400-e29b-41d4-a716-446655440000, Time: 2024-06-01T12:00:00Z",
            ),
        ]),
    ]
    result = transform(messages, CacheAlignerConfig())
    dv = result.details["dynamic_values"]
    assert any("550e8400" in v for v in dv.values())
    assert any("2024-06-01" in v for v in dv.values())


def test_disabled_options():
    messages = [
        Message(role=Role.SYSTEM, content=[
            ContentBlock(
                type=ContentType.TEXT,
                text="UUID: 550e8400-e29b-41d4-a716-446655440000 at 2024-01-15T10:30:00Z",
            ),
        ]),
    ]
    config = CacheAlignerConfig(normalize_uuids=False)
    result = transform(messages, config)
    text = result.messages[0].content[0].text
    # UUID should still be there since normalization is off
    assert "550e8400" in text
    # Timestamp should be normalized
    assert "{TS_" in text
