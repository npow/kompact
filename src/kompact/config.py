"""Configuration for Kompact proxy and transforms."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToonConfig:
    enabled: bool = True
    min_array_length: int = 2
    separator: str = " | "


@dataclass
class ObservationMaskerConfig:
    enabled: bool = True
    keep_last_n: int = 3
    include_summary: bool = True


@dataclass
class CacheAlignerConfig:
    enabled: bool = True
    normalize_uuids: bool = True
    normalize_timestamps: bool = True
    normalize_paths: bool = True


@dataclass
class JsonCrusherConfig:
    enabled: bool = True
    min_array_length: int = 3
    constant_threshold: float = 1.0  # fraction of items that must match
    low_cardinality_threshold: int = 5


@dataclass
class SchemaOptimizerConfig:
    enabled: bool = False  # Requires embedding model, off by default
    max_tools: int = 10
    min_relevance_score: float = 0.3


@dataclass
class CodeCompressorConfig:
    enabled: bool = True
    keep_signatures: bool = True
    keep_imports: bool = True
    keep_docstrings: bool = True
    keep_type_annotations: bool = True
    max_body_lines: int = 0  # 0 = remove all bodies


@dataclass
class LogCompressorConfig:
    enabled: bool = True
    dedup_threshold: int = 3  # Min consecutive similar lines to compress
    keep_first_last: bool = True


@dataclass
class ContentCompressorConfig:
    enabled: bool = True
    target_ratio: float = 0.5  # Keep 50% of tokens
    min_tokens_to_compress: int = 200  # Only compress blocks > this
    entity_boost: float = 1.5
    position_boost: float = 1.2
    protect_recent_user_messages: int = 1
    protect_code_blocks: bool = True


@dataclass
class StoreConfig:
    max_entries: int = 10000
    default_ttl_seconds: int = 3600
    adaptive_ttl: bool = True


@dataclass
class KompactConfig:
    """Top-level configuration."""

    host: str = "0.0.0.0"
    port: int = 7878
    anthropic_base_url: str = "https://api.anthropic.com"
    openai_base_url: str = "https://api.openai.com"
    verbose: bool = False

    # Model fallbacks: if primary model returns 429, retry with the fallback.
    # e.g. {"claude-sonnet-4-6": "claude-sonnet-4-5-20250929"}
    model_fallbacks: dict[str, str] = field(default_factory=dict)

    toon: ToonConfig = field(default_factory=ToonConfig)
    observation_masker: ObservationMaskerConfig = field(default_factory=ObservationMaskerConfig)
    cache_aligner: CacheAlignerConfig = field(default_factory=CacheAlignerConfig)
    json_crusher: JsonCrusherConfig = field(default_factory=JsonCrusherConfig)
    schema_optimizer: SchemaOptimizerConfig = field(default_factory=SchemaOptimizerConfig)
    code_compressor: CodeCompressorConfig = field(default_factory=CodeCompressorConfig)
    log_compressor: LogCompressorConfig = field(default_factory=LogCompressorConfig)
    content_compressor: ContentCompressorConfig = field(default_factory=ContentCompressorConfig)
    store: StoreConfig = field(default_factory=StoreConfig)

    @property
    def disabled_transforms(self) -> set[str]:
        disabled = set()
        for name in [
            "toon", "observation_masker", "cache_aligner",
            "json_crusher", "schema_optimizer", "code_compressor",
            "log_compressor", "content_compressor",
        ]:
            if not getattr(getattr(self, name), "enabled"):
                disabled.add(name)
        return disabled
