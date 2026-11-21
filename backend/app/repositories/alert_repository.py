"""Neo4j persistence for scheduled-scan alert delivery."""
from __future__ import annotations

from neo4j import Session
from neo4j.exceptions import ServiceUnavailable, TransientError

_QUEUE_NOTIFICATION = """
MERGE (n:Notification {notification_id: $notification_id})
ON CREATE SET
    n.scan_id = $scan_id,
    n.status = 'pending',
    n.subject = $subject,
    n.body = $body,
    n.created_at = $now,
    n.attempts = 0
RETURN n {.*} AS notification
"""

_LIST_RETRYABLE = """
MATCH (n:Notification)
WHERE n.status IN ['pending', 'failed']
   OR (n.status = 'sending' AND coalesce(n.updated_at, n.created_at) <= $stale_before)
RETURN n {.*} AS notification
ORDER BY n.created_at
LIMIT $limit
"""

_CLAIM_NOTIFICATION = """
MATCH (n:Notification {notification_id: $notification_id})
WHERE n.status IN ['pending', 'failed']
   OR (n.status = 'sending' AND coalesce(n.updated_at, n.created_at) <= $stale_before)
SET n.status = 'sending',
    n.attempts = coalesce(n.attempts, 0) + 1,
    n.updated_at = $now
RETURN n {.*} AS notification
"""

_MARK_SENT = """
MATCH (n:Notification {notification_id: $notification_id})
SET n.status = 'sent', n.sent_at = $now, n.updated_at = $now
REMOVE n.last_error
"""

_MARK_FAILED = """
MATCH (n:Notification {notification_id: $notification_id})
SET n.status = 'failed', n.last_error = $error, n.updated_at = $now
"""


def queue_notification(session: Session, notification: dict) -> dict:
    try:
        record = session.run(
            _QUEUE_NOTIFICATION,
            notification_id=notification["notification_id"],
            scan_id=notification["scan_id"],
            subject=notification["subject"],
            body=notification["body"],
            now=notification["created_at"],
        ).single()
        if record is None:
            raise RuntimeError("Neo4j did not return the queued notification.")
        return dict(record["notification"])
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def list_retryable_notifications(
    session: Session,
    stale_before: str,
    limit: int = 100,
) -> list[dict]:
    try:
        result = session.run(
            _LIST_RETRYABLE,
            stale_before=stale_before,
            limit=limit,
        )
        return [dict(record["notification"]) for record in result]
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def claim_notification(
    session: Session,
    notification_id: str,
    now: str,
    stale_before: str,
) -> dict | None:
    try:
        record = session.run(
            _CLAIM_NOTIFICATION,
            notification_id=notification_id,
            now=now,
            stale_before=stale_before,
        ).single()
        return dict(record["notification"]) if record else None
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def mark_notification_sent(session: Session, notification_id: str, now: str) -> None:
    try:
        session.run(_MARK_SENT, notification_id=notification_id, now=now)
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def mark_notification_failed(
    session: Session,
    notification_id: str,
    error: str,
    now: str,
) -> None:
    try:
        session.run(
            _MARK_FAILED,
            notification_id=notification_id,
            error=error[:500],
            now=now,
        )
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc
