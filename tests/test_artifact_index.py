"""Tests for artifact index and compression store tracking."""

from kompact.cache.store import ArtifactIndex, CompressionStore


def test_artifact_index_add_and_retrieve():
    idx = ArtifactIndex()
    idx.add(kind="tool_result", key="search_1", summary="Search results for Python", turn_id=3)
    idx.add(kind="file", key="/app/main.py", summary="Main application file", turn_id=5)

    assert len(idx.entries) == 2
    assert len(idx.get_by_kind("tool_result")) == 1
    assert len(idx.get_by_kind("file")) == 1


def test_artifact_index_to_text():
    idx = ArtifactIndex()
    idx.add(kind="tool_result", key="search_1", summary="Results", turn_id=1)
    text = idx.to_text()

    assert "[Artifact Index]" in text
    assert "tool_result:" in text
    assert "search_1" in text


def test_artifact_index_empty():
    idx = ArtifactIndex()
    assert idx.to_text() == ""
    assert idx.get_by_kind("anything") == []


def test_store_track_creates_artifact_entry():
    store = CompressionStore()
    store_key = store.track(
        kind="tool_result",
        key="search_1",
        content="Full search results content here...",
        turn_id=3,
    )

    # Content should be stored
    assert store.get(store_key) == "Full search results content here..."

    # Artifact index should have the entry
    assert len(store.artifact_index.entries) == 1
    entry = store.artifact_index.entries[0]
    assert entry.kind == "tool_result"
    assert entry.key == "search_1"
    assert entry.turn_id == 3
    assert entry.store_key == store_key


def test_store_track_multiple():
    store = CompressionStore()
    store.track(kind="tool_result", key="search_1", content="Results 1", turn_id=1)
    store.track(kind="file", key="/app/main.py", content="import os\n...", turn_id=2)
    store.track(kind="tool_result", key="search_2", content="Results 2", turn_id=3)

    assert len(store.artifact_index.entries) == 3
    assert len(store.artifact_index.get_by_kind("tool_result")) == 2
    assert len(store.artifact_index.get_by_kind("file")) == 1
