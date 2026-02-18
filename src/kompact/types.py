"""Core type definitions for Kompact.

All transforms operate on these types. Provider-specific formats are converted
to/from these types by the parser module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Role(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ContentType(Enum):
    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    IMAGE = "image"


class Provider(Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


@dataclass
class ContentBlock:
    """A single content block within a message."""

    type: ContentType
    text: str = ""
    tool_use_id: str = ""
    tool_name: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)
    # For tracking which content has been compressed
    is_compressed: bool = False
    original_tokens: int = 0


@dataclass
class ToolDefinition:
    """A tool/function definition sent with the request."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    # Original provider-specific format preserved for serialization
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    """A single message in the conversation."""

    role: Role
    content: list[ContentBlock] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Get concatenated text content."""
        return "\n".join(b.text for b in self.content if b.text)

    @property
    def is_tool_result(self) -> bool:
        return any(b.type == ContentType.TOOL_RESULT for b in self.content)


@dataclass
class TransformResult:
    """Result of applying a transform to messages.

    Every transform must return this, tracking tokens saved.
    """

    messages: list[Message]
    tokens_saved: int = 0
    transform_name: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Request:
    """A parsed LLM API request, provider-agnostic."""

    provider: Provider
    messages: list[Message]
    tools: list[ToolDefinition] = field(default_factory=list)
    system: str = ""
    model: str = ""
    # Preserve all other fields from the original request
    extra: dict[str, Any] = field(default_factory=dict)
    # Raw request body for fields we don't parse
    raw_body: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Result of running the full transform pipeline."""

    request: Request
    total_tokens_saved: int = 0
    transform_results: list[TransformResult] = field(default_factory=list)

    @property
    def compression_ratio(self) -> float:
        """Ratio of tokens saved to original tokens (0 = no savings, 1 = all removed)."""
        total_original = sum(
            r.details.get("tokens_before", 0) for r in self.transform_results
        )
        if total_original == 0:
            return 0.0
        return self.total_tokens_saved / total_original
