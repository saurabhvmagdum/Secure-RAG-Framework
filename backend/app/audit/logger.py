"""
Audit Logger
=============

Protocol and default implementation for immutable audit event logging.
Append-only — no delete or update operations are exposed.

Logs are written to local structured JSON files on a write-once medium.
No external log shipping.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.audit.models import AuditEvent
from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@runtime_checkable
class AuditLogger(Protocol):
    """
    Protocol for immutable audit event logging.

    Implementations must:
    - ONLY support append operations (no update, no delete)
    - Write to durable, tamper-evident storage
    - Include full event context including correlation IDs
    - Never silently drop events — log errors and raise
    """

    def log_event(self, event: AuditEvent) -> None:
        """
        Persist an audit event to the immutable log.

        This operation must be durable — if it returns without error,
        the event is guaranteed to be persisted.

        Raises:
            StorageError if the event cannot be persisted.
        """
        ...

    def query_events(
        self,
        *,
        principal_id: str | None = None,
        action: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        correlation_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """
        Query audit events with filters.

        This is a read-only operation for audit review and compliance.
        Access must be gated by VIEW_AUDIT permission.
        """
        ...


class FileAuditLogger:
    """
    Default file-based audit logger.

    Writes JSON-lines formatted audit events to date-partitioned files.
    Append-only — files are opened in append mode only.

    Storage: {audit_log_path}/audit-{YYYY-MM-DD}.jsonl

    TODO: Phase 2 — implement write-once filesystem integration,
    checksum chains for tamper detection, and indexed query support.
    """

    def __init__(self, log_path: Path | None = None) -> None:
        self._log_path = log_path or settings.audit.audit_log_path
        self._ensure_log_directory()

    def _ensure_log_directory(self) -> None:
        """Create the audit log directory if it doesn't exist."""
        self._log_path.mkdir(parents=True, exist_ok=True)

    def _get_log_file_path(self, dt: datetime) -> Path:
        """Get the log file path for a given date."""
        date_str = dt.strftime("%Y-%m-%d")
        return self._log_path / f"audit-{date_str}.jsonl"

    def log_event(self, event: AuditEvent) -> None:
        """Append audit event to date-partitioned JSONL file."""
        try:
            file_path = self._get_log_file_path(event.timestamp)
            event_json = json.dumps(event.to_log_dict(), default=str)

            # Append-only open mode
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(event_json + "\n")
                f.flush()
                os.fsync(f.fileno())  # Ensure durability

            logger.debug(
                "audit_event_logged",
                event_id=event.event_id,
                action=event.action.value,
                file=str(file_path),
            )

        except Exception as exc:
            # Never silently drop audit events
            logger.error(
                "audit_event_write_failed",
                event_id=event.event_id,
                action=event.action.value,
                error=str(exc),
            )
            from app.core.exceptions import StorageError
            raise StorageError(
                message=f"Failed to write audit event: {exc}",
                backend="file_audit_logger",
                context={"event_id": event.event_id},
            ) from exc

    def query_events(
        self,
        *,
        principal_id: str | None = None,
        action: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        correlation_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """
        Query audit events from JSONL files.

        Phase 1: Simple file-based scan with filters.
        TODO: Phase 2 — implement indexed query for production scale.
        """
        events: list[AuditEvent] = []

        try:
            log_files = sorted(self._log_path.glob("audit-*.jsonl"))

            for log_file in log_files:
                with open(log_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue

                        event_data = json.loads(line)
                        event = AuditEvent(**event_data)

                        # Apply filters
                        if principal_id and event.principal_id != principal_id:
                            continue
                        if action and event.action.value != action:
                            continue
                        if start_time and event.timestamp < start_time:
                            continue
                        if end_time and event.timestamp > end_time:
                            continue
                        if correlation_id and (
                            event.request_id != correlation_id
                            and correlation_id not in event.correlation_ids
                        ):
                            continue

                        events.append(event)

                        if len(events) >= limit:
                            return events

        except Exception as exc:
            logger.error("audit_query_failed", error=str(exc))

        return events
