"""Observation masker transform.

Replaces old tool outputs with compact placeholders, keeping only the most
recent N tool outputs in full. Based on JetBrains Mellum research showing
~50% cost reduction with minimal accuracy impact.

Old outputs are stored in the compression store for retrieval if needed.
"""

from __future__ import annotations

from kompact.config import ObservationMaskerConfig
from kompact.types import ContentBlock, ContentType, Message, TransformResult


def transform(
    messages: list[Message],
    config: ObservationMaskerConfig | None = None,
    store: object | None = None,
) -> TransformResult:
    """Mask old tool outputs, keeping the last N in full."""
    if config is None:
        config = ObservationMaskerConfig()

    # Find all tool result positions (message index, block index)
    tool_result_positions: list[tuple[int, int]] = []
    for msg_idx, msg in enumerate(messages):
        for block_idx, block in enumerate(msg.content):
            if block.type == ContentType.TOOL_RESULT:
                tool_result_positions.append((msg_idx, block_idx))

    # Determine which to mask (all except last N)
    if len(tool_result_positions) <= config.keep_last_n:
        return TransformResult(
            messages=messages,
            tokens_saved=0,
            transform_name="observation_masker",
        )

    positions_to_mask = set(
        (mi, bi) for mi, bi in tool_result_positions[: -config.keep_last_n]
    )

    tokens_saved = 0
    new_messages = []

    for msg_idx, msg in enumerate(messages):
        new_blocks = []
        for block_idx, block in enumerate(msg.content):
            if (msg_idx, block_idx) in positions_to_mask:
                original_len = len(block.text)
                original_tokens = original_len // 4

                # Build placeholder
                summary = _build_summary(block, config)

                # Store original if store is provided
                if store is not None and hasattr(store, "put"):
                    store.put(
                        key=block.tool_use_id or f"obs_{msg_idx}_{block_idx}",
                        content=block.text,
                        metadata={"tool_name": block.tool_name},
                    )

                new_block = ContentBlock(
                    type=block.type,
                    text=summary,
                    tool_use_id=block.tool_use_id,
                    tool_name=block.tool_name,
                    is_compressed=True,
                    original_tokens=original_tokens,
                )
                new_blocks.append(new_block)
                placeholder_tokens = len(summary) // 4
                tokens_saved += max(0, original_tokens - placeholder_tokens)
            else:
                new_blocks.append(block)
        new_messages.append(Message(role=msg.role, content=new_blocks))

    return TransformResult(
        messages=new_messages,
        tokens_saved=tokens_saved,
        transform_name="observation_masker",
        details={"masked_count": len(positions_to_mask)},
    )


def _build_summary(block: ContentBlock, config: ObservationMaskerConfig) -> str:
    """Build a placeholder summary for a masked tool output."""
    token_count = len(block.text) // 4
    parts = [f"[Output omitted — {token_count} tokens"]

    if config.include_summary and block.text:
        # Include first line as brief context
        first_line = block.text.split("\n", 1)[0][:100]
        if first_line:
            parts.append(f". Starts with: {first_line}")

    parts.append("]")
    return "".join(parts)
