"""Message parser for Anthropic and OpenAI formats.

Converts provider-specific request bodies to internal types and back.
"""

from __future__ import annotations

from typing import Any

from kompact.types import (
    ContentBlock,
    ContentType,
    Message,
    Provider,
    Request,
    Role,
    ToolDefinition,
)


def parse_request(body: dict[str, Any], provider: Provider) -> Request:
    """Parse a raw API request body into internal types."""
    if provider == Provider.ANTHROPIC:
        return _parse_anthropic(body)
    elif provider == Provider.OPENAI:
        return _parse_openai(body)
    raise ValueError(f"Unknown provider: {provider}")


def serialize_request(request: Request) -> dict[str, Any]:
    """Serialize internal types back to provider-specific format."""
    if request.provider == Provider.ANTHROPIC:
        return _serialize_anthropic(request)
    elif request.provider == Provider.OPENAI:
        return _serialize_openai(request)
    raise ValueError(f"Unknown provider: {request.provider}")


# --- Anthropic ---


def _parse_anthropic(body: dict[str, Any]) -> Request:
    messages = []
    for msg in body.get("messages", []):
        messages.append(_parse_anthropic_message(msg))

    tools = []
    for tool in body.get("tools", []):
        tools.append(ToolDefinition(
            name=tool.get("name", ""),
            description=tool.get("description", ""),
            input_schema=tool.get("input_schema", {}),
            raw=tool,
        ))

    system = ""
    sys_field = body.get("system", "")
    if isinstance(sys_field, str):
        system = sys_field
    elif isinstance(sys_field, list):
        system = "\n".join(
            b.get("text", "") for b in sys_field if isinstance(b, dict)
        )

    extra = {k: v for k, v in body.items()
             if k not in ("messages", "tools", "system", "model")}

    return Request(
        provider=Provider.ANTHROPIC,
        messages=messages,
        tools=tools,
        system=system,
        model=body.get("model", ""),
        extra=extra,
        raw_body=body,
    )


def _parse_anthropic_message(msg: dict[str, Any]) -> Message:
    role = Role(msg.get("role", "user"))
    content_raw = msg.get("content", "")

    blocks = []
    if isinstance(content_raw, str):
        blocks.append(ContentBlock(type=ContentType.TEXT, text=content_raw))
    elif isinstance(content_raw, list):
        for block in content_raw:
            if block.get("type") == "text":
                blocks.append(ContentBlock(type=ContentType.TEXT, text=block.get("text", "")))
            elif block.get("type") == "tool_use":
                blocks.append(ContentBlock(
                    type=ContentType.TOOL_USE,
                    tool_use_id=block.get("id", ""),
                    tool_name=block.get("name", ""),
                    tool_input=block.get("input", {}),
                ))
            elif block.get("type") == "tool_result":
                content_text = ""
                content_field = block.get("content", "")
                if isinstance(content_field, str):
                    content_text = content_field
                elif isinstance(content_field, list):
                    content_text = "\n".join(
                        b.get("text", "") for b in content_field
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                blocks.append(ContentBlock(
                    type=ContentType.TOOL_RESULT,
                    text=content_text,
                    tool_use_id=block.get("tool_use_id", ""),
                ))

    return Message(role=role, content=blocks)


def _serialize_anthropic(request: Request) -> dict[str, Any]:
    body: dict[str, Any] = {}

    if request.model:
        body["model"] = request.model
    if request.system:
        body["system"] = request.system

    messages = []
    for msg in request.messages:
        messages.append(_serialize_anthropic_message(msg))
    body["messages"] = messages

    if request.tools:
        body["tools"] = [_serialize_anthropic_tool(t) for t in request.tools]

    body.update(request.extra)
    return body


def _serialize_anthropic_message(msg: Message) -> dict[str, Any]:
    content = []
    for block in msg.content:
        if block.type == ContentType.TEXT:
            content.append({"type": "text", "text": block.text})
        elif block.type == ContentType.TOOL_USE:
            content.append({
                "type": "tool_use",
                "id": block.tool_use_id,
                "name": block.tool_name,
                "input": block.tool_input,
            })
        elif block.type == ContentType.TOOL_RESULT:
            content.append({
                "type": "tool_result",
                "tool_use_id": block.tool_use_id,
                "content": block.text,
            })

    return {"role": msg.role.value, "content": content}


def _serialize_anthropic_tool(tool: ToolDefinition) -> dict[str, Any]:
    if tool.raw:
        return tool.raw
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }


# --- OpenAI ---


def _parse_openai(body: dict[str, Any]) -> Request:
    messages = []
    for msg in body.get("messages", []):
        messages.append(_parse_openai_message(msg))

    tools = []
    for tool in body.get("tools", []):
        func = tool.get("function", {})
        tools.append(ToolDefinition(
            name=func.get("name", ""),
            description=func.get("description", ""),
            input_schema=func.get("parameters", {}),
            raw=tool,
        ))

    system = ""
    for msg in messages:
        if msg.role == Role.SYSTEM:
            system = msg.text
            break

    extra = {k: v for k, v in body.items()
             if k not in ("messages", "tools", "model")}

    return Request(
        provider=Provider.OPENAI,
        messages=messages,
        tools=tools,
        system=system,
        model=body.get("model", ""),
        extra=extra,
        raw_body=body,
    )


def _parse_openai_message(msg: dict[str, Any]) -> Message:
    role_str = msg.get("role", "user")
    role = Role(role_str) if role_str in Role.__members__.values() else Role.USER

    blocks = []
    content = msg.get("content", "")
    if isinstance(content, str) and content:
        blocks.append(ContentBlock(type=ContentType.TEXT, text=content))
    elif isinstance(content, list):
        for part in content:
            if part.get("type") == "text":
                blocks.append(ContentBlock(type=ContentType.TEXT, text=part.get("text", "")))

    # OpenAI tool calls are in the message itself
    for tc in msg.get("tool_calls", []):
        func = tc.get("function", {})
        import json
        try:
            args = json.loads(func.get("arguments", "{}"))
        except (json.JSONDecodeError, TypeError):
            args = {}
        blocks.append(ContentBlock(
            type=ContentType.TOOL_USE,
            tool_use_id=tc.get("id", ""),
            tool_name=func.get("name", ""),
            tool_input=args,
        ))

    # Tool role messages
    if role_str == "tool":
        tool_call_id = msg.get("tool_call_id", "")
        text = content if isinstance(content, str) else ""
        blocks = [ContentBlock(
            type=ContentType.TOOL_RESULT,
            text=text,
            tool_use_id=tool_call_id,
        )]

    return Message(role=role, content=blocks)


def _serialize_openai(request: Request) -> dict[str, Any]:
    body: dict[str, Any] = {}

    if request.model:
        body["model"] = request.model

    messages = []
    for msg in request.messages:
        messages.append(_serialize_openai_message(msg))
    body["messages"] = messages

    if request.tools:
        body["tools"] = [_serialize_openai_tool(t) for t in request.tools]

    body.update(request.extra)
    return body


def _serialize_openai_message(msg: Message) -> dict[str, Any]:
    import json

    result: dict[str, Any] = {"role": msg.role.value}

    tool_calls = []
    text_parts = []
    tool_result = None

    for block in msg.content:
        if block.type == ContentType.TEXT:
            text_parts.append(block.text)
        elif block.type == ContentType.TOOL_USE:
            tool_calls.append({
                "id": block.tool_use_id,
                "type": "function",
                "function": {
                    "name": block.tool_name,
                    "arguments": json.dumps(block.tool_input),
                },
            })
        elif block.type == ContentType.TOOL_RESULT:
            tool_result = block

    if tool_result:
        result["role"] = "tool"
        result["tool_call_id"] = tool_result.tool_use_id
        result["content"] = tool_result.text
    else:
        result["content"] = "\n".join(text_parts) if text_parts else ""
        if tool_calls:
            result["tool_calls"] = tool_calls

    return result


def _serialize_openai_tool(tool: ToolDefinition) -> dict[str, Any]:
    if tool.raw:
        return tool.raw
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }
