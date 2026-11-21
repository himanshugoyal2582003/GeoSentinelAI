from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from typing import Any


MAX_GEOMETRY_VERTICES = 5000
MAX_IMPORT_BYTES = 2 * 1024 * 1024


def normalize_polygon_geometry(value: Any) -> dict[str, Any]:
    """Validate and normalize a GeoJSON Polygon or MultiPolygon."""
    if isinstance(value, dict) and value.get("type") == "Feature":
        value = value.get("geometry")
    if not isinstance(value, dict):
        raise ValueError("Geometry must be a GeoJSON Polygon or MultiPolygon.")

    geometry_type = value.get("type")
    coordinates = value.get("coordinates")
    if geometry_type == "Polygon":
        polygons = [coordinates]
    elif geometry_type == "MultiPolygon":
        polygons = coordinates
    else:
        raise ValueError("Only GeoJSON Polygon and MultiPolygon geometries are supported.")

    if not isinstance(polygons, list) or not polygons:
        raise ValueError("Polygon geometry must contain at least one ring.")

    normalized_polygons: list[list[list[list[float]]]] = []
    vertex_count = 0
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise ValueError("Each polygon must contain an exterior ring.")
        normalized_rings = []
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4:
                raise ValueError("Each polygon ring must contain at least four positions.")
            normalized_ring = []
            for position in ring:
                if (
                    not isinstance(position, (list, tuple))
                    or len(position) < 2
                    or not isinstance(position[0], (int, float))
                    or isinstance(position[0], bool)
                    or not isinstance(position[1], (int, float))
                    or isinstance(position[1], bool)
                ):
                    raise ValueError("Polygon positions must contain longitude and latitude.")
                try:
                    longitude, latitude = float(position[0]), float(position[1])
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("Polygon coordinates must be finite numbers.") from exc
                if not math.isfinite(longitude) or not math.isfinite(latitude):
                    raise ValueError("Polygon coordinates must be finite numbers.")
                if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
                    raise ValueError("Polygon coordinates must be valid WGS-84 longitude/latitude.")
                normalized_ring.append([longitude, latitude])
            if normalized_ring[0] != normalized_ring[-1]:
                raise ValueError("Polygon rings must be closed.")
            if abs(_ring_area(normalized_ring)) < 1e-12:
                raise ValueError("Polygon rings must enclose a non-zero area.")
            vertex_count += len(normalized_ring)
            normalized_rings.append(normalized_ring)
        normalized_polygons.append(normalized_rings)

    if vertex_count > MAX_GEOMETRY_VERTICES:
        raise ValueError(f"Geometry exceeds the {MAX_GEOMETRY_VERTICES}-vertex limit.")
    if geometry_type == "Polygon":
        return {"type": "Polygon", "coordinates": normalized_polygons[0]}
    return {"type": "MultiPolygon", "coordinates": normalized_polygons}


def geometry_bbox(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    positions = (
        position
        for polygon in (
            [geometry["coordinates"]]
            if geometry["type"] == "Polygon"
            else geometry["coordinates"]
        )
        for ring in polygon
        for position in ring
    )
    coordinates = list(positions)
    west = min(position[0] for position in coordinates)
    south = min(position[1] for position in coordinates)
    east = max(position[0] for position in coordinates)
    north = max(position[1] for position in coordinates)
    if east - west > 180:
        raise ValueError("Polygons crossing the antimeridian are not supported.")
    if south < -80 or north > 84:
        raise ValueError("Monitoring sites must fit within the UTM latitude range (-80 to 84 degrees).")
    return west, south, east, north


def parse_geojson_upload(content: bytes) -> dict[str, Any]:
    if len(content) > MAX_IMPORT_BYTES:
        raise ValueError("Geometry upload exceeds the 2 MB limit.")
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Upload is not valid GeoJSON.") from exc

    if isinstance(payload, dict) and payload.get("type") == "FeatureCollection":
        features = payload.get("features")
        if not isinstance(features, list):
            raise ValueError("GeoJSON FeatureCollection must contain a features array.")
        geometries = [
            feature.get("geometry")
            for feature in features
            if isinstance(feature, dict) and feature.get("geometry")
        ]
        polygons = []
        for geometry in geometries:
            normalized = normalize_polygon_geometry(geometry)
            if normalized["type"] == "Polygon":
                polygons.append(normalized["coordinates"])
            else:
                polygons.extend(normalized["coordinates"])
        if not polygons:
            raise ValueError("GeoJSON FeatureCollection contains no supported polygon features.")
        return normalize_polygon_geometry({"type": "MultiPolygon", "coordinates": polygons})
    return normalize_polygon_geometry(payload)


def parse_kml_upload(content: bytes) -> dict[str, Any]:
    if len(content) > MAX_IMPORT_BYTES:
        raise ValueError("Geometry upload exceeds the 2 MB limit.")
    upper_content = content.upper()
    if b"<!DOCTYPE" in upper_content or b"<!ENTITY" in upper_content:
        raise ValueError("KML document types and entities are not supported.")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError("Upload is not valid KML.") from exc

    polygons = []
    for polygon in root.findall(".//{*}Polygon"):
        rings = []
        for linear_ring in polygon.findall(".//{*}LinearRing"):
            coordinates = linear_ring.find("{*}coordinates")
            if coordinates is None or not coordinates.text:
                continue
            ring = []
            for token in coordinates.text.split():
                parts = token.split(",")
                if len(parts) < 2:
                    raise ValueError("KML coordinates must use longitude,latitude pairs.")
                try:
                    ring.append([float(parts[0]), float(parts[1])])
                except ValueError as exc:
                    raise ValueError("KML coordinates must be numeric.") from exc
            rings.append(ring)
        if rings:
            polygons.append(rings)
    if not polygons:
        raise ValueError("KML contains no Polygon geometry.")
    if len(polygons) == 1:
        return normalize_polygon_geometry({"type": "Polygon", "coordinates": polygons[0]})
    return normalize_polygon_geometry({"type": "MultiPolygon", "coordinates": polygons})


def _ring_area(ring: list[list[float]]) -> float:
    return sum(
        ring[index][0] * ring[index + 1][1] - ring[index + 1][0] * ring[index][1]
        for index in range(len(ring) - 1)
    ) / 2
