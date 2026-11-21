from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.services.alert_service import build_scan_notification, qualifying_findings
from app.services.evidence_service import CloudflareR2Storage
from app.worker import cron_scan
from app.services import alert_service


class FakeR2Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.content_types: dict[tuple[str, str], str] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        self.objects[(Bucket, Key)] = Body
        self.content_types[(Bucket, Key)] = ContentType

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, io.BytesIO]:
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}


def _scan_result(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "scanId": "scan-123",
        "region": "Test quarry",
        "historicalDate": "2026-01-01",
        "recentDate": "2026-01-06",
        "source": {"siteName": "Test quarry"},
        "processing": {"cloudMaskFraction": 0.05},
        "findings": [{
            "id": "finding-1",
            "label": "Detected change",
            "areaSqm": 1200,
            "confidence": 0.85,
            "googleSatelliteUrl": "https://maps.example.test/site",
        }],
    }
    result.update(overrides)
    return result


def test_r2_storage_round_trips_bytes_and_rejects_other_buckets() -> None:
    client = FakeR2Client()
    storage = CloudflareR2Storage(
        bucket="evidence",
        account_id="account",
        access_key_id="access",
        secret_access_key="secret",
        client=client,
    )

    uri, sha256, size = storage.store_bytes(b"image-bytes", "../../historical.png")

    assert uri.startswith("r2://evidence/evidence/")
    assert len(sha256) == 64
    assert size == len(b"image-bytes")
    assert client.content_types[("evidence", uri.split("/", 3)[-1])] == "image/png"
    assert storage.read_bytes(uri) == b"image-bytes"
    with pytest.raises(ValueError):
        storage.read_bytes("r2://other-bucket/evidence/file.png")


def test_alerts_require_fresh_low_cloud_threshold_qualified_findings() -> None:
    scan = _scan_result()
    assert len(qualifying_findings(scan)) == 1
    assert build_scan_notification(scan)["scan_id"] == "scan-123"

    below_area = _scan_result(findings=[{"areaSqm": 999, "confidence": 0.99}])
    below_confidence = _scan_result(findings=[{"areaSqm": 1500, "confidence": 0.79}])
    cloudy = _scan_result(processing={"cloudMaskFraction": 0.2})
    stale = _scan_result(source={"stale": True})

    assert qualifying_findings(below_area) == []
    assert qualifying_findings(below_confidence) == []
    assert qualifying_findings(cloudy) == []
    assert qualifying_findings(stale) == []


def test_brevo_delivery_uses_configured_recipient_without_network_calls(monkeypatch) -> None:
    monkeypatch.setenv("BREVO_API_KEY", "test-api-key")
    monkeypatch.setenv("BREVO_FROM_EMAIL", "alerts@example.test")
    monkeypatch.setenv("ALERT_TO_EMAIL", "operator@example.test")
    response = MagicMock()
    response.status = 201
    response.__enter__.return_value = response
    with patch.object(alert_service, "urlopen", return_value=response) as urlopen:
        alert_service.send_brevo_email("Test alert", "Screening signal")

    request = urlopen.call_args.args[0]
    headers = {key.lower(): value for key, value in request.header_items()}
    payload = json.loads(request.data)
    assert headers["api-key"] == "test-api-key"
    assert payload["to"] == [{"email": "operator@example.test"}]
    assert payload["subject"] == "Test alert"


def test_retryable_alert_is_claimed_sent_and_marked() -> None:
    notification = {
        "notification_id": "notice-123",
        "subject": "Test alert",
        "body": "Screening signal",
    }
    session = MagicMock()
    session.__enter__.return_value = session
    sender = MagicMock()
    with (
        patch.object(alert_service, "get_session", return_value=session),
        patch.object(
            alert_service.alert_repository,
            "list_retryable_notifications",
            return_value=[notification],
        ),
        patch.object(
            alert_service.alert_repository,
            "claim_notification",
            return_value=notification,
        ),
        patch.object(alert_service.alert_repository, "mark_notification_sent") as mark_sent,
    ):
        result = alert_service.send_retryable_notifications(
            now=datetime(2026, 1, 10, tzinfo=timezone.utc),
            email_sender=sender,
        )

    assert result == {"sent": 1, "failed": 0}
    sender.assert_called_once_with("Test alert", "Screening signal")
    mark_sent.assert_called_once()


def test_daily_worker_scans_sites_only_after_five_days() -> None:
    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    site = {
        "region_id": "site-123",
        "name": "Test quarry",
        "geometry_geojson": json.dumps({
            "type": "Polygon",
            "coordinates": [[[73.82, 18.48], [73.83, 18.48], [73.83, 18.49], [73.82, 18.48]]],
        }),
    }
    session = MagicMock()
    session.__enter__.return_value = session
    scanner = MagicMock(return_value=_scan_result())
    queued: list[dict[str, Any]] = []

    with (
        patch.object(cron_scan, "get_session", return_value=session),
        patch.object(cron_scan.region_repository, "list_sites", return_value=[site]),
        patch.object(cron_scan.scan_repository, "list_scans", return_value=[]),
    ):
        result = cron_scan.run_scheduled_scans(
            now=now,
            scanner=scanner,
            notification_queue=lambda scan: queued.append(scan) or True,
            notification_dispatch=lambda **_: {"sent": 1, "failed": 0},
        )

    assert result == {
        "sites_due": 1,
        "scanned": 1,
        "skipped": 0,
        "failed": 0,
        "alerts_sent": 1,
        "alerts_failed": 0,
    }
    scanner.assert_called_once()
    assert scanner.call_args.kwargs["region_id"] == "site-123"
    assert len(queued) == 1

    recent_scan = {"created_at": (now - timedelta(days=4)).isoformat()}
    scanner.reset_mock()
    with (
        patch.object(cron_scan, "get_session", return_value=session),
        patch.object(cron_scan.region_repository, "list_sites", return_value=[site]),
        patch.object(cron_scan.scan_repository, "list_scans", return_value=[recent_scan]),
    ):
        result = cron_scan.run_scheduled_scans(
            now=now,
            scanner=scanner,
            notification_queue=lambda _: pytest.fail("No alert should be queued without a scan."),
            notification_dispatch=lambda **_: {"sent": 0, "failed": 0},
        )
    assert result["sites_due"] == 0
    scanner.assert_not_called()


def test_stale_worker_results_do_not_queue_alerts() -> None:
    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    site = {
        "region_id": "site-123",
        "name": "Test quarry",
        "geometry_geojson": {
            "type": "Polygon",
            "coordinates": [[[73.82, 18.48], [73.83, 18.48], [73.83, 18.49], [73.82, 18.48]]],
        },
    }
    session = MagicMock()
    session.__enter__.return_value = session
    queued = []

    with (
        patch.object(cron_scan, "get_session", return_value=session),
        patch.object(cron_scan.region_repository, "list_sites", return_value=[site]),
        patch.object(cron_scan.scan_repository, "list_scans", return_value=[]),
    ):
        result = cron_scan.run_scheduled_scans(
            now=now,
            scanner=lambda **_: _scan_result(source={"stale": True}),
            notification_queue=lambda scan: queued.append(scan),
            notification_dispatch=lambda **_: {"sent": 0, "failed": 0},
        )

    assert result["skipped"] == 1
    assert queued == []
