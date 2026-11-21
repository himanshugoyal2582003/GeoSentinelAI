from __future__ import annotations

import io
import json
import logging
import math
import re
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from PIL import Image, ImageDraw
from rasterio.transform import Affine
from rasterio.warp import transform as transform_coordinates
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.db.neo4j import get_session
from app.history import read_findings_for_scan as read_csv_findings_for_scan
from app.history import read_scan as read_csv_scan
from app.repositories import finding_repository, scan_repository
from app.services.evidence_service import read_evidence_bytes

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scans", tags=["reports"])

MEDIA_DIR = Path(__file__).resolve().parents[2] / "data" / "live"
MAX_CLOUD_MASK_FRACTION = 0.2
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 36
INK = HexColor("#20302c")
MUTED = HexColor("#68746e")
GREEN = HexColor("#60751a")
PALE = HexColor("#f1f3ea")
RED = HexColor("#aa4839")
AMBER = HexColor("#8b6413")

ReportTemplate = Literal["quarry-compliance", "landowner-evidence"]


def _load_scan_record(scan_id: str) -> tuple[dict[str, Any], bool]:
    try:
        with get_session() as session:
            scan = scan_repository.get_scan(session, scan_id)
    except Exception as exc:
        logger.warning("Neo4j unavailable for scan report %s; checking CSV history: %s", scan_id, exc)
        scan = read_csv_scan(scan_id)
        if scan is None:
            raise HTTPException(status_code=503, detail="Scan report storage is unavailable.") from exc
        return scan, True

    if scan is None:
        scan = read_csv_scan(scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan not found.")
        return scan, True
    return scan, False


def _load_scan_report_data(scan_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    scan, from_csv = _load_scan_record(scan_id)
    if from_csv:
        return scan, read_csv_findings_for_scan(scan_id)
    try:
        with get_session() as session:
            findings = finding_repository.list_findings_for_scan(session, scan_id)
    except Exception as exc:
        logger.warning("Neo4j findings unavailable for scan report %s; checking CSV history: %s", scan_id, exc)
        findings = read_csv_findings_for_scan(scan_id)
        expected_count = _finite_number(scan.get("finding_count"))
        if expected_count is not None and len(findings) < expected_count:
            raise HTTPException(
                status_code=503,
                detail="Finding storage is unavailable or incomplete for this scan.",
            ) from exc
    return scan, findings


def _json_mapping(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Stored scan {field} is not valid JSON.") from exc
    if not isinstance(decoded, dict):
        raise ValueError(f"Stored scan {field} must be a JSON object.")
    return decoded


def _finding_id(finding: dict[str, Any]) -> str:
    return str(
        finding.get("original_finding_id")
        or finding.get("finding_id")
        or finding.get("detection_id")
        or finding.get("id")
        or ""
    )


def _value(finding: dict[str, Any] | None, *names: str, default: Any = None) -> Any:
    if finding is None:
        return default
    for name in names:
        if name in finding and finding[name] is not None:
            return finding[name]
    return default


def _clean_text(value: Any, fallback: str = "Not available") -> str:
    text = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or "")).strip()
    return text or fallback


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _scan_cloud_fraction(processing: dict[str, Any], source: dict[str, Any]) -> float | None:
    fraction = _finite_number(processing.get("cloudMaskFraction"))
    if fraction is not None:
        return min(1.0, max(0.0, fraction))
    cloud_pixels = _finite_number(processing.get("cloudMaskPixels"))
    grid = source.get("grid")
    if cloud_pixels is None or not isinstance(grid, dict):
        return None
    width = _finite_number(grid.get("width"))
    height = _finite_number(grid.get("height"))
    if not width or not height or width < 1 or height < 1:
        return None
    return min(1.0, max(0.0, cloud_pixels / (width * height)))


def _capture_images(
    source: dict[str, Any],
    media_dir: Path = MEDIA_DIR,
) -> tuple[Path | io.BytesIO | None, Path | io.BytesIO | None]:
    capture_id = source.get("imageCaptureId")
    if not isinstance(capture_id, str) or not re.fullmatch(r"[a-f0-9]{32}", capture_id):
        capture_id = None

    images: list[Path | io.BytesIO | None] = []
    for kind in ("historical", "recent"):
        local_path = media_dir / f"{kind}-{capture_id}.png" if capture_id else None
        if local_path is not None and local_path.is_file():
            images.append(local_path)
            continue
        asset_uri = source.get(f"{kind}ImageAssetUri")
        if isinstance(asset_uri, str) and asset_uri:
            images.append(io.BytesIO(read_evidence_bytes(asset_uri)))
        else:
            images.append(None)
    return images[0], images[1]


def _pixel_coordinate(
    longitude: float,
    latitude: float,
    source: dict[str, Any],
    image_size: tuple[int, int],
) -> tuple[float, float] | None:
    grid = source.get("grid")
    if isinstance(grid, dict):
        try:
            transform = grid["transform"]
            if not isinstance(transform, (list, tuple)) or len(transform) < 6:
                return None
            affine = Affine(*(float(value) for value in transform[:6]))
            xs, ys = transform_coordinates(
                "EPSG:4326",
                str(grid["crs"]),
                [longitude],
                [latitude],
            )
            column, row = (~affine) * (xs[0], ys[0])
            return float(column), float(row)
        except (KeyError, TypeError, ValueError, IndexError):
            return None

    bbox = source.get("bbox")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    west, south, east, north = (_finite_number(item) for item in bbox)
    if None in (west, south, east, north) or east == west or north == south:
        return None
    width, height = image_size
    return (
        (longitude - west) / (east - west) * width,
        (north - latitude) / (north - south) * height,
    )


def _finding_polygon_pixels(
    finding: dict[str, Any] | None,
    source: dict[str, Any],
    image_size: tuple[int, int],
) -> list[tuple[float, float]]:
    bbox = _value(finding, "region_bbox", "regionBbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        min_lat, min_lon, max_lat, max_lon = (_finite_number(item) for item in bbox)
        if None not in (min_lat, min_lon, max_lat, max_lon):
            corners = (
                (min_lon, max_lat),
                (max_lon, max_lat),
                (max_lon, min_lat),
                (min_lon, min_lat),
            )
            projected = [
                _pixel_coordinate(lon, lat, source, image_size)
                for lon, lat in corners
            ]
            if all(point is not None for point in projected):
                return [point for point in projected if point is not None]

    latitude = _finite_number(_value(finding, "latitude"))
    longitude = _finite_number(_value(finding, "longitude"))
    if latitude is None or longitude is None:
        return []
    center = _pixel_coordinate(longitude, latitude, source, image_size)
    if center is None:
        return []
    x, y = center
    return [(x - 12, y - 12), (x + 12, y - 12), (x + 12, y + 12), (x - 12, y + 12)]


def _site_polygon_pixels(
    source: dict[str, Any],
    image_size: tuple[int, int],
) -> list[list[tuple[float, float]]]:
    geometry = source.get("geometry")
    if not isinstance(geometry, dict):
        return []
    coordinates = geometry.get("coordinates")
    if geometry.get("type") == "Polygon":
        polygons = [coordinates]
    elif geometry.get("type") == "MultiPolygon":
        polygons = coordinates
    else:
        return []

    result: list[list[tuple[float, float]]] = []
    for polygon in polygons or []:
        if not isinstance(polygon, (list, tuple)) or not polygon:
            continue
        ring = polygon[0]
        if not isinstance(ring, (list, tuple)):
            continue
        points = []
        for coordinate in ring:
            if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
                continue
            longitude = _finite_number(coordinate[0])
            latitude = _finite_number(coordinate[1])
            if longitude is None or latitude is None:
                continue
            pixel = _pixel_coordinate(longitude, latitude, source, image_size)
            if pixel is not None:
                points.append(pixel)
        if len(points) >= 3:
            result.append(points)
    return result


def _make_crop(
    image_path: Path | io.BytesIO | None,
    finding: dict[str, Any] | None,
    source: dict[str, Any],
) -> io.BytesIO | None:
    if image_path is None:
        return None
    try:
        if isinstance(image_path, io.BytesIO):
            image_path.seek(0)
        with Image.open(image_path) as opened:
            image = opened.convert("RGB")
    except OSError:
        logger.warning("Could not read report evidence image %s", image_path)
        return None

    width, height = image.size
    feature = _finding_polygon_pixels(finding, source, image.size)
    if feature:
        xs, ys = zip(*feature)
        center_x = (min(xs) + max(xs)) / 2
        center_y = (min(ys) + max(ys)) / 2
        feature_width = max(max(xs) - min(xs), 1)
        feature_height = max(max(ys) - min(ys), 1)
        crop_width = min(width, max(96, feature_width * 3, feature_height * 3 * 1.7))
        crop_height = min(height, max(72, crop_width / 1.7))
        crop_width = min(width, max(crop_width, crop_height * 1.7))
    else:
        center_x, center_y = width / 2, height / 2
        crop_width, crop_height = width, height

    left = max(0, min(width - crop_width, center_x - crop_width / 2))
    top = max(0, min(height - crop_height, center_y - crop_height / 2))
    box = (
        int(left),
        int(top),
        max(int(left) + 1, min(width, int(left + crop_width))),
        max(int(top) + 1, min(height, int(top + crop_height))),
    )
    crop = image.crop(box)
    draw = ImageDraw.Draw(crop)

    def local_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [(x - box[0], y - box[1]) for x, y in points]

    for ring in _site_polygon_pixels(source, image.size):
        draw.line(local_points(ring + [ring[0]]), fill="#a5cb45", width=3)
    if feature:
        draw.line(local_points(feature + [feature[0]]), fill="#f06454", width=3)

    crop.thumbnail((760, 360), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    crop.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


def _cloud_status(
    scan: dict[str, Any],
    source: dict[str, Any],
    processing: dict[str, Any],
    has_images: bool,
    finding: dict[str, Any] | None,
) -> tuple[str, str, Any]:
    fraction = _scan_cloud_fraction(processing, source)
    if scan.get("status") not in (None, "completed"):
        return "INCONCLUSIVE", "The stored scan is not marked completed.", fraction
    if source.get("stale"):
        return "CLOUDY / INCONCLUSIVE", "The result is a cached scan, not a fresh acquisition.", fraction
    if fraction is not None and fraction >= MAX_CLOUD_MASK_FRACTION:
        return (
            "CLOUDY / INCONCLUSIVE",
            f"{fraction:.0%} of the scan pixels were masked; review the imagery before relying on this signal.",
            fraction,
        )
    if not has_images:
        return "INCONCLUSIVE", "The original scan-specific before/after imagery is unavailable.", fraction
    if finding is None:
        return "NO CHANGE FLAGGED", "No finding was recorded for this scan.", fraction
    if fraction is None:
        return "INCONCLUSIVE", "Cloud-mask coverage was not recorded for this scan.", fraction
    return "REVIEW REQUIRED", "Automated surface-change signal; verify site boundaries and field conditions.", fraction


def _draw_wrapped(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    max_width: float,
    leading: float,
    color: Any = INK,
    font: str = "Helvetica",
    size: float = 8.5,
) -> float:
    pdf.setFillColor(color)
    pdf.setFont(font, size)
    line = ""
    for word in _clean_text(text).split():
        candidate = f"{line} {word}".strip()
        if pdf.stringWidth(candidate, font, size) > max_width and line:
            pdf.drawString(x, y, line)
            y -= leading
            line = word
        else:
            line = candidate
    if line:
        pdf.drawString(x, y, line)
        y -= leading
    return y


def _draw_image_panel(
    pdf: canvas.Canvas,
    image_data: io.BytesIO | None,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    caption: str,
) -> None:
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(x, y + height + 18, title)
    pdf.setFillColor(PALE)
    pdf.roundRect(x, y, width, height + 10, 4, fill=1, stroke=0)
    if image_data is None:
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 8)
        pdf.drawCentredString(x + width / 2, y + (height + 10) / 2, "Evidence preview unavailable")
    else:
        pdf.drawImage(
            ImageReader(image_data),
            x + 3,
            y + 3,
            width=width - 6,
            height=height + 4,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(x, y - 12, _clean_text(caption)[:100])


def build_pdf_report(
    scan: dict[str, Any],
    findings: list[dict[str, Any]],
    *,
    template: ReportTemplate,
    brand_name: str,
    finding_id: str | None = None,
    media_dir: Path = MEDIA_DIR,
) -> bytes:
    source = _json_mapping(scan.get("source_metadata"), "source metadata")
    processing = _json_mapping(scan.get("processing_metadata"), "processing metadata")
    summary = _json_mapping(scan.get("summary"), "summary")

    selected = None
    if finding_id:
        selected = next((item for item in findings if _finding_id(item) == finding_id), None)
        if selected is None:
            raise HTTPException(status_code=404, detail="Finding not found in this scan.")
    elif findings:
        selected = findings[0]

    source_name = _clean_text(
        source.get("siteName") or scan.get("region_name") or scan.get("region_id"),
        "Monitoring site",
    )
    historical_path, recent_path = _capture_images(source, media_dir)

    before_crop = _make_crop(historical_path, selected, source)
    after_crop = _make_crop(recent_path, selected, source)
    has_images = before_crop is not None and after_crop is not None
    status, status_reason, cloud_fraction = _cloud_status(
        scan,
        source,
        processing,
        has_images,
        selected,
    )

    is_compliance = template == "quarry-compliance"
    title = (
        "QUARRY LEASE / EIA COMPLIANCE REVIEW"
        if is_compliance
        else "LANDOWNER / ENCROACHMENT EVIDENCE NOTE"
    )
    assessment = (
        "Screening signal for comparison with the applicable lease boundary, approved plans, and EIA conditions."
        if is_compliance
        else "Preliminary surface-change signal near the monitored property; confirm cadastral limits and field evidence."
    )
    caution = (
        "Not a formal EIA, lease-compliance finding, boundary survey, or legal determination."
        if is_compliance
        else "Not proof of encroachment, ownership, or a legal boundary. Obtain a qualified survey and field verification."
    )
    brand = _clean_text(brand_name, "GeoSentinel AI")[:80]
    client = source_name
    scan_id = _clean_text(scan.get("scan_id"), "Unknown scan")
    historical_date = _clean_text(scan.get("historical_date") or "Historical observation")
    recent_date = _clean_text(scan.get("recent_date") or "Recent observation")
    area = _finite_number(_value(selected, "area_sqm", "areaSqm"))
    if area is None:
        area = _finite_number(summary.get("changedAreaSqm")) or 0
    confidence = _finite_number(_value(selected, "confidence")) or 0
    coordinates = [
        _finite_number(_value(selected, "latitude")),
        _finite_number(_value(selected, "longitude")),
    ]
    google_url = None
    if coordinates[0] is not None and coordinates[1] is not None:
        google_url = (
            "https://www.google.com/maps/@?api=1&map_action=map"
            f"&center={coordinates[0]:.6f},{coordinates[1]:.6f}&zoom=17&basemap=satellite"
        )

    resolution = _finite_number(source.get("resolutionMeters"))
    is_sentinel = source.get("assetType") == "Native Sentinel-2 L2A COG" and resolution is not None
    historical_caption = (
        f"{historical_date} | {resolution:g} m/pixel"
        if is_sentinel
        else f"{historical_date} | uploaded imagery; pixel scale unverified"
    )
    recent_caption = (
        f"{recent_date} | {resolution:g} m/pixel"
        if is_sentinel
        else f"{recent_date} | uploaded imagery; pixel scale unverified"
    )

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
    pdf.setTitle(f"{title} - {scan_id}")
    pdf.setAuthor(brand)
    pdf.setSubject("Automated satellite surface-change screening report")

    header_height = 88
    pdf.setFillColor(INK)
    pdf.rect(0, PAGE_HEIGHT - header_height, PAGE_WIDTH, header_height, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#a8c94b"))
    pdf.circle(MARGIN + 8, PAGE_HEIGHT - 32, 7, fill=1, stroke=0)
    pdf.setStrokeColor(INK)
    pdf.setLineWidth(1.3)
    pdf.line(MARGIN + 4, PAGE_HEIGHT - 32, MARGIN + 12, PAGE_HEIGHT - 32)
    pdf.line(MARGIN + 8, PAGE_HEIGHT - 36, MARGIN + 8, PAGE_HEIGHT - 28)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(MARGIN + 22, PAGE_HEIGHT - 36, brand)
    pdf.setFont("Helvetica", 7)
    pdf.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 35, "SATELLITE CHANGE SCREENING")
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(MARGIN, PAGE_HEIGHT - 62, title)

    y = PAGE_HEIGHT - header_height - 25
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(MARGIN, y, f"SITE / CLIENT   {client[:64]}")
    pdf.drawRightString(PAGE_WIDTH - MARGIN, y, f"REPORT   {scan_id[:42]}")
    y -= 28

    card_gap = 8
    card_width = (PAGE_WIDTH - 2 * MARGIN - 3 * card_gap) / 4
    cards = [
        ("OBSERVATION WINDOW", f"{historical_date[:10]} to {recent_date[:10]}"),
        ("CHANGED AREA", f"{area:,.0f} m2  |  {area / 10000:.2f} ha"),
        ("MODEL CONFIDENCE", f"{confidence:.0%}" if selected else "No finding"),
        ("CLOUD MASK", f"{cloud_fraction:.0%}" if cloud_fraction is not None else "Unknown"),
    ]
    for index, (label, value) in enumerate(cards):
        x = MARGIN + index * (card_width + card_gap)
        pdf.setFillColor(PALE)
        pdf.roundRect(x, y - 33, card_width, 42, 4, fill=1, stroke=0)
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica-Bold", 6)
        pdf.drawString(x + 7, y - 3, label)
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica", 7.5)
        pdf.drawString(x + 7, y - 19, value[:40])

    y -= 82
    status_color = AMBER if status in {"CLOUDY / INCONCLUSIVE", "INCONCLUSIVE"} else GREEN
    if status == "REVIEW REQUIRED":
        status_color = RED
    pdf.setFillColor(status_color)
    pdf.roundRect(MARGIN, y - 23, PAGE_WIDTH - 2 * MARGIN, 30, 4, fill=1, stroke=0)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(MARGIN + 10, y - 4, status)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(MARGIN + 10, y - 16, status_reason[:125])

    y -= 174
    panel_gap = 14
    panel_width = (PAGE_WIDTH - 2 * MARGIN - panel_gap) / 2
    panel_height = 112
    _draw_image_panel(
        pdf,
        before_crop,
        MARGIN,
        y,
        panel_width,
        panel_height,
        "BEFORE",
        historical_caption,
    )
    _draw_image_panel(
        pdf,
        after_crop,
        MARGIN + panel_width + panel_gap,
        y,
        panel_width,
        panel_height,
        "AFTER",
        recent_caption,
    )
    legend_y = y - 28
    pdf.setFillColor(HexColor("#f06454"))
    pdf.circle(MARGIN + 3, legend_y + 2, 3, fill=1, stroke=0)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(MARGIN + 10, legend_y, "Detected change extent")
    if source.get("geometry"):
        pdf.setFillColor(HexColor("#a5cb45"))
        pdf.circle(MARGIN + 145, legend_y + 2, 3, fill=1, stroke=0)
        pdf.setFillColor(MUTED)
        pdf.drawString(MARGIN + 152, legend_y, "Monitoring-site boundary")

    section_y = legend_y - 23
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(MARGIN, section_y, "OBSERVATION")
    pdf.setStrokeColor(PALE)
    pdf.line(MARGIN, section_y - 5, PAGE_WIDTH - MARGIN, section_y - 5)

    details_y = section_y - 22
    finding_label = _clean_text(_value(selected, "label", "change_type", "changeType"), "No finding")
    area_name = _clean_text(_value(selected, "areaName", "area_name"), client)
    detail_text = f"{finding_label} | {area_name}"
    details_y = _draw_wrapped(pdf, detail_text, MARGIN, details_y, PAGE_WIDTH - 2 * MARGIN, 11, size=8)

    if coordinates[0] is not None and coordinates[1] is not None:
        coordinates_text = f"Coordinates: {coordinates[0]:.6f}, {coordinates[1]:.6f}"
    else:
        coordinates_text = "Coordinates: scan-level summary"
    details_y = _draw_wrapped(
        pdf,
        coordinates_text,
        MARGIN,
        details_y - 1,
        PAGE_WIDTH - 2 * MARGIN,
        11,
        color=MUTED,
        size=7.5,
    )
    details_y = _draw_wrapped(
        pdf,
        assessment,
        MARGIN,
        details_y - 1,
        PAGE_WIDTH - 2 * MARGIN,
        11,
        size=7.5,
    )

    if google_url:
        pdf.setFillColor(GREEN)
        pdf.setFont("Helvetica-Bold", 7.5)
        link_y = details_y - 2
        pdf.drawString(MARGIN, link_y, "OPEN GOOGLE SATELLITE VIEW")
        link_width = pdf.stringWidth("OPEN GOOGLE SATELLITE VIEW", "Helvetica-Bold", 7.5)
        pdf.linkURL(google_url, (MARGIN, link_y - 2, MARGIN + link_width, link_y + 9), relative=0)

    footer_y = 40
    pdf.setStrokeColor(PALE)
    pdf.line(MARGIN, footer_y + 16, PAGE_WIDTH - MARGIN, footer_y + 16)
    _draw_wrapped(pdf, caution, MARGIN, footer_y + 4, PAGE_WIDTH - 2 * MARGIN, 9, MUTED, size=6.5)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 6)
    pdf.drawRightString(PAGE_WIDTH - MARGIN, 20, "CONFIDENTIAL SCREENING OUTPUT")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


@router.get("/{scan_id}/report.pdf")
def download_scan_report(
    scan_id: str,
    template: ReportTemplate = Query(default="quarry-compliance"),
    brand_name: str = Query(default="GeoSentinel AI", min_length=1, max_length=80),
    finding_id: str | None = Query(default=None, max_length=120),
) -> Response:
    try:
        scan, findings = _load_scan_report_data(scan_id)
        pdf_bytes = build_pdf_report(
            scan,
            findings,
            template=template,
            brand_name=brand_name,
            finding_id=finding_id,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        logger.exception("Stored scan data could not be used to build a report for %s", scan_id)
        raise HTTPException(status_code=500, detail="Stored scan report data is invalid.") from exc
    except Exception as exc:
        logger.exception("Failed to generate PDF report for scan %s", scan_id)
        raise HTTPException(status_code=503, detail="Scan report storage or PDF generation is unavailable.") from exc

    safe_scan_id = re.sub(r"[^A-Za-z0-9_-]", "-", scan_id)[:80] or "scan"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="GeoSentinel-{safe_scan_id}-{template}.pdf"',
        },
    )


@router.get("/{scan_id}/images/{image_kind}")
def download_scan_image(scan_id: str, image_kind: Literal["historical", "recent"]) -> Response:
    try:
        scan, _ = _load_scan_record(scan_id)
        source = _json_mapping(scan.get("source_metadata"), "source metadata")
        asset_uri = source.get(f"{image_kind}ImageAssetUri")
        if isinstance(asset_uri, str) and asset_uri:
            image_bytes = read_evidence_bytes(asset_uri)
        else:
            historical, recent = _capture_images(source)
            image = historical if image_kind == "historical" else recent
            if image is None:
                raise HTTPException(status_code=404, detail="Scan image is unavailable.")
            image_bytes = image.read_bytes() if isinstance(image, Path) else image.getvalue()
        return Response(
            content=image_bytes,
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=3600"},
        )
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Scan image is unavailable.") from exc
    except Exception as exc:
        logger.exception("Failed to retrieve %s image for scan %s", image_kind, scan_id)
        raise HTTPException(status_code=503, detail="Scan image storage is unavailable.") from exc
