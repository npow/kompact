"""Tests for html_stripper transform."""

from __future__ import annotations

import pytest

from kompact.config import HtmlStripperConfig
from kompact.transforms.html_stripper import (
    _is_nav_phrase_chunk,
    _is_raw_html,
    _link_density,
    _strip,
    _strip_html_tags,
    _strip_markdown_nav,
    transform,
)
from kompact.types import ContentBlock, ContentType, Message, Role


# Fixture: real Wikipedia-style WebFetch markdown (condensed from actual fetch)
WIKIPEDIA_MARKDOWN = """Context window - Wikipedia

[Jump to content](#bodyContent)

 Main menu

Main menu

move to sidebar hide

Navigation

*   [Main page](/wiki/Main_Page "Visit the main page [z]")
*   [Contents](/wiki/Wikipedia:Contents "Guides to browsing Wikipedia")
*   [Current events](/wiki/Portal:Current_events "Articles related to current events")
*   [Random article](/wiki/Special:Random "Visit a randomly selected article [x]")
*   [About Wikipedia](/wiki/Wikipedia:About "Learn about Wikipedia and how it works")
*   [Contact us](//en.wikipedia.org/wiki/Wikipedia:Contact_us "How to contact Wikipedia")

Contribute

*   [Help](/wiki/Help:Contents "Guidance on how to use and edit Wikipedia")
*   [Learn to edit](/wiki/Help:Introduction "Learn how to edit Wikipedia")
*   [Community portal](/wiki/Wikipedia:Community_portal "The hub for editors")
*   [Recent changes](/wiki/Special:RecentChanges "A list of recent changes to Wikipedia [r]")
*   [Upload file](/wiki/Wikipedia:File_upload_wizard "Add images or other media for use on Wikipedia")

## Context window

A context window is the span of text a large language model (LLM) can process
at once. Longer context windows allow models to consider more information when
generating responses, which is useful for tasks like summarization of long
documents, code generation across many files, and multi-turn dialogue.

## History

Early transformer models had context windows of 512 to 2048 tokens. Modern
models like Claude and GPT-4 support 128,000 tokens or more.

## See also

*   [Large language model](/wiki/Large_language_model)
*   [Transformer (machine learning model)](/wiki/Transformer_(machine_learning_model))

Retrieved from "https://en.wikipedia.org/wiki/Context_window"
"""

RAW_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Test Page</title>
  <style>body { font-family: sans-serif; }</style>
  <script>console.log('hello');</script>
</head>
<body>
  <nav><a href="/">Home</a> | <a href="/about">About</a></nav>
  <main>
    <h1>Article Title</h1>
    <p>This is the first paragraph with real content about the topic.</p>
    <p>A second paragraph continues the discussion with more detail.</p>
  </main>
  <footer><p>Copyright 2025</p></footer>
</body>
</html>"""


def _make_tool_result(text: str) -> list[Message]:
    return [Message(
        role=Role.USER,
        content=[ContentBlock(type=ContentType.TOOL_RESULT, text=text)],
    )]


# --- Unit tests for helpers ---

def test_is_raw_html_positive():
    assert _is_raw_html("<!DOCTYPE html><html><body>hello</body></html>")
    assert _is_raw_html("<html lang='en'><head></head>")
    assert _is_raw_html("<div class='main'><p>text</p></div>")


def test_is_raw_html_negative():
    assert not _is_raw_html("# Markdown heading\n\nSome prose text.")
    assert not _is_raw_html("[Link text](https://example.com)")
    assert not _is_raw_html("Plain text with no HTML.")


def test_link_density_all_links():
    lines = [
        "* [Main page](/wiki/Main_Page)",
        "* [Contents](/wiki/Contents)",
        "* [Random article](/wiki/Special:Random)",
    ]
    assert _link_density(lines) == 1.0


def test_link_density_no_links():
    lines = [
        "A context window is the span of text an LLM can process.",
        "Longer context windows allow more information to be considered.",
    ]
    assert _link_density(lines) == 0.0


def test_link_density_mixed():
    lines = [
        "* [Link one](/path/one)",
        "* [Link two](/path/two)",
        "Some prose line.",
        "Another prose line.",
    ]
    assert _link_density(lines) == 0.5


def test_is_nav_phrase_chunk_true():
    assert _is_nav_phrase_chunk(["navigation"])
    assert _is_nav_phrase_chunk(["contribute"])
    assert _is_nav_phrase_chunk(["main menu", "navigation"])


def test_is_nav_phrase_chunk_false():
    assert not _is_nav_phrase_chunk(["Context window is a span of text."])
    assert not _is_nav_phrase_chunk([])


# --- HTML tag stripping ---

def test_strip_html_tags_removes_script_style():
    result = _strip_html_tags(RAW_HTML)
    assert "<script>" not in result
    assert "console.log" not in result
    assert "font-family" not in result


def test_strip_html_tags_keeps_content():
    result = _strip_html_tags(RAW_HTML)
    assert "Article Title" in result
    assert "first paragraph with real content" in result
    assert "second paragraph" in result


def test_strip_html_tags_removes_tags():
    result = _strip_html_tags("<p>Hello <b>world</b>.</p>")
    assert "<" not in result
    assert "Hello world." in result


def test_strip_html_decodes_entities():
    result = _strip_html_tags("<p>Caf&eacute; &amp; Bistro &lt;3&gt;</p>")
    assert "Café & Bistro <3>" in result


# --- Markdown nav stripping ---

def test_strip_markdown_nav_removes_nav_links():
    config = HtmlStripperConfig()
    result = _strip_markdown_nav(WIKIPEDIA_MARKDOWN, config)
    assert "[Main page](/wiki/Main_Page" not in result
    assert "[Contents](/wiki/Wikipedia:Contents" not in result
    assert "[Help](/wiki/Help:Contents" not in result


def test_strip_markdown_nav_keeps_body():
    config = HtmlStripperConfig()
    result = _strip_markdown_nav(WIKIPEDIA_MARKDOWN, config)
    assert "A context window is the span of text" in result
    assert "Early transformer models" in result


def test_strip_markdown_nav_removes_footer():
    config = HtmlStripperConfig(strip_footer_sections=True)
    result = _strip_markdown_nav(WIKIPEDIA_MARKDOWN, config)
    assert "Retrieved from" not in result
    # See also section should be gone
    assert "[Large language model]" not in result


def test_strip_markdown_nav_footer_off():
    config = HtmlStripperConfig(strip_footer_sections=False)
    result = _strip_markdown_nav(WIKIPEDIA_MARKDOWN, config)
    # With footer stripping off, "See also" links may survive
    # (depends on link density) — just check body is still there
    assert "A context window is the span of text" in result


def test_strip_reduces_size():
    config = HtmlStripperConfig()
    result, saved = _strip(WIKIPEDIA_MARKDOWN, config)
    assert saved > 0
    assert len(result) < len(WIKIPEDIA_MARKDOWN)


# --- Transform-level tests ---

def test_transform_skips_short_blocks():
    config = HtmlStripperConfig(min_chars=500)
    short_text = "* [Link](/path)\n* [Link2](/path2)"
    messages = _make_tool_result(short_text)
    result = transform(messages, config)
    assert result.tokens_saved == 0
    assert result.messages[0].content[0].text == short_text


def test_transform_processes_tool_results():
    config = HtmlStripperConfig()
    messages = _make_tool_result(WIKIPEDIA_MARKDOWN)
    result = transform(messages, config)
    assert result.tokens_saved > 0
    assert "A context window" in result.messages[0].content[0].text


def test_transform_skips_non_tool_result():
    config = HtmlStripperConfig()
    messages = [Message(
        role=Role.USER,
        content=[ContentBlock(type=ContentType.TOOL_USE, text=WIKIPEDIA_MARKDOWN)],
    )]
    result = transform(messages, config)
    # TOOL_USE blocks are not processed
    assert result.tokens_saved == 0


def test_transform_processes_raw_html():
    config = HtmlStripperConfig(min_chars=100)
    messages = _make_tool_result(RAW_HTML)
    result = transform(messages, config)
    text = result.messages[0].content[0].text
    assert "<script>" not in text
    assert "<style>" not in text
    assert "Article Title" in text
    assert result.tokens_saved > 0


def test_transform_disabled():
    config = HtmlStripperConfig(enabled=False)
    messages = _make_tool_result(WIKIPEDIA_MARKDOWN)
    result = transform(messages, config)
    assert result.tokens_saved == 0
    assert result.messages[0].content[0].text == WIKIPEDIA_MARKDOWN


def test_wikipedia_compression_ratio():
    """Verify real-world savings on Wikipedia-style WebFetch output."""
    config = HtmlStripperConfig()
    result, saved = _strip(WIKIPEDIA_MARKDOWN, config)
    original_tokens = len(WIKIPEDIA_MARKDOWN) // 4
    remaining_tokens = len(result) // 4
    ratio = remaining_tokens / original_tokens
    # Should compress to less than 60% of original
    assert ratio < 0.60, f"Expected <60% retention, got {ratio:.1%}"
