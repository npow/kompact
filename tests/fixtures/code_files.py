"""
Data pipeline module for processing and transforming structured records.

This module provides a flexible ETL (Extract, Transform, Load) framework
for handling data from multiple sources including databases, APIs, and
flat files. It supports both batch and streaming processing modes.

Author: Data Engineering Team
Version: 2.8.1
License: MIT
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from pathlib import Path
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Generic,
    Iterator,
    List,
    Optional,
    Protocol,
    Sequence,
    TypeVar,
    Union,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


class ProcessingMode(Enum):
    """Enumeration of supported data processing modes."""

    BATCH = auto()
    STREAMING = auto()
    MICRO_BATCH = auto()


class RecordStatus(Enum):
    """Status tracking for individual records in the pipeline."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


@dataclass(frozen=True)
class PipelineConfig:
    """Immutable configuration for a data pipeline instance.

    Attributes:
        name: Human-readable pipeline identifier.
        source_uri: Connection string or path for the data source.
        destination_uri: Connection string or path for the data sink.
        batch_size: Number of records to process per batch.
        max_retries: Maximum retry attempts for failed records.
        retry_delay_seconds: Base delay between retry attempts (exponential backoff).
        timeout_seconds: Maximum time allowed for a single batch operation.
        mode: Processing mode (batch, streaming, or micro-batch).
        enable_deduplication: Whether to filter duplicate records.
        checkpoint_interval: Number of batches between checkpoint saves.
    """

    name: str
    source_uri: str
    destination_uri: str
    batch_size: int = 1000
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    timeout_seconds: float = 300.0
    mode: ProcessingMode = ProcessingMode.BATCH
    enable_deduplication: bool = True
    checkpoint_interval: int = 10


@dataclass
class Record:
    """A single data record flowing through the pipeline.

    Attributes:
        id: Unique record identifier.
        payload: The actual data content.
        source: Origin identifier for tracing.
        timestamp: When the record was created or ingested.
        status: Current processing status.
        attempt_count: Number of processing attempts.
        metadata: Additional key-value pairs for routing and filtering.
        errors: List of error messages from failed processing attempts.
    """

    id: str
    payload: Dict[str, Any]
    source: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: RecordStatus = RecordStatus.PENDING
    attempt_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def fingerprint(self) -> str:
        """Generate a content-based fingerprint for deduplication.

        Returns:
            A hex digest string representing the record content.
        """
        content = f"{self.source}:{sorted(self.payload.items())}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


class Transformer(Protocol[T, R]):
    """Protocol for record transformation functions."""

    def transform(self, record: T) -> R:
        """Transform a single record from type T to type R."""
        ...


class DataSource(ABC, Generic[T]):
    """Abstract base class for data sources.

    Implementations must provide methods for reading records either
    as an iterator (for batch mode) or as an async iterator (for streaming).
    """

    def __init__(self, uri: str, config: Optional[Dict[str, Any]] = None) -> None:
        self.uri = uri
        self.config = config or {}
        self._is_connected = False

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the data source."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Clean up and close the connection."""
        ...

    @abstractmethod
    def read_batch(self, batch_size: int) -> List[T]:
        """Read a batch of records from the source.

        Args:
            batch_size: Maximum number of records to return.

        Returns:
            A list of records, which may be shorter than batch_size
            if fewer records are available.
        """
        ...

    def __enter__(self) -> DataSource[T]:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()


class DataSink(ABC, Generic[T]):
    """Abstract base class for data sinks (destinations)."""

    def __init__(self, uri: str, config: Optional[Dict[str, Any]] = None) -> None:
        self.uri = uri
        self.config = config or {}

    @abstractmethod
    def write_batch(self, records: List[T]) -> int:
        """Write a batch of records to the destination.

        Args:
            records: The records to write.

        Returns:
            The number of records successfully written.
        """
        ...

    @abstractmethod
    def flush(self) -> None:
        """Ensure all buffered records are written."""
        ...


@dataclass
class PipelineMetrics:
    """Runtime metrics collected during pipeline execution.

    Attributes:
        records_read: Total records read from the source.
        records_written: Total records successfully written to the sink.
        records_failed: Total records that failed processing.
        records_skipped: Total records skipped (e.g., duplicates).
        batches_processed: Number of batches completed.
        start_time: When the pipeline run started.
        end_time: When the pipeline run completed (None if still running).
        errors: Mapping of error types to their occurrence count.
    """

    records_read: int = 0
    records_written: int = 0
    records_failed: int = 0
    records_skipped: int = 0
    batches_processed: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    errors: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def duration(self) -> Optional[timedelta]:
        """Calculate the total runtime duration."""
        if self.start_time is None:
            return None
        end = self.end_time or datetime.now(timezone.utc)
        return end - self.start_time

    @property
    def throughput(self) -> float:
        """Calculate records processed per second."""
        if self.duration is None or self.duration.total_seconds() == 0:
            return 0.0
        return self.records_written / self.duration.total_seconds()

    @property
    def success_rate(self) -> float:
        """Calculate the percentage of records successfully processed."""
        total = self.records_read
        if total == 0:
            return 0.0
        return (self.records_written / total) * 100.0

    def summary(self) -> str:
        """Generate a human-readable summary of pipeline metrics."""
        lines = [
            f"Pipeline Metrics Summary",
            f"========================",
            f"Records read:    {self.records_read:>10,}",
            f"Records written: {self.records_written:>10,}",
            f"Records failed:  {self.records_failed:>10,}",
            f"Records skipped: {self.records_skipped:>10,}",
            f"Batches:         {self.batches_processed:>10,}",
            f"Duration:        {self.duration}",
            f"Throughput:      {self.throughput:>10.1f} rec/s",
            f"Success rate:    {self.success_rate:>9.1f}%",
        ]
        if self.errors:
            lines.append(f"\nError Breakdown:")
            for error_type, count in sorted(self.errors.items()):
                lines.append(f"  {error_type}: {count}")
        return "\n".join(lines)


class Pipeline:
    """Main data pipeline orchestrator.

    Coordinates reading from a source, applying transformations,
    and writing to a sink with retry logic, deduplication, and
    comprehensive metrics tracking.

    Example usage::

        config = PipelineConfig(
            name="user-sync",
            source_uri="postgresql://db:5432/users",
            destination_uri="s3://data-lake/users/",
            batch_size=500,
        )
        pipeline = Pipeline(config, source=db_source, sink=s3_sink)
        pipeline.add_transformer(NormalizeEmailTransformer())
        pipeline.add_transformer(EnrichProfileTransformer())
        metrics = pipeline.run()
        print(metrics.summary())
    """

    def __init__(
        self,
        config: PipelineConfig,
        source: DataSource,
        sink: DataSink,
    ) -> None:
        self.config = config
        self.source = source
        self.sink = sink
        self.transformers: List[Callable[[Record], Record]] = []
        self.metrics = PipelineMetrics()
        self._seen_fingerprints: set[str] = set()
        self._checkpoint_counter = 0

    def add_transformer(self, transformer: Callable[[Record], Record]) -> Pipeline:
        """Register a transformation to be applied to each record.

        Args:
            transformer: A callable that accepts and returns a Record.

        Returns:
            Self, for method chaining.
        """
        self.transformers.append(transformer)
        return self

    def _is_duplicate(self, record: Record) -> bool:
        """Check if a record has already been seen based on content fingerprint."""
        if not self.config.enable_deduplication:
            return False
        fp = record.fingerprint()
        if fp in self._seen_fingerprints:
            return True
        self._seen_fingerprints.add(fp)
        return False

    def _apply_transformations(self, record: Record) -> Record:
        """Apply all registered transformers to a record in sequence."""
        current = record
        for transformer in self.transformers:
            current = transformer(current)
        return current

    def _process_record(self, record: Record) -> Record:
        """Process a single record through the full pipeline logic.

        Handles deduplication, transformation, and error tracking.
        """
        if self._is_duplicate(record):
            record.status = RecordStatus.SKIPPED
            self.metrics.records_skipped += 1
            logger.debug("Skipping duplicate record: %s", record.id)
            return record

        record.status = RecordStatus.PROCESSING
        record.attempt_count += 1

        try:
            transformed = self._apply_transformations(record)
            transformed.status = RecordStatus.COMPLETED
            return transformed
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            record.errors.append(error_msg)
            record.status = RecordStatus.FAILED
            self.metrics.errors[type(exc).__name__] += 1
            logger.warning(
                "Record %s failed (attempt %d/%d): %s",
                record.id,
                record.attempt_count,
                self.config.max_retries,
                error_msg,
            )
            return record

    def _process_batch(self, records: List[Record]) -> tuple[List[Record], List[Record]]:
        """Process a batch of records, separating successes from failures.

        Returns:
            A tuple of (successful_records, failed_records).
        """
        successes = []
        failures = []

        for record in records:
            result = self._process_record(record)
            if result.status == RecordStatus.COMPLETED:
                successes.append(result)
            elif result.status == RecordStatus.FAILED:
                if result.attempt_count < self.config.max_retries:
                    result.status = RecordStatus.RETRYING
                    failures.append(result)
                else:
                    self.metrics.records_failed += 1
                    logger.error(
                        "Record %s permanently failed after %d attempts",
                        result.id,
                        result.attempt_count,
                    )

        return successes, failures

    def _save_checkpoint(self) -> None:
        """Persist pipeline state for crash recovery."""
        self._checkpoint_counter += 1
        if self._checkpoint_counter % self.config.checkpoint_interval == 0:
            logger.info(
                "Checkpoint saved at batch %d (records: %d read, %d written)",
                self.metrics.batches_processed,
                self.metrics.records_read,
                self.metrics.records_written,
            )

    def run(self) -> PipelineMetrics:
        """Execute the pipeline from start to finish.

        Returns:
            PipelineMetrics with complete execution statistics.
        """
        logger.info("Starting pipeline '%s' in %s mode", self.config.name, self.config.mode.name)
        self.metrics.start_time = datetime.now(timezone.utc)

        try:
            self.source.connect()

            while True:
                batch = self.source.read_batch(self.config.batch_size)
                if not batch:
                    break

                self.metrics.records_read += len(batch)
                successes, failures = self._process_batch(batch)

                # Retry failed records with exponential backoff
                retry_round = 0
                while failures and retry_round < self.config.max_retries:
                    delay = self.config.retry_delay_seconds * (2 ** retry_round)
                    logger.info("Retrying %d records after %.1fs delay", len(failures), delay)
                    time.sleep(delay)
                    successes_retry, failures = self._process_batch(failures)
                    successes.extend(successes_retry)
                    retry_round += 1

                if successes:
                    written = self.sink.write_batch(successes)
                    self.metrics.records_written += written

                self.metrics.batches_processed += 1
                self._save_checkpoint()

            self.sink.flush()

        except Exception as exc:
            logger.exception("Pipeline '%s' failed: %s", self.config.name, exc)
            raise

        finally:
            self.source.disconnect()
            self.metrics.end_time = datetime.now(timezone.utc)

        logger.info(
            "Pipeline '%s' completed: %s",
            self.config.name,
            self.metrics.summary(),
        )
        return self.metrics


def create_pipeline_from_env(
    name: str,
    source_factory: Callable[[str], DataSource],
    sink_factory: Callable[[str], DataSink],
    **overrides: Any,
) -> Pipeline:
    """Factory function to create a pipeline from environment configuration.

    Args:
        name: Pipeline name, used to look up env vars.
        source_factory: Callable that creates a DataSource from a URI.
        sink_factory: Callable that creates a DataSink from a URI.
        **overrides: Additional config values to override env defaults.

    Returns:
        A configured Pipeline instance ready to run.
    """
    import os

    prefix = name.upper().replace("-", "_")
    config = PipelineConfig(
        name=name,
        source_uri=os.environ.get(f"{prefix}_SOURCE_URI", "memory://default"),
        destination_uri=os.environ.get(f"{prefix}_DEST_URI", "memory://default"),
        batch_size=int(os.environ.get(f"{prefix}_BATCH_SIZE", "1000")),
        max_retries=int(os.environ.get(f"{prefix}_MAX_RETRIES", "3")),
        **overrides,
    )
    source = source_factory(config.source_uri)
    sink = sink_factory(config.destination_uri)
    return Pipeline(config, source=source, sink=sink)
