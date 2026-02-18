"""Compression store for CCR-style content retrieval.

Stores original content replaced by compression markers, allowing the LLM
to request full content back when needed.

Features:
- Statistical summary in markers (not just token count)
- Adaptive TTL based on access frequency
- In-memory with bounded size (LRU eviction)
- Artifact index tracking what was compressed (kind, key, summary, turn)
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ArtifactEntry:
    """A tracked artifact that was compressed/masked."""

    kind: str  # "tool_result", "file", "search", "log", "code"
    key: str  # identifier (tool name, file path, etc.)
    summary: str  # brief description of what was stored
    turn_id: int  # conversation turn where this appeared
    store_key: str = ""  # key in the compression store for retrieval


@dataclass
class ArtifactIndex:
    """Persistent index of compressed artifacts for re-fetching."""

    entries: list[ArtifactEntry] = field(default_factory=list)

    def add(
        self,
        kind: str,
        key: str,
        summary: str,
        turn_id: int,
        store_key: str = "",
    ) -> None:
        self.entries.append(ArtifactEntry(
            kind=kind, key=key, summary=summary, turn_id=turn_id, store_key=store_key,
        ))

    def get_by_kind(self, kind: str) -> list[ArtifactEntry]:
        return [e for e in self.entries if e.kind == kind]

    def to_text(self) -> str:
        """Render as a compact text block for inclusion in context."""
        if not self.entries:
            return ""
        lines = ["[Artifact Index]"]
        by_kind: dict[str, list[ArtifactEntry]] = {}
        for e in self.entries:
            by_kind.setdefault(e.kind, []).append(e)
        for kind, items in by_kind.items():
            lines.append(f"  {kind}:")
            for item in items:
                lines.append(f"    - {item.key}: {item.summary} (turn {item.turn_id})")
        return "\n".join(lines)


@dataclass
class StoreEntry:
    content: str
    metadata: dict[str, Any]
    created_at: float
    ttl_seconds: float
    access_count: int = 0
    last_accessed: float = 0.0

    @property
    def is_expired(self) -> bool:
        return time.time() > self.created_at + self.ttl_seconds


@dataclass
class CompressionStore:
    """In-memory store for compressed content retrieval."""

    max_entries: int = 10000
    default_ttl_seconds: float = 3600
    adaptive_ttl: bool = True
    _entries: dict[str, StoreEntry] = field(default_factory=dict)
    _stats: dict[str, int] = field(default_factory=lambda: {
        "puts": 0,
        "gets": 0,
        "hits": 0,
        "misses": 0,
        "evictions": 0,
    })
    artifact_index: ArtifactIndex = field(default_factory=ArtifactIndex)

    def put(
        self,
        key: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        ttl_seconds: float | None = None,
    ) -> str:
        """Store content and return a retrieval key."""
        # Generate stable key from content hash if not provided
        store_key = self._make_key(key, content)

        # Evict if at capacity
        if len(self._entries) >= self.max_entries:
            self._evict()

        self._entries[store_key] = StoreEntry(
            content=content,
            metadata=metadata or {},
            created_at=time.time(),
            ttl_seconds=ttl_seconds or self.default_ttl_seconds,
            last_accessed=time.time(),
        )
        self._stats["puts"] += 1
        return store_key

    def track(
        self,
        kind: str,
        key: str,
        content: str,
        turn_id: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store content and record it in the artifact index."""
        summary = content[:80].split("\n")[0] if content else ""
        store_key = self.put(key, content, metadata)
        self.artifact_index.add(
            kind=kind, key=key, summary=summary,
            turn_id=turn_id, store_key=store_key,
        )
        return store_key

    def get(self, key: str) -> str | None:
        """Retrieve stored content by key."""
        self._stats["gets"] += 1

        entry = self._entries.get(key)
        if entry is None:
            self._stats["misses"] += 1
            return None

        if entry.is_expired:
            del self._entries[key]
            self._stats["misses"] += 1
            return None

        entry.access_count += 1
        entry.last_accessed = time.time()

        # Extend TTL on access if adaptive
        if self.adaptive_ttl:
            entry.ttl_seconds = min(
                entry.ttl_seconds * 1.5,
                self.default_ttl_seconds * 4,
            )

        self._stats["hits"] += 1
        return entry.content

    def get_metadata(self, key: str) -> dict[str, Any] | None:
        """Get metadata for a stored entry."""
        entry = self._entries.get(key)
        if entry is None or entry.is_expired:
            return None
        return entry.metadata

    def summary(self, key: str, max_length: int = 200) -> str | None:
        """Get a brief summary of stored content."""
        content = self.get(key)
        if content is None:
            return None

        if len(content) <= max_length:
            return content

        # Return first and last portions
        half = max_length // 2
        return f"{content[:half]}...[{len(content)} chars total]...{content[-half:]}"

    @property
    def stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "entries": len(self._entries),
            "hit_rate": (
                self._stats["hits"] / self._stats["gets"]
                if self._stats["gets"] > 0
                else 0.0
            ),
        }

    def clear(self) -> None:
        """Clear all entries."""
        self._entries.clear()

    def _make_key(self, key: str, content: str) -> str:
        """Generate a store key."""
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"{key}:{content_hash}"

    def _evict(self) -> None:
        """Evict least recently accessed entries."""
        # Remove expired first
        expired = [k for k, v in self._entries.items() if v.is_expired]
        for k in expired:
            del self._entries[k]
            self._stats["evictions"] += 1

        # If still over capacity, remove LRU
        while len(self._entries) >= self.max_entries:
            lru_key = min(
                self._entries,
                key=lambda k: self._entries[k].last_accessed,
            )
            del self._entries[lru_key]
            self._stats["evictions"] += 1
