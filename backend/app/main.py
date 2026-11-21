from __future__ import annotations

import io
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import numpy as np
import torch
from dotenv import load_dotenv
from fastapi import FastAPI, File, Header, HTTPException, Response, UploadFile
from fastapi import Request as FastAPIRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image

from .api.findings import router as findings_router
from .api.graph import router as graph_router

# Import sub-routers
from .api.health import router as health_router
from .api.investigations import router as investigations_router
from .api.pdf_reports import router as pdf_reports_router
from .api.scans import router as scans_router
from .api.sites import router as sites_router
from .change_model import load_model
from .db.neo4j import get_driver, neo4j_lifespan
from .history import save_scan
from .geometry import geometry_bbox, normalize_polygon_geometry
from .model_config import MODEL_BANDS, MODEL_INPUT_CHANNELS
from .repositories import region_repository
from .services.detection_service import (
    validate_coordinates,
    validate_image_pair,
    validate_pixel_size,
)
from .services.evidence_service import get_default_storage
from .services.persistence_service import persist_scan
from .satellite_cog import (
    RasterGrid,
    Sentinel2Raster,
    create_target_grid,
    pixel_bounds_wgs84,
    pixel_center_wgs84,
    read_sentinel2_scene,
    rgb_preview,
)
from .spectral import SpectralChange, compare_spectral_scenes

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(
    title="GeoSentinel AI API",
    version="0.2.0",
    lifespan=neo4j_lifespan,
)


def _cors_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS", "")
    origins = {
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    }
    origins.update(origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip())
    return sorted(origins)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_correlation_id(request: FastAPIRequest, call_next):
    correlation_id = request.headers.get("X-Request-ID") or str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = correlation_id
    return response


# Include modular routers
app.include_router(health_router)
app.include_router(scans_router)
app.include_router(findings_router)
app.include_router(investigations_router)
app.include_router(graph_router)
app.include_router(sites_router)
app.include_router(pdf_reports_router)

MEDIA_DIR = Path(__file__).resolve().parents[1] / "data" / "live"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = MEDIA_DIR / "last-result.json"
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")
STATIC_BBOX = (73.82, 18.48, 73.90, 18.56)
MAX_TIMELINE_SCENES = 8
SENTINEL_REVISIT_DAYS = 5
MAX_SITE_GRID_PIXELS = 4_000_000
LIVE_SCAN_INTERVAL_MINUTES = 30
LIVE_SCAN_CACHE_TTL_SECONDS = LIVE_SCAN_INTERVAL_MINUTES * 60
LIVE_SCAN_LOCK = threading.Lock()
_LAST_LIVE_SCAN_ATTEMPT: float | None = None

MODEL_PATH = str(Path(__file__).resolve().parents[1] / "models" / "change_cnn.pt")
CHANGE_MODEL = load_model(MODEL_PATH)
TRAINING_STATE: dict[str, Any] = {"status": "idle", "message": "Training has not been started."}
TRAINING_LOCK = threading.Lock()


@app.get("/api/model")
def model_status() -> dict[str, Any]:
    metrics_path = Path(MODEL_PATH).with_name("metrics.json")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    return {
        "loaded": CHANGE_MODEL is not None,
        "inputChannels": CHANGE_MODEL.input_channels if CHANGE_MODEL is not None else None,
        "metrics": metrics,
    }


def _run_training() -> None:
    global CHANGE_MODEL
    try:
        process = subprocess.run(
            [sys.executable, "train_model.py"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        with TRAINING_LOCK:
            if process.returncode == 0:
                trained_model = load_model(MODEL_PATH)
                if trained_model is None or trained_model.input_channels != MODEL_INPUT_CHANNELS:
                    TRAINING_STATE.update({
                        "status": "failed",
                        "message": "Training completed but the 10-channel model could not be loaded.",
                        "output": process.stdout[-2000:],
                    })
                else:
                    CHANGE_MODEL = trained_model
                    TRAINING_STATE.update({
                        "status": "completed",
                        "message": "OSCD 10-channel CNN training completed and the model was reloaded.",
                        "output": process.stdout[-2000:],
                    })
            else:
                TRAINING_STATE.update({
                    "status": "failed",
                    "message": "OSCD CNN training failed. Check the prepared dataset and backend output for details.",
                    "output": (process.stdout + process.stderr)[-2000:],
                })
    except (OSError, ValueError) as exc:
        with TRAINING_LOCK:
            TRAINING_STATE.update({"status": "failed", "message": f"Could not start CNN training: {exc}"})


@app.get("/api/train")
def training_status() -> dict[str, Any]:
    with TRAINING_LOCK:
        return dict(TRAINING_STATE)


@app.post("/api/train")
def train_model() -> dict[str, Any]:
    if os.getenv("TRAINING_ENABLED", "").lower() != "true":
        raise HTTPException(status_code=403, detail="CNN training is disabled. Set TRAINING_ENABLED=true to enable it.")
    oscd_data_dir = Path(__file__).resolve().parents[1] / "data" / "oscd"
    if not (oscd_data_dir / "train").is_dir() or not (oscd_data_dir / "validation").is_dir():
        raise HTTPException(
            status_code=400,
            detail=(
                "Prepared OSCD patches are missing. Run prepare_oscd.py with the extracted "
                "OSCD Images and Train Labels directories before training."
            ),
        )
    with TRAINING_LOCK:
        if TRAINING_STATE["status"] == "running":
            return dict(TRAINING_STATE)
        TRAINING_STATE.clear()
        TRAINING_STATE.update({"status": "running", "message": "OSCD CNN training is running."})
    threading.Thread(target=_run_training, daemon=True).start()
    return dict(TRAINING_STATE)


def _components(mask: np.ndarray, min_pixels: int = 20) -> list[tuple[int, int, int, int, int]]:
    """Return connected components as (x, y, width, height, pixel_count)."""
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    results: list[tuple[int, int, int, int, int]] = []
    for y in range(height):
        for x in range(width):
            if not mask[y, x] or visited[y, x]:
                continue
            stack = [(x, y)]
            visited[y, x] = True
            points: list[tuple[int, int]] = []
            while stack:
                px, py = stack.pop()
                points.append((px, py))
                for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
                    if 0 <= nx < width and 0 <= ny < height and mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((nx, ny))
            if len(points) >= min_pixels:
                xs = [point[0] for point in points]
                ys = [point[1] for point in points]
                results.append((min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1, len(points)))
    return sorted(results, key=lambda item: item[4], reverse=True)


def _analyse_pair(
    old_image: np.ndarray,
    new_image: np.ndarray,
    latitude: float,
    longitude: float,
    pixel_size_m: float,
    mode: str,
    historical_date: str,
    recent_date: str,
    *,
    spectral_change: SpectralChange | None = None,
    spectral_model_input: np.ndarray | None = None,
    raster_grid: RasterGrid | None = None,
    alignment_shift: tuple[float, float] | None = None,
) -> dict[str, Any]:
    new_image = _normalize_season(new_image, old_image)
    if alignment_shift is None:
        aligned_image, shift = _align_image(old_image, new_image)
    else:
        shift_x, shift_y = (int(round(alignment_shift[0])), int(round(alignment_shift[1])))
        aligned_image = np.roll(new_image, (shift_y, shift_x), axis=(0, 1))
        shift = alignment_shift
    if spectral_change is None:
        cloud_mask = _cloud_mask(old_image) | _cloud_mask(aligned_image)
        difference = np.mean(np.abs(aligned_image - old_image), axis=2)
        threshold = max(25.0, float(np.percentile(difference, 90)))
        mask = (difference >= threshold) & ~cloud_mask
    else:
        cloud_mask = spectral_change.cloud_mask
        difference = spectral_change.score
        threshold = spectral_change.threshold
        mask = spectral_change.mask & ~cloud_mask
    components = _components(mask)
    findings = []
    height, width = mask.shape
    for index, (x, y, component_width, component_height, pixels) in enumerate(components[:10], start=1):
        area_sqm = round(pixels * pixel_size_m * pixel_size_m)
        if raster_grid is None:
            center_lat = latitude + ((y + component_height / 2) / height - 0.5) * 0.08
            center_lon = longitude + ((x + component_width / 2) / width - 0.5) * 0.08
            region_bbox = [
                round(latitude + (y / height - 0.5) * 0.08, 6),
                round(longitude + (x / width - 0.5) * 0.08, 6),
                round(latitude + ((y + component_height) / height - 0.5) * 0.08, 6),
                round(longitude + ((x + component_width) / width - 0.5) * 0.08, 6),
            ]
        else:
            center_lat, center_lon = pixel_center_wgs84(
                raster_grid,
                x + component_width / 2,
                y + component_height / 2,
            )
            region_bbox = pixel_bounds_wgs84(raster_grid, x, y, component_width, component_height)
        component_signal = difference[y : y + component_height, x : x + component_width].mean()
        confidence_scale = 0.25 if spectral_change is not None else 1 / 255
        confidence = min(0.98, 0.65 + float(component_signal) * confidence_scale)
        model_score = None
        if CHANGE_MODEL is not None and width >= 32 and height >= 32:
            patch_x = max(0, min(width - 32, x + component_width // 2 - 16))
            patch_y = max(0, min(height - 32, y + component_height // 2 - 16))
            model_patch = None
            if CHANGE_MODEL.input_channels == MODEL_INPUT_CHANNELS and spectral_model_input is not None:
                model_patch = spectral_model_input[:, patch_y : patch_y + 32, patch_x : patch_x + 32]
            elif CHANGE_MODEL.input_channels == 6:
                model_patch = np.concatenate(
                    [old_image[patch_y : patch_y + 32, patch_x : patch_x + 32],
                     aligned_image[patch_y : patch_y + 32, patch_x : patch_x + 32]],
                    axis=2,
                ).transpose(2, 0, 1) / 255
            if model_patch is not None and model_patch.shape == (CHANGE_MODEL.input_channels, 32, 32):
                model_patch = np.nan_to_num(model_patch, nan=0.0, posinf=0.0, neginf=0.0)
                with torch.no_grad():
                    model_score = float(
                        torch.sigmoid(
                            CHANGE_MODEL(torch.from_numpy(model_patch.astype(np.float32))[None])
                        )[0]
                    )
                confidence = round((confidence + model_score) / 2, 3)
        if spectral_change is None:
            change_type = "Spectral surface change"
        else:
            component_ndvi_loss = spectral_change.ndvi_loss[
                y : y + component_height, x : x + component_width
            ].mean()
            component_bsi_gain = spectral_change.bsi_gain[
                y : y + component_height, x : x + component_width
            ].mean()
            change_type = "Vegetation loss" if component_ndvi_loss >= component_bsi_gain else "Bare-soil exposure"
        detection_error_sqm = max(
            round(pixel_size_m * pixel_size_m),
            round(area_sqm * min(0.35, 1 - confidence)),
        )
        google_query = f"{center_lat:.6f},{center_lon:.6f}"
        findings.append(
            {
                "id": f"GS-{mode.upper()}-{index:03d}",
                "label": f"Detected change {index}",
                "severity": "high" if area_sqm >= 10000 else "medium" if area_sqm >= 3000 else "low",
                "confidence": round(float(confidence), 2),
                "areaSqm": area_sqm,
                "coordinates": [round(center_lat, 6), round(center_lon, 6)],
                "regionBbox": region_bbox,
                "detectionErrorSqm": detection_error_sqm,
                "googleMapsUrl": f"https://www.google.com/maps/search/?api=1&query={google_query}",
                "googleSatelliteUrl": (
                    "https://www.google.com/maps/@?api=1&map_action=map"
                    f"&center={google_query}&zoom=17&basemap=satellite"
                ),
                "changeType": change_type,
                "firstObserved": historical_date,
                "lastObserved": recent_date,
                "status": "Needs review",
                "modelScore": model_score,
            }
        )
    total_area = sum(item["areaSqm"] for item in findings)
    processing = {
        "threshold": round(threshold, 4 if spectral_change is not None else 2),
        "components": len(findings),
        "model": "ChangeCNN" if CHANGE_MODEL else "difference-fallback",
        "modelInputChannels": CHANGE_MODEL.input_channels if CHANGE_MODEL is not None else None,
        "modelAppliedToFindings": sum(item["modelScore"] is not None for item in findings),
        "cloudMaskPixels": int(cloud_mask.sum()),
        "cloudMaskFraction": round(float(cloud_mask.mean()), 4),
        "gridPixelCount": int(mask.size),
        "alignmentShiftPixels": [round(shift[0], 3), round(shift[1], 3)],
        "seasonalNormalization": "per-channel percentile matching",
    }
    if spectral_change is not None:
        processing.update({
            "reflectanceBands": ["B02", "B03", "B04", "B08", "B11"],
            "spectralIndices": ["NDVI", "BSI"],
            "changeSignal": "NDVI loss or BSI gain",
        })
    if (
        CHANGE_MODEL is not None
        and CHANGE_MODEL.input_channels == MODEL_INPUT_CHANNELS
        and spectral_model_input is None
    ):
        processing["modelNote"] = "The 10-channel model is skipped for RGB-only image uploads."
    return {
        "mode": mode,
        "region": "Pune quarry belt",
        "historicalDate": historical_date,
        "recentDate": recent_date,
        "findings": findings,
        "summary": {
            "changedAreaSqm": total_area,
            "changedAreaHa": round(total_area / 10000, 2),
            "highRiskCount": sum(item["severity"] == "high" for item in findings),
            "averageConfidence": round(sum(item["confidence"] for item in findings) / len(findings), 2)
            if findings else 0,
        },
        "timeline": [
            {"month": historical_date, "areaSqm": 0},
            {"month": recent_date, "areaSqm": total_area},
        ],
        "areaBreakdown": [
            {"label": item["label"], "areaSqm": item["areaSqm"], "severity": item["severity"]}
            for item in findings
        ],
        "timelineNote": (
            "Two-date trajectory: the historical scene is the baseline and the recent scene "
            "contains the measured changed area. Additional scenes are required for a multi-point trend."
        ),
        "processing": processing,
    }


def _cloud_mask(image: np.ndarray) -> np.ndarray:
    brightness = image.mean(axis=2)
    spread = image.max(axis=2) - image.min(axis=2)
    return (brightness > 220) & (spread < 35)


def _normalize_season(new_image: np.ndarray, old_image: np.ndarray) -> np.ndarray:
    normalized = new_image.copy()
    for channel in range(3):
        old_low, old_high = np.percentile(old_image[:, :, channel], [5, 95])
        new_low, new_high = np.percentile(new_image[:, :, channel], [5, 95])
        scale = (old_high - old_low) / max(new_high - new_low, 1)
        normalized[:, :, channel] = np.clip(
            (new_image[:, :, channel] - new_low) * scale + old_low, 0, 255
        )
    return normalized


def _align_image(reference: np.ndarray, moving: np.ndarray) -> tuple[np.ndarray, tuple[float, float]]:
    reference_gray = reference.mean(axis=2) - reference.mean()
    moving_gray = moving.mean(axis=2) - moving.mean()
    reference_fft = np.fft.fft2(reference_gray)
    moving_fft = np.fft.fft2(moving_gray)
    correlation = np.fft.ifft2(reference_fft * np.conj(moving_fft))
    peak_y, peak_x = np.unravel_index(np.argmax(np.abs(correlation)), correlation.shape)
    height, width = reference_gray.shape
    shift_y = float(peak_y if peak_y <= height // 2 else peak_y - height)
    shift_x = float(peak_x if peak_x <= width // 2 else peak_x - width)
    aligned = np.roll(moving, (int(round(shift_y)), int(round(shift_x))), axis=(0, 1))
    return aligned, (shift_x, shift_y)


def _read_live_cache(cache_file: Path = CACHE_FILE) -> dict[str, Any] | None:
    if not cache_file.exists():
        return None
    try:
        cache_age_seconds = max(0, int(time.time() - cache_file.stat().st_mtime))
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        cached["source"]["stale"] = True
        cached["source"]["cacheAgeSeconds"] = cache_age_seconds
        cached["source"]["monitoringIntervalMinutes"] = LIVE_SCAN_INTERVAL_MINUTES
        cached["source"]["note"] = (
            "Provider rate limit reached. Showing the most recent successfully downloaded "
            "real Sentinel-2 scan; run again later for a fresh acquisition."
        )
        return cached
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _read_recent_live_cache(
    cache_file: Path = CACHE_FILE,
    *,
    now: float | None = None,
) -> dict[str, Any] | None:
    try:
        age_seconds = (time.time() if now is None else now) - cache_file.stat().st_mtime
    except OSError:
        return None
    if age_seconds < 0 or age_seconds >= LIVE_SCAN_CACHE_TTL_SECONDS:
        return None

    cached = _read_live_cache(cache_file)
    if cached is not None:
        age_minutes = int(age_seconds // 60)
        cached["source"]["cacheAgeSeconds"] = int(age_seconds)
        cached["source"]["note"] = (
            f"Reusing a real satellite scan from {age_minutes} minutes ago. "
            f"Automatic refresh is limited to once every {LIVE_SCAN_INTERVAL_MINUTES} minutes."
        )
    return cached


def _run_live_detect_request(
    idempotency_key: str | None,
    *,
    allow_recent_cache: bool,
) -> dict[str, Any]:
    global _LAST_LIVE_SCAN_ATTEMPT

    with LIVE_SCAN_LOCK:
        if allow_recent_cache and idempotency_key is None:
            cached = _read_recent_live_cache()
            if cached is not None:
                return cached

            if _LAST_LIVE_SCAN_ATTEMPT is not None:
                now = time.monotonic()
                remaining = LIVE_SCAN_CACHE_TTL_SECONDS - (now - _LAST_LIVE_SCAN_ATTEMPT)
                if remaining > 0:
                    cached = _read_live_cache()
                    if cached is not None:
                        cached["source"]["note"] = (
                            "A satellite refresh was attempted recently. Showing the last real scan "
                            f"until the {LIVE_SCAN_INTERVAL_MINUTES}-minute refresh window ends."
                        )
                        return cached
                    raise HTTPException(
                        status_code=429,
                        detail="Satellite data was requested recently. Retry after the 30-minute refresh window.",
                        headers={"Retry-After": str(max(1, int(remaining)))},
                    )

        try:
            return _execute_live_detect(idempotency_key=idempotency_key)
        finally:
            _LAST_LIVE_SCAN_ATTEMPT = time.monotonic()


def _live_scenes(
    bbox: tuple[float, float, float, float] = STATIC_BBOX,
) -> list[dict[str, Any]]:
    payload = json.dumps({
        "collections": ["sentinel-2-l2a"],
        "bbox": list(bbox),
        "datetime": "2025-01-01T00:00:00Z/2026-12-31T23:59:59Z",
        "limit": 100,
        "query": {"eo:cloud_cover": {"lt": 20}},
    }).encode()
    request = Request(
        "https://planetarycomputer.microsoft.com/api/stac/v1/search",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "GeoSentinel-MVP/1.0"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        features = json.loads(response.read()).get("features", [])
    scenes = sorted(features, key=lambda item: item["properties"]["datetime"])
    if len(scenes) < 2:
        raise HTTPException(status_code=502, detail="The public Sentinel-2 catalog returned fewer than two scenes.")
    return scenes[-MAX_TIMELINE_SCENES:]


def _area_name(latitude: float, longitude: float) -> str:
    fallback = f"Pune monitoring area ({latitude:.5f}, {longitude:.5f})"
    try:
        url = (
            "https://nominatim.openstreetmap.org/reverse?format=jsonv2"
            f"&lat={latitude:.6f}&lon={longitude:.6f}&zoom=14&addressdetails=1"
        )
        response = json.loads(
            urlopen(
                Request(url, headers={"User-Agent": "GeoSentinel-MVP/1.0 contact=hackathon"}),
                timeout=10,
            ).read()
        )
        address = response.get("address", {})
        return (
            address.get("suburb")
            or address.get("neighbourhood")
            or address.get("village")
            or address.get("town")
            or address.get("city")
            or fallback
        )
    except (OSError, ValueError, KeyError):
        return fallback


def _add_area_names(findings: list[dict[str, Any]]) -> None:
    for finding in findings:
        latitude, longitude = finding["coordinates"]
        finding["areaName"] = _area_name(latitude, longitude)


def _analyse_scene_pair(
    historical: Sentinel2Raster,
    recent: Sentinel2Raster,
    historical_date: str,
    recent_date: str,
    mode: str,
    bbox: tuple[float, float, float, float] = STATIC_BBOX,
) -> dict[str, Any]:
    old_image = rgb_preview(historical.bands).astype(np.float32)
    new_image = rgb_preview(recent.bands).astype(np.float32)
    _, shift = _align_image(old_image, new_image)
    spectral_change = compare_spectral_scenes(
        historical.bands,
        recent.bands,
        historical.scl,
        recent.scl,
        shift,
    )
    shift_y, shift_x = int(round(shift[1])), int(round(shift[0]))
    historical_channels = np.stack([historical.bands[name] for name in MODEL_BANDS])
    recent_channels = np.stack([
        np.roll(recent.bands[name], (shift_y, shift_x), axis=(0, 1))
        for name in MODEL_BANDS
    ])
    spectral_model_input = np.nan_to_num(
        np.clip(np.concatenate([historical_channels, recent_channels], axis=0), 0, 1),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    ).astype(np.float32)
    return _analyse_pair(
        old_image,
        new_image,
        (bbox[1] + bbox[3]) / 2,
        (bbox[0] + bbox[2]) / 2,
        recent.grid.resolution_m,
        mode,
        historical_date,
        recent_date,
        spectral_change=spectral_change,
        spectral_model_input=spectral_model_input,
        raster_grid=recent.grid,
        alignment_shift=shift,
    )


def _persist_scan_images(
    source: dict[str, Any],
    historical_path: Path,
    recent_path: Path,
) -> None:
    storage = get_default_storage()
    for kind, image_path in (
        ("historical", historical_path),
        ("recent", recent_path),
    ):
        uri, sha256, file_size = storage.store_bytes(image_path.read_bytes(), image_path.name)
        source[f"{kind}ImageAssetUri"] = uri
        source[f"{kind}ImageSha256"] = sha256
        source[f"{kind}ImageFileSize"] = file_size


def _set_scan_image_urls(source: dict[str, Any], scan_id: str) -> None:
    for kind in ("historical", "recent"):
        source[f"{kind}Image"] = f"/api/scans/{scan_id}/images/{kind}"


def _execute_live_detect(
    idempotency_key: str | None = None,
    *,
    bbox: tuple[float, float, float, float] = STATIC_BBOX,
    geometry: dict[str, Any] | None = None,
    region_name: str = "Pune quarry belt",
    region_id: str | None = None,
) -> dict[str, Any]:
    """Internal implementation of live detection."""
    cache_file = CACHE_FILE if region_id is None else MEDIA_DIR / f"last-result-{region_id}.json"
    image_capture_id = uuid4().hex
    try:
        grid = create_target_grid(bbox, resolution_m=10)
        if grid.width * grid.height > MAX_SITE_GRID_PIXELS:
            raise HTTPException(
                status_code=413,
                detail=f"Monitoring area exceeds the {MAX_SITE_GRID_PIXELS:,}-pixel scan limit.",
            )
        scenes = _live_scenes(bbox)
        first_raster = None
        previous_raster = None
        previous_scene = None
        timeline = []
        for scene in scenes:
            current_raster = read_sentinel2_scene(scene, bbox, grid, geometry)
            if first_raster is None:
                first_raster = current_raster
            if previous_raster is not None and previous_scene is not None:
                pair_result = _analyse_scene_pair(
                    previous_raster,
                    current_raster,
                    previous_scene["properties"]["datetime"][:10],
                    scene["properties"]["datetime"][:10],
                    "timeline",
                    bbox,
                )
                timeline.append({
                    "month": scene["properties"]["datetime"][:10],
                    "areaSqm": pair_result["summary"]["changedAreaSqm"],
                })
            previous_raster = current_raster
            previous_scene = scene

        if first_raster is None or previous_raster is None:
            raise RuntimeError("The Sentinel-2 catalog returned no readable scenes.")
        historical, recent = scenes[0], scenes[-1]
        old_image = rgb_preview(first_raster.bands)
        new_image = rgb_preview(previous_raster.bands)
        historical_path = MEDIA_DIR / f"historical-{image_capture_id}.png"
        recent_path = MEDIA_DIR / f"recent-{image_capture_id}.png"
        Image.fromarray(old_image).save(historical_path, format="PNG")
        Image.fromarray(new_image).save(recent_path, format="PNG")
        result = _analyse_scene_pair(
            first_raster,
            previous_raster,
            historical["properties"]["datetime"][:10],
            recent["properties"]["datetime"][:10],
            "live-sentinel2",
            bbox,
        )
        _add_area_names(result["findings"])
        result["timeline"] = [{"month": historical["properties"]["datetime"][:10], "areaSqm": 0}] + timeline
        result["timelineNote"] = (
            f"Multi-scene trajectory from up to {MAX_TIMELINE_SCENES} newest low-cloud observations. "
            f"Sentinel-2 revisits this area approximately every {SENTINEL_REVISIT_DAYS} days; "
            "actual timeline dates are shown because cloudy scenes are skipped."
        )
        result["source"] = {
            "provider": "Microsoft Planetary Computer / Copernicus Sentinel-2 L2A",
            "bbox": list(bbox),
            "historicalItem": historical["id"],
            "recentItem": recent["id"],
            "historicalCloudCover": historical["properties"].get("eo:cloud_cover"),
            "recentCloudCover": recent["properties"].get("eo:cloud_cover"),
            "assetType": "Native Sentinel-2 L2A COG",
            "bands": ["B02", "B03", "B04", "B08", "B11", "SCL"],
            "resolutionMeters": grid.resolution_m,
            "grid": {
                "crs": grid.crs,
                "transform": list(grid.transform)[:6],
                "width": grid.width,
                "height": grid.height,
            },
            "imageCaptureId": image_capture_id,
            "historicalImage": f"/media/historical-{image_capture_id}.png",
            "recentImage": f"/media/recent-{image_capture_id}.png",
            "siteName": region_name,
            "sceneCount": len(scenes),
            "sceneCadenceDays": SENTINEL_REVISIT_DAYS,
            "monitoringIntervalMinutes": LIVE_SCAN_INTERVAL_MINUTES,
            "sceneDates": [scene["properties"]["datetime"][:10] for scene in scenes],
            "note": "Public satellite imagery; detections are intelligence signals, not legal determinations.",
        }
        if geometry is not None:
            result["region"] = region_name
            result["regionId"] = region_id
            result["source"]["geometry"] = geometry
        _persist_scan_images(result["source"], historical_path, recent_path)

        # Persist to Neo4j (and CSV fallback)
        try:
            scan_id = persist_scan(
                get_driver(),
                result,
                result["source"],
                "live-sentinel2",
                idempotency_key=idempotency_key,
            )
            result["scanId"] = scan_id
        except Exception as exc:
            logger.warning("Neo4j persistence failed, saving via CSV fallback: %s", exc)
            result["scanId"] = save_scan(result, result["source"])

        _set_scan_image_urls(result["source"], result["scanId"])
        cache_file.write_text(json.dumps(result), encoding="utf-8")
        return result
    except HTTPException:
        raise
    except HTTPError as exc:
        cached = _read_live_cache(cache_file)
        if cached and exc.code == 429:
            return cached
        raise HTTPException(
            status_code=502,
            detail=f"Live Sentinel-2 provider rate-limited the request (HTTP {exc.code}). Try again later.",
        ) from exc
    except Exception as exc:
        logger.warning("Live Sentinel-2 scan failed: %s", exc)
        cached = _read_live_cache(cache_file)
        if cached:
            return cached
        raise HTTPException(status_code=502, detail=f"Live Sentinel-2 acquisition failed: {exc}") from exc


@app.post("/api/live-detect")
def live_detect_post(
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    """Preferred endpoint for live satellite acquisition, analysis, and graph persistence."""
    return _run_live_detect_request(idempotency_key, allow_recent_cache=False)


@app.get("/api/live-detect")
def live_detect(
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    """Return a recent shared scan or acquire new data after the refresh interval."""
    response.headers["X-Deprecated"] = "Use POST /api/live-detect instead"
    return _run_live_detect_request(idempotency_key, allow_recent_cache=True)


@app.post("/api/sites/{site_id}/scan")
def scan_site(
    site_id: str,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    if not re.fullmatch(r"site-[0-9a-f]{32}", site_id):
        raise HTTPException(status_code=404, detail="Monitoring site not found.")
    try:
        with get_driver().session() as session:
            region = region_repository.get_region(session, site_id)
        if not region or not region.get("is_monitoring_site") or region.get("active") is False:
            raise HTTPException(status_code=404, detail="Monitoring site not found.")
        geometry_value = region.get("geometry_geojson")
        if isinstance(geometry_value, str):
            geometry_value = json.loads(geometry_value)
        geometry = normalize_polygon_geometry(geometry_value)
        bbox = geometry_bbox(geometry)
        region_name = region.get("name") or "Monitoring site"
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to load monitoring site %s", site_id)
        raise HTTPException(status_code=503, detail="Monitoring site storage is unavailable.") from exc
    return _execute_live_detect(
        idempotency_key=f"{site_id}:{idempotency_key}" if idempotency_key else None,
        bbox=bbox,
        geometry=geometry,
        region_name=region_name,
        region_id=site_id,
    )


@app.post("/api/detect")
async def detect(
    historical: UploadFile = File(...),
    recent: UploadFile = File(...),
    latitude: float = 18.5204,
    longitude: float = 73.8567,
    pixel_size_m: float = 10,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    # 1. Geographic input validation
    validate_coordinates(latitude, longitude)
    validate_pixel_size(pixel_size_m)

    # 2. Image reading & dimension validation
    try:
        hist_bytes = await historical.read()
        recent_bytes = await recent.read()
        if len(hist_bytes) == 0 or len(recent_bytes) == 0:
            raise HTTPException(status_code=400, detail="Uploaded images must not be empty.")
        old_image = np.asarray(Image.open(io.BytesIO(hist_bytes)).convert("RGB"), dtype=np.float32)
        new_image = np.asarray(Image.open(io.BytesIO(recent_bytes)).convert("RGB"), dtype=np.float32)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Both files must be readable RGB images.") from exc

    validate_image_pair(old_image, new_image)

    # 3. Process detection
    result = _analyse_pair(
        old_image,
        new_image,
        latitude,
        longitude,
        pixel_size_m,
        "upload",
        "Historical upload",
        "Recent upload",
    )
    _add_area_names(result["findings"])

    source = {
        "provider": "User upload",
        "bbox": [
            round(longitude - 0.04, 6),
            round(latitude - 0.04, 6),
            round(longitude + 0.04, 6),
            round(latitude + 0.04, 6),
        ],
        "historicalItem": historical.filename or "historical_upload",
        "recentItem": recent.filename or "recent_upload",
        "note": "User-uploaded image pair",
    }
    result["source"] = source

    image_capture_id = uuid4().hex
    historical_path = MEDIA_DIR / f"historical-{image_capture_id}.png"
    recent_path = MEDIA_DIR / f"recent-{image_capture_id}.png"
    Image.fromarray(old_image.astype(np.uint8)).save(historical_path, format="PNG")
    Image.fromarray(new_image.astype(np.uint8)).save(recent_path, format="PNG")
    source.update({
        "assetType": "User-uploaded RGB images",
        "imageCaptureId": image_capture_id,
        "historicalImage": f"/media/historical-{image_capture_id}.png",
        "recentImage": f"/media/recent-{image_capture_id}.png",
    })
    try:
        _persist_scan_images(source, historical_path, recent_path)
    except Exception as exc:
        logger.exception("Could not persist uploaded scan evidence")
        raise HTTPException(status_code=503, detail="Scan evidence storage is unavailable.") from exc

    # 4. Persist to Neo4j (and CSV fallback)
    try:
        scan_id = persist_scan(
            get_driver(),
            result,
            source,
            "upload",
            idempotency_key=idempotency_key,
        )
        result["scanId"] = scan_id
    except Exception as exc:
        logger.warning("Neo4j persistence failed for upload, saving via CSV fallback: %s", exc)
        result["scanId"] = save_scan(result, source)

    _set_scan_image_urls(source, result["scanId"])
    return result
