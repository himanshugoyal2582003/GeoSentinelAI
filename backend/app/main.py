from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image
import torch
from dotenv import load_dotenv

from .change_model import load_model
from .history import read_scans, save_scan

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
app = FastAPI(title="GeoSentinel AI API", version="0.1.0")


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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
MEDIA_DIR = Path(__file__).resolve().parents[1] / "data" / "live"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = MEDIA_DIR / "last-result.json"
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")
STATIC_BBOX = (73.82, 18.48, 73.90, 18.56)
MAX_TIMELINE_SCENES = 8
SENTINEL_REVISIT_DAYS = 5

MODEL_PATH = str(Path(__file__).resolve().parents[1] / "models" / "change_cnn.pt")
CHANGE_MODEL = load_model(MODEL_PATH)
TRAINING_STATE: dict[str, Any] = {"status": "idle", "message": "Training has not been started."}
TRAINING_LOCK = threading.Lock()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "geosentinel-api", "model": "ChangeCNN" if CHANGE_MODEL else "difference-fallback"}


@app.get("/api/model")
def model_status() -> dict[str, Any]:
    metrics_path = Path(MODEL_PATH).with_name("metrics.json")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    return {"loaded": CHANGE_MODEL is not None, "metrics": metrics}


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
                CHANGE_MODEL = load_model(MODEL_PATH)
                TRAINING_STATE.update({
                    "status": "completed",
                    "message": "CNN training completed and the model was reloaded.",
                    "output": process.stdout[-2000:],
                })
            else:
                TRAINING_STATE.update({
                    "status": "failed",
                    "message": "CNN training failed.",
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
    with TRAINING_LOCK:
        if TRAINING_STATE["status"] == "running":
            return dict(TRAINING_STATE)
        TRAINING_STATE.clear()
        TRAINING_STATE.update({"status": "running", "message": "CNN training is running."})
    threading.Thread(target=_run_training, daemon=True).start()
    return dict(TRAINING_STATE)


@app.get("/api/scans")
def scans() -> dict[str, Any]:
    return {"scans": read_scans()}


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
) -> dict[str, Any]:
    new_image = _normalize_season(new_image, old_image)
    aligned_image, shift = _align_image(old_image, new_image)
    cloud_mask = _cloud_mask(old_image) | _cloud_mask(aligned_image)
    difference = np.mean(np.abs(aligned_image - old_image), axis=2)
    threshold = max(25.0, float(np.percentile(difference, 90)))
    mask = (difference >= threshold) & ~cloud_mask
    components = _components(mask)
    findings = []
    height, width = mask.shape
    for index, (x, y, component_width, component_height, pixels) in enumerate(components[:10], start=1):
        area_sqm = round(pixels * pixel_size_m * pixel_size_m)
        center_lat = latitude + ((y + component_height / 2) / height - 0.5) * 0.08
        center_lon = longitude + ((x + component_width / 2) / width - 0.5) * 0.08
        region_bbox = [
            round(latitude + (y / height - 0.5) * 0.08, 6),
            round(longitude + (x / width - 0.5) * 0.08, 6),
            round(latitude + ((y + component_height) / height - 0.5) * 0.08, 6),
            round(longitude + ((x + component_width) / width - 0.5) * 0.08, 6),
        ]
        confidence = min(0.98, 0.65 + difference[y : y + component_height, x : x + component_width].mean() / 255)
        model_score = None
        if CHANGE_MODEL:
            patch_x = max(0, min(width - 32, x + component_width // 2 - 16))
            patch_y = max(0, min(height - 32, y + component_height // 2 - 16))
            patch = np.concatenate(
                [old_image[patch_y : patch_y + 32, patch_x : patch_x + 32],
                 aligned_image[patch_y : patch_y + 32, patch_x : patch_x + 32]],
                axis=2,
            ).transpose(2, 0, 1) / 255
            with torch.no_grad():
                model_score = float(torch.sigmoid(CHANGE_MODEL(torch.from_numpy(patch.astype(np.float32))[None]))[0])
            confidence = round((confidence + model_score) / 2, 3)
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
                "changeType": "Spectral surface change",
                "firstObserved": historical_date,
                "lastObserved": recent_date,
                "status": "Needs review",
                "modelScore": model_score,
            }
        )
    total_area = sum(item["areaSqm"] for item in findings)
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
        "processing": {
            "threshold": round(threshold, 2),
            "components": len(findings),
            "model": "ChangeCNN" if CHANGE_MODEL else "difference-fallback",
            "cloudMaskPixels": int(cloud_mask.sum()),
            "alignmentShiftPixels": [round(shift[0], 3), round(shift[1], 3)],
            "seasonalNormalization": "per-channel percentile matching",
        },
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


def _download_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "GeoSentinel-MVP/1.0"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=90) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code != 429 or attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Satellite download retry limit reached")


def _read_live_cache() -> dict[str, Any] | None:
    if not CACHE_FILE.exists():
        return None
    try:
        cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        cached["source"]["stale"] = True
        cached["source"]["note"] = (
            "Provider rate limit reached. Showing the most recent successfully downloaded "
            "real Sentinel-2 scan; run again later for a fresh acquisition."
        )
        return cached
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _live_scenes() -> list[dict[str, Any]]:
    # POST is used because the STAC API's query syntax is more reliable in JSON.
    payload = json.dumps({
        "collections": ["sentinel-2-l2a"],
        "bbox": list(STATIC_BBOX),
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


def _signed_preview(item: dict[str, Any]) -> bytes:
    href = item["assets"]["rendered_preview"]["href"]
    sign_url = "https://planetarycomputer.microsoft.com/api/sas/v1/sign?href=" + quote(href, safe="")
    for attempt in range(3):
        try:
            with urlopen(Request(sign_url, headers={"User-Agent": "GeoSentinel-MVP/1.0"}), timeout=30) as response:
                signed = json.loads(response.read())["href"]
            return _download_bytes(signed)
        except HTTPError as exc:
            if exc.code != 429 or attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Satellite signing retry limit reached")


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


@app.get("/api/live-detect")
def live_detect() -> dict[str, Any]:
    """Fetch the two newest low-cloud public scenes at the static Pune location and infer changes."""
    try:
        scenes = _live_scenes()
        image_bytes = {scene["id"]: _signed_preview(scene) for scene in scenes}
        historical, recent = scenes[0], scenes[-1]
        historical_bytes = image_bytes[historical["id"]]
        recent_bytes = image_bytes[recent["id"]]
        historical_path = MEDIA_DIR / "historical-live.png"
        recent_path = MEDIA_DIR / "recent-live.png"
        historical_path.write_bytes(historical_bytes)
        recent_path.write_bytes(recent_bytes)
        old_image = np.asarray(Image.open(io.BytesIO(historical_bytes)).convert("RGB"), dtype=np.float32)
        new_image = np.asarray(Image.open(io.BytesIO(recent_bytes)).convert("RGB"), dtype=np.float32)
        result = _analyse_pair(
            old_image,
            new_image,
            (STATIC_BBOX[1] + STATIC_BBOX[3]) / 2,
            (STATIC_BBOX[0] + STATIC_BBOX[2]) / 2,
            10,
            "live-sentinel2",
            historical["properties"]["datetime"][:10],
            recent["properties"]["datetime"][:10],
        )
        _add_area_names(result["findings"])
        timeline = []
        historical_image = np.asarray(Image.open(io.BytesIO(historical_bytes)).convert("RGB"), dtype=np.float32)
        for previous, current in zip(scenes, scenes[1:]):
            pair_result = _analyse_pair(
                np.asarray(Image.open(io.BytesIO(image_bytes[previous["id"]])).convert("RGB"), dtype=np.float32),
                np.asarray(Image.open(io.BytesIO(image_bytes[current["id"]])).convert("RGB"), dtype=np.float32),
                (STATIC_BBOX[1] + STATIC_BBOX[3]) / 2,
                (STATIC_BBOX[0] + STATIC_BBOX[2]) / 2,
                10,
                "timeline",
                previous["properties"]["datetime"][:10],
                current["properties"]["datetime"][:10],
            )
            timeline.append({"month": current["properties"]["datetime"][:10], "areaSqm": pair_result["summary"]["changedAreaSqm"]})
        result["timeline"] = [{"month": historical["properties"]["datetime"][:10], "areaSqm": 0}] + timeline
        result["timelineNote"] = (
            f"Multi-scene trajectory from up to {MAX_TIMELINE_SCENES} newest low-cloud observations. "
            f"Sentinel-2 revisits this area approximately every {SENTINEL_REVISIT_DAYS} days; "
            "actual timeline dates are shown because cloudy scenes are skipped."
        )
        result["source"] = {
            "provider": "Microsoft Planetary Computer / Copernicus Sentinel-2 L2A",
            "bbox": list(STATIC_BBOX),
            "historicalItem": historical["id"],
            "recentItem": recent["id"],
            "historicalCloudCover": historical["properties"].get("eo:cloud_cover"),
            "recentCloudCover": recent["properties"].get("eo:cloud_cover"),
            "historicalImage": "/media/historical-live.png",
            "recentImage": "/media/recent-live.png",
            "sceneCount": len(scenes),
            "sceneCadenceDays": SENTINEL_REVISIT_DAYS,
            "monitoringIntervalMinutes": 10,
            "sceneDates": [scene["properties"]["datetime"][:10] for scene in scenes],
            "note": "Public satellite imagery; detections are intelligence signals, not legal determinations.",
        }
        result["scanId"] = save_scan(result, result["source"])
        CACHE_FILE.write_text(json.dumps(result), encoding="utf-8")
        return result
    except HTTPException:
        raise
    except HTTPError as exc:
        cached = _read_live_cache()
        if cached and exc.code == 429:
            return cached
        raise HTTPException(
            status_code=502,
            detail=f"Live Sentinel-2 provider rate-limited the request (HTTP {exc.code}). Try again later.",
        ) from exc
    except Exception as exc:
        cached = _read_live_cache()
        if cached:
            return cached
        raise HTTPException(status_code=502, detail=f"Live Sentinel-2 acquisition failed: {exc}") from exc


@app.post("/api/detect")
async def detect(
    historical: UploadFile = File(...),
    recent: UploadFile = File(...),
    latitude: float = 18.5204,
    longitude: float = 73.8567,
    pixel_size_m: float = 10,
) -> dict[str, Any]:
    try:
        old_image = np.asarray(Image.open(io.BytesIO(await historical.read())).convert("RGB"), dtype=np.float32)
        new_image = np.asarray(Image.open(io.BytesIO(await recent.read())).convert("RGB"), dtype=np.float32)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Both files must be readable RGB images.") from exc
    if old_image.shape != new_image.shape:
        raise HTTPException(status_code=400, detail="Historical and recent images must have identical dimensions.")
    if old_image.shape[0] * old_image.shape[1] > 4_000_000:
        raise HTTPException(status_code=413, detail="Images must be at most 4 megapixels for this MVP.")

    return _analyse_pair(
        old_image,
        new_image,
        latitude,
        longitude,
        pixel_size_m,
        "upload",
        "Historical upload",
        "Recent upload",
    )
