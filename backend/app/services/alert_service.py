"""Thresholded scheduled-scan alerts delivered through Brevo email."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.db.neo4j import get_session
from app.repositories import alert_repository

logger = logging.getLogger(__name__)

MIN_ALERT_AREA_SQM = 1000
MIN_ALERT_CONFIDENCE = 0.8
MAX_ALERT_CLOUD_FRACTION = 0.2
BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def qualifying_findings(scan: dict[str, Any]) -> list[dict[str, Any]]:
    source = scan.get("source") or {}
    processing = scan.get("processing") or {}
    cloud_fraction = _number(processing.get("cloudMaskFraction"))
    if source.get("stale") or cloud_fraction is None or cloud_fraction >= MAX_ALERT_CLOUD_FRACTION:
        return []
    if scan.get("status", "completed") != "completed":
        return []

    findings = scan.get("findings") or []
    return [
        finding
        for finding in findings
        if (_number(finding.get("areaSqm", finding.get("area_sqm"))) or 0) >= MIN_ALERT_AREA_SQM
        and (_number(finding.get("confidence")) or 0) >= MIN_ALERT_CONFIDENCE
    ]


def build_scan_notification(scan: dict[str, Any]) -> dict[str, str] | None:
    findings = qualifying_findings(scan)
    scan_id = str(scan.get("scanId") or scan.get("scan_id") or "")
    if not findings or not scan_id:
        return None

    source = scan.get("source") or {}
    site_name = str(source.get("siteName") or scan.get("region") or "Monitoring site")
    lines = [
        f"GeoSentinel AI detected {len(findings)} threshold-qualified change(s) at {site_name}.",
        f"Scan: {scan_id}",
        f"Observation window: {scan.get('historicalDate', 'unknown')} to {scan.get('recentDate', 'unknown')}",
        "",
        "Automated screening signal only. Verify imagery, permits, and field conditions before taking action.",
        "",
    ]
    for finding in findings:
        area = _number(finding.get("areaSqm", finding.get("area_sqm"))) or 0
        confidence = _number(finding.get("confidence")) or 0
        label = finding.get("label") or finding.get("areaName") or finding.get("area_name") or "Detected change"
        lines.append(f"- {label}: {area:,.0f} m², {confidence:.0%} confidence")
        satellite_url = finding.get("googleSatelliteUrl")
        if satellite_url:
            lines.append(f"  Satellite view: {satellite_url}")

    subject = f"GeoSentinel alert: {site_name} ({len(findings)} qualifying change(s))"
    notification_id = hashlib.sha256(f"scheduled-scan-alert:{scan_id}".encode("utf-8")).hexdigest()
    return {
        "notification_id": notification_id,
        "scan_id": scan_id,
        "subject": subject[:180],
        "body": "\n".join(lines)[:10000],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def queue_scan_notification(scan: dict[str, Any]) -> bool:
    notification = build_scan_notification(scan)
    if notification is None:
        return False
    with get_session() as session:
        alert_repository.queue_notification(session, notification)
    return True


def send_brevo_email(subject: str, body: str) -> None:
    api_key = os.getenv("BREVO_API_KEY", "").strip()
    sender_email = os.getenv("BREVO_FROM_EMAIL", "").strip()
    recipient_email = os.getenv("ALERT_TO_EMAIL", "").strip()
    missing = [
        name
        for name, value in (
            ("BREVO_API_KEY", api_key),
            ("BREVO_FROM_EMAIL", sender_email),
            ("ALERT_TO_EMAIL", recipient_email),
        )
        if not value
    ]
    if missing:
        raise RuntimeError("Brevo alert settings are missing: " + ", ".join(missing))

    sender_name = os.getenv("BREVO_FROM_NAME", "GeoSentinel AI").strip() or "GeoSentinel AI"
    payload = json.dumps({
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": recipient_email}],
        "subject": subject,
        "textContent": body,
    }).encode("utf-8")
    request = Request(
        BREVO_API_URL,
        data=payload,
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"Brevo returned HTTP {response.status}.")
    except HTTPError as exc:
        raise RuntimeError(f"Brevo returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach Brevo: {exc.reason}") from exc


def send_retryable_notifications(
    *,
    now: datetime | None = None,
    email_sender: Callable[[str, str], None] = send_brevo_email,
    limit: int = 100,
) -> dict[str, int]:
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)
    now_text = current_time.isoformat()
    stale_before = (current_time - timedelta(minutes=15)).isoformat()
    with get_session() as session:
        notifications = alert_repository.list_retryable_notifications(
            session,
            stale_before=stale_before,
            limit=limit,
        )

    sent = 0
    failed = 0
    for notification in notifications:
        notification_id = notification["notification_id"]
        with get_session() as session:
            claimed = alert_repository.claim_notification(
                session,
                notification_id,
                now=now_text,
                stale_before=stale_before,
            )
        if claimed is None:
            continue
        try:
            email_sender(claimed["subject"], claimed["body"])
        except Exception as exc:
            logger.warning("Scheduled alert %s could not be sent: %s", notification_id, exc)
            with get_session() as session:
                alert_repository.mark_notification_failed(
                    session,
                    notification_id,
                    str(exc),
                    now=now_text,
                )
            failed += 1
        else:
            with get_session() as session:
                alert_repository.mark_notification_sent(session, notification_id, now=now_text)
            sent += 1
    return {"sent": sent, "failed": failed}
