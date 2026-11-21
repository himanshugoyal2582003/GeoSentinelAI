"""Daily Render cron entry point for five-day monitoring scans."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.db.neo4j import get_driver, get_session
from app.db.schema import initialize_schema
from app.geometry import geometry_bbox, normalize_polygon_geometry
from app.repositories import region_repository, scan_repository
from app.services.alert_service import queue_scan_notification, send_retryable_notifications

logger = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(days=5)
SITE_PAGE_SIZE = 200


def _as_datetime(value: Any) -> datetime:
    if hasattr(value, "to_native"):
        value = value.to_native()
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("Latest scan has no valid created_at timestamp.")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _site_geometry(site: dict[str, Any]) -> dict[str, Any]:
    geometry = site.get("geometry_geojson")
    if isinstance(geometry, str):
        geometry = json.loads(geometry)
    return normalize_polygon_geometry(geometry)


def _is_due(last_scan: dict[str, Any] | None, now: datetime) -> bool:
    if last_scan is None:
        return True
    return now - _as_datetime(last_scan.get("created_at")) >= SCAN_INTERVAL


def run_scheduled_scans(
    *,
    now: datetime | None = None,
    scanner: Callable[..., dict[str, Any]] | None = None,
    notification_queue: Callable[[dict[str, Any]], bool] = queue_scan_notification,
    notification_dispatch: Callable[..., dict[str, int]] = send_retryable_notifications,
) -> dict[str, int]:
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)
    if scanner is None:
        from app.main import _execute_live_detect

        scanner = _execute_live_detect

    sites_due: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    with get_session() as session:
        offset = 0
        while True:
            sites = region_repository.list_sites(session, limit=SITE_PAGE_SIZE, offset=offset)
            for site in sites:
                region_id = site.get("region_id")
                if not region_id:
                    logger.warning("Skipping a monitoring site without a region_id.")
                    continue
                latest_scans = scan_repository.list_scans(
                    session,
                    region_id=region_id,
                    limit=1,
                    offset=0,
                )
                latest_scan = latest_scans[0] if latest_scans else None
                if _is_due(latest_scan, current_time):
                    sites_due.append((site, latest_scan))
            if len(sites) < SITE_PAGE_SIZE:
                break
            offset += SITE_PAGE_SIZE

    scanned = 0
    skipped = 0
    failed = 0
    for site, _ in sites_due:
        site_id = site["region_id"]
        try:
            geometry = _site_geometry(site)
            result = scanner(
                bbox=geometry_bbox(geometry),
                geometry=geometry,
                region_name=site.get("name") or "Monitoring site",
                region_id=site_id,
                idempotency_key=f"scheduled:{site_id}:{current_time.date().isoformat()}",
            )
            if result.get("source", {}).get("stale"):
                logger.info("Skipping stale cached result for scheduled site %s.", site_id)
                skipped += 1
                continue
            scanned += 1
            if notification_queue(result):
                logger.info("Queued a threshold-qualified alert for site %s.", site_id)
        except Exception:
            logger.exception("Scheduled scan failed for site %s.", site_id)
            failed += 1

    try:
        alert_summary = notification_dispatch(now=current_time)
    except Exception:
        logger.exception("Could not process scheduled alert queue.")
        alert_summary = {"sent": 0, "failed": 1}

    return {
        "sites_due": len(sites_due),
        "scanned": scanned,
        "skipped": skipped,
        "failed": failed,
        "alerts_sent": alert_summary.get("sent", 0),
        "alerts_failed": alert_summary.get("failed", 0),
    }


def main() -> int:
    initialize_schema(get_driver())
    summary = run_scheduled_scans()
    logger.info("Scheduled monitoring run: %s", summary)
    return 1 if summary["failed"] or summary["alerts_failed"] else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
