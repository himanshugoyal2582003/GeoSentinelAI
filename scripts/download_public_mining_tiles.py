from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import sqlite3
import struct
import time
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import numpy as np
import planetary_computer
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform
import pystac

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GPKG = ROOT / "dataset" / "public-global-mining" / "mining_area_data.gpkg"
DEFAULT_OUTPUT = ROOT / "backend" / "data" / "public_mining"
STAC_ITEM_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-2-l2a/items/{}"
PATCH_TILE_METERS = 20_480
PIXEL_SIZE_METERS = 10
IMAGE_SIZE = PATCH_TILE_METERS // PIXEL_SIZE_METERS
BANDS = ("B04", "B03", "B02")


def _gpkg_wkb(geometry_blob: bytes) -> bytes:
    if geometry_blob[:2] != b"GP":
        raise ValueError("Geometry is missing the GeoPackage binary header")
    flags = geometry_blob[3]
    envelope_code = (flags >> 1) & 0b111
    envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    if envelope_code not in envelope_sizes:
        raise ValueError(f"Unknown GeoPackage envelope indicator: {envelope_code}")
    return geometry_blob[8 + envelope_sizes[envelope_code] :]


def _read_wkb_geometry(data: bytes, offset: int = 0) -> tuple[dict[str, Any], int]:
    byte_order = data[offset]
    endian = "<" if byte_order == 1 else ">"
    geometry_type = struct.unpack_from(f"{endian}I", data, offset + 1)[0]
    offset += 5
    if geometry_type == 3:
        ring_count = struct.unpack_from(f"{endian}I", data, offset)[0]
        offset += 4
        rings = []
        for _ in range(ring_count):
            point_count = struct.unpack_from(f"{endian}I", data, offset)[0]
            offset += 4
            ring = []
            for _ in range(point_count):
                x, y = struct.unpack_from(f"{endian}dd", data, offset)
                offset += 16
                ring.append((x, y))
            rings.append(ring)
        return {"type": "Polygon", "coordinates": rings}, offset
    if geometry_type == 6:
        polygon_count = struct.unpack_from(f"{endian}I", data, offset)[0]
        offset += 4
        polygons = []
        for _ in range(polygon_count):
            polygon, offset = _read_wkb_geometry(data, offset)
            if polygon["type"] != "Polygon":
                raise ValueError("A MultiPolygon contained a non-Polygon geometry")
            polygons.append(polygon["coordinates"])
        return {"type": "MultiPolygon", "coordinates": polygons}, offset
    raise ValueError(f"Only 2D Polygon and MultiPolygon labels are supported; got WKB type {geometry_type}")


def _geometry(geometry_blob: bytes) -> dict[str, Any]:
    geometry, _ = _read_wkb_geometry(_gpkg_wkb(geometry_blob))
    return geometry


def _polygon_centroid(ring: list[tuple[float, float]]) -> tuple[float, float]:
    area_twice = 0.0
    centroid_x = centroid_y = 0.0
    for first, second in zip(ring, ring[1:]):
        cross = first[0] * second[1] - second[0] * first[1]
        area_twice += cross
        centroid_x += (first[0] + second[0]) * cross
        centroid_y += (first[1] + second[1]) * cross
    if abs(area_twice) < 1e-15:
        xs, ys = zip(*ring)
        return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    return centroid_x / (3 * area_twice), centroid_y / (3 * area_twice)


def _project_geometry(geometry: dict[str, Any], epsg: int) -> dict[str, Any]:
    def project_ring(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
        xs, ys = transform("EPSG:4326", f"EPSG:{epsg}", [p[0] for p in ring], [p[1] for p in ring])
        return list(zip(xs, ys))

    if geometry["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": [project_ring(ring) for ring in geometry["coordinates"]]}
    return {
        "type": "MultiPolygon",
        "coordinates": [[project_ring(ring) for ring in polygon] for polygon in geometry["coordinates"]],
    }


def _rasterize_mask(geometry: dict[str, Any], epsg: int, affine: Any) -> np.ndarray:
    projected = _project_geometry(geometry, epsg)
    return rasterize(
        [(projected, 1)],
        out_shape=(IMAGE_SIZE, IMAGE_SIZE),
        transform=affine,
        fill=0,
        dtype="uint8",
        all_touched=False,
    )


def _load_records(gpkg_path: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(gpkg_path)
    try:
        masks = {
            int(tile_id): _geometry(geom)
            for tile_id, geom in connection.execute(
                "SELECT tile_id, geom FROM preferred_polygons WHERE geom IS NOT NULL"
            )
        }
        records = []
        for tile_id, item_id, split, geom in connection.execute(
            "SELECT tile_id, s2_tile_id, split, geom FROM tiles WHERE split IN ('train', 'val', 'test') ORDER BY split, tile_id"
        ):
            tile_id = int(tile_id)
            if tile_id not in masks:
                continue
            tile_geometry = _geometry(geom)
            if tile_geometry["type"] != "Polygon":
                raise ValueError(f"Tile geometry for {tile_id} is not a Polygon")
            center_lon, center_lat = _polygon_centroid(tile_geometry["coordinates"][0])
            records.append({
                "tile_id": tile_id,
                "item_id": item_id,
                "split": split,
                "center_lon": center_lon,
                "center_lat": center_lat,
                "mask": masks[tile_id],
            })
        return records
    finally:
        connection.close()


def _signed_item(item_id: str) -> pystac.Item:
    with urlopen(STAC_ITEM_URL.format(item_id), timeout=60) as response:
        item = pystac.Item.from_dict(json.loads(response.read()))
    return planetary_computer.sign(item)


def _read_band(href: str, transform_out: Any, epsg: int) -> np.ndarray:
    result = np.zeros((IMAGE_SIZE, IMAGE_SIZE), dtype=np.uint16)
    with rasterio.open(href) as source:
        source_epsg = source.crs.to_epsg() if source.crs else None
        if source_epsg != epsg:
            raise ValueError(f"Band CRS EPSG:{source_epsg} does not match scene EPSG:{epsg}")
        reproject(
            source=rasterio.band(source, 1),
            destination=result,
            src_transform=source.transform,
            src_crs=source.crs,
            dst_transform=transform_out,
            dst_crs=f"EPSG:{epsg}",
            resampling=Resampling.bilinear,
            src_nodata=source.nodata,
            dst_nodata=0,
            num_threads=1,
        )
    return result


def _persist_tile(record: dict[str, Any], output_dir: Path) -> None:
    split_dir = output_dir / record["split"]
    split_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{record['tile_id']}_{record['item_id']}"
    image_path = split_dir / f"{stem}_img.tif"
    mask_path = split_dir / f"{stem}_mask.tif"
    if image_path.exists() and mask_path.exists():
        return

    item = _signed_item(record["item_id"])
    epsg = item.properties.get("proj:epsg")
    if epsg is None:
        crs_code = item.properties.get("proj:code")
        if crs_code and str(crs_code).upper().startswith("EPSG:"):
            epsg = str(crs_code).split(":", 1)[1]
    if epsg is None:
        raise ValueError(f"STAC item {record['item_id']} does not specify proj:epsg")
    x_center, y_center = transform(
        "EPSG:4326", f"EPSG:{epsg}", [record["center_lon"]], [record["center_lat"]]
    )
    affine = from_origin(
        x_center[0] - PATCH_TILE_METERS / 2,
        y_center[0] + PATCH_TILE_METERS / 2,
        PIXEL_SIZE_METERS,
        PIXEL_SIZE_METERS,
    )
    bands = []
    for band in BANDS:
        if band not in item.assets:
            raise ValueError(f"STAC item {record['item_id']} is missing band {band}")
        bands.append(_read_band(item.assets[band].href, affine, int(epsg)))
    image = np.stack(bands)
    mask = _rasterize_mask(record["mask"], int(epsg), affine)

    image_tmp = image_path.with_suffix(".tmp.tif")
    mask_tmp = mask_path.with_suffix(".tmp.tif")
    profile = {
        "driver": "GTiff",
        "height": IMAGE_SIZE,
        "width": IMAGE_SIZE,
        "count": 3,
        "dtype": "uint16",
        "crs": f"EPSG:{epsg}",
        "transform": affine,
        "compress": "deflate",
        "predictor": 2,
        "tiled": True,
    }
    with rasterio.open(image_tmp, "w", **profile) as destination:
        destination.write(image)
    profile.update(count=1, dtype="uint8", predictor=1)
    with rasterio.open(mask_tmp, "w", **profile) as destination:
        destination.write(mask, 1)
    image_tmp.replace(image_path)
    mask_tmp.replace(mask_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the public mining dataset's Sentinel-2 RGB tiles and masks.")
    parser.add_argument("--gpkg", type=Path, default=DEFAULT_GPKG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, help="Optional per-run tile cap; omit to retrieve all assigned splits.")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--pause-seconds", type=float, default=0.1)
    args = parser.parse_args()
    if not args.gpkg.exists():
        parser.error(f"GeoPackage not found: {args.gpkg}. Download and extract the Zenodo archive first.")

    records = _load_records(args.gpkg)
    if args.limit is not None:
        if args.limit < 1:
            parser.error("--limit must be positive")
        records = records[: args.limit]
    if args.workers < 1:
        parser.error("--workers must be positive")
    counts = {split: sum(record["split"] == split for record in records) for split in ("train", "val", "test")}
    print(
        f"Preparing {len(records)} tiles (train={counts['train']}, val={counts['val']}, "
        f"test={counts['test']}) with {args.workers} workers."
    )
    errors = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_persist_tile, record, args.output_dir): record for record in records}
        for index, future in enumerate(as_completed(futures), start=1):
            record = futures[future]
            try:
                future.result()
            except Exception as exc:
                errors.append({"tileId": record["tile_id"], "itemId": record["item_id"], "error": str(exc)})
            if index % 10 == 0 or index == len(records):
                print(f"Processed {index}/{len(records)} tiles; failures={len(errors)}.", flush=True)
            if args.pause_seconds > 0:
                time.sleep(args.pause_seconds)
    if errors:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "download_errors.json").write_text(json.dumps(errors, indent=2), encoding="utf-8")
        raise SystemExit(f"{len(errors)} tile(s) failed. Rerun the command to resume; completed tiles are skipped.")
    error_manifest = args.output_dir / "download_errors.json"
    if error_manifest.exists():
        error_manifest.unlink()
    (args.output_dir / "download_manifest.json").write_text(
        json.dumps({"sourceDoi": "10.5281/zenodo.14195737", "bands": BANDS, "tileCount": len(records), "splits": counts}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
