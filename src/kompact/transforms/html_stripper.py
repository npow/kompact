"""HTML/nav stripper transform.

Strips navigation chrome from WebFetch tool results — nav bars, sidebars,
link-list menus, and footers — keeping only body content.

Two passes:
1. Raw HTML: strip tags and decode entities
2. Markdown-with-nav: remove link-list sections heuristically

Verified on real WebFetch output: Wikipedia pages carry ~88% nav overhead
(17,847 chars markdown total, 2,156 chars body content).
"""

from __future__ import annotations

import html
import re

from kompact.config import HtmlStripperConfig
from kompact.types import ContentBlock, ContentType, Message, TransformResult

# Matches a line that is entirely (or nearly so) a markdown link or link list item
_MD_LINK_LINE = re.compile(r"^\s*[\*\-]?\s*\[([^\]]*)\]\([^\)]*\)[\"']?\s*$")

# Raw HTML detection: has block-level tags or DOCTYPE
_HTML_TAG = re.compile(r"<(/?\w[\w\-]*)(\s[^>]*)?>", re.IGNORECASE)
_HTML_SIGNAL = re.compile(
    r"(?:<!DOCTYPE|<html|<head|<body|<div|<nav|<header|<footer|<script|<style)",
    re.IGNORECASE,
)

# Known nav/chrome phrases — lines consisting only of these are dropped
_NAV_PHRASES = frozenset({
    "jump to content", "move to sidebar", "hide", "main menu",
    "personal tools", "navigation", "contribute", "appearance",
    "view history", "talk", "search", "donate",
    "create account", "log in", "contents", "move to sidebar hide",
})

# Footer section headings that mark end of article body
_FOOTER_HEADINGS = frozenset({
    "references", "see also", "external links", "further reading",
    "notes", "bibliography", "citations", "footnotes", "sources",
})


def transform(
    messages: list[Message],
    config: HtmlStripperConfig | None = None,
) -> TransformResult:
    """Strip nav chrome from HTML/markdown tool results."""
    if config is None:
        config = HtmlStripperConfig()

    if not config.enabled:
        return TransformResult(
            messages=messages,
            tokens_saved=0,
            transform_name="html_stripper",
        )

    tokens_saved = 0
    new_messages = []

    for msg in messages:
        new_blocks = []
        for block in msg.content:
            if (
                block.type in (ContentType.TOOL_RESULT, ContentType.TEXT)
                and block.text
                and len(block.text) >= config.min_chars
            ):
                new_text, saved = _strip(block.text, config)
                tokens_saved += saved
                new_blocks.append(ContentBlock(
                    type=block.type,
                    text=new_text,
                    tool_use_id=block.tool_use_id,
                    tool_name=block.tool_name,
                    tool_input=block.tool_input,
                    is_compressed=saved > 0 or block.is_compressed,
                    original_tokens=block.original_tokens,
                ))
            else:
                new_blocks.append(block)
        new_messages.append(Message(role=msg.role, content=new_blocks))

    return TransformResult(
        messages=new_messages,
        tokens_saved=tokens_saved,
        transform_name="html_stripper",
    )


def _strip(text: str, config: HtmlStripperConfig) -> tuple[str, int]:
    """Strip nav chrome. Returns (cleaned_text, tokens_saved)."""
    if _is_raw_html(text):
        result = _strip_html_tags(text)
    else:
        result = _strip_markdown_nav(text, config)

    saved = max(0, len(text) // 4 - len(result) // 4)
    return result, saved


def _is_raw_html(text: str) -> bool:
    """True if text contains raw HTML block-level tags."""
    return bool(_HTML_SIGNAL.search(text[:2000]))


def _strip_html_tags(text: str) -> str:
    """Strip HTML tags and decode entities from raw HTML."""
    # Remove <script> and <style> blocks entirely
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.IGNORECASE)

    # Convert block elements to newlines before stripping
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|li|h[1-6]|tr|td|th)>", "\n", text, flags=re.IGNORECASE)

    # Strip remaining tags
    text = _HTML_TAG.sub("", text)

    # Decode entities
    text = html.unescape(text)

    # Collapse excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


def _strip_markdown_nav(text: str, config: HtmlStripperConfig) -> str:
    """Remove nav sections from markdown-converted WebFetch output."""
    chunks = _split_chunks(text)
    kept: list[str] = []
    in_footer = False

    for chunk in chunks:
        if in_footer:
            break

        lines = chunk.split("\n")
        stripped_lines = [l.strip() for l in lines]
        non_empty = [l for l in stripped_lines if l]

        if not non_empty:
            continue

        # Detect footer headings — stop including content after these
        if config.strip_footer_sections and len(non_empty) == 1:
            heading_text = non_empty[0].lstrip("#").strip().lower()
            if heading_text in _FOOTER_HEADINGS:
                in_footer = True
                break

        # Drop pure nav-phrase chunks
        if _is_nav_phrase_chunk(non_empty):
            continue

        # Drop high link-density chunks (nav lists)
        if _link_density(non_empty) >= config.nav_link_ratio:
            continue

        kept.append(chunk)

    result = "\n\n".join(kept)
    return re.sub(r"\n{3,}", "\n\n", result).strip()


def _split_chunks(text: str) -> list[str]:
    """Split text into chunks on blank lines."""
    return re.split(r"\n{2,}", text)


def _is_nav_phrase_chunk(non_empty_lines: list[str]) -> bool:
    """True if all non-empty lines in this chunk are known nav phrases."""
    if not non_empty_lines:
        return False
    return all(l.lower() in _NAV_PHRASES for l in non_empty_lines)


def _link_density(non_empty_lines: list[str]) -> float:
    """Fraction of lines that are pure markdown link items."""
    if not non_empty_lines:
        return 0.0
    link_count = sum(1 for l in non_empty_lines if _MD_LINK_LINE.match(l))
    return link_count / len(non_empty_lines)
