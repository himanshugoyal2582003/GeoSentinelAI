from __future__ import annotations

import json
import pytest

from app.geometry import geometry_bbox, normalize_polygon_geometry, parse_geojson_upload, parse_kml_upload

POLYGON = {
    "type": "Polygon",
    "coordinates": [[
        [73.82, 18.48],
        [73.86, 18.48],
        [73.86, 18.52],
        [73.82, 18.52],
        [73.82, 18.48],
    ]],
}


def test_normalizes_polygon_and_derives_wgs84_bbox() -> None:
    geometry = normalize_polygon_geometry(POLYGON)

    assert geometry == POLYGON
    assert geometry_bbox(geometry) == (73.82, 18.48, 73.86, 18.52)


def test_rejects_unclosed_and_out_of_range_rings() -> None:
    unclosed = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1]]]}
    invalid_coordinate = {
        "type": "Polygon",
        "coordinates": [[[181, 0], [1, 0], [1, 1], [181, 0]]],
    }

    with pytest.raises(ValueError, match="closed"):
        normalize_polygon_geometry(unclosed)
    with pytest.raises(ValueError, match="WGS-84"):
        normalize_polygon_geometry(invalid_coordinate)


def test_rejects_polygons_crossing_antimeridian() -> None:
    geometry = normalize_polygon_geometry({
        "type": "Polygon",
        "coordinates": [[[179, 0], [-179, 0], [-179, 1], [179, 1], [179, 0]]],
    })

    with pytest.raises(ValueError, match="antimeridian"):
        geometry_bbox(geometry)


def test_imports_polygon_feature_collection_and_kml() -> None:
    feature_collection = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": POLYGON}],
    }
    kml = b"""<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><Polygon>
    <outerBoundaryIs><LinearRing><coordinates>
    73.82,18.48,0 73.86,18.48,0 73.86,18.52,0 73.82,18.52,0 73.82,18.48,0
    </coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>"""

    expected_multi = {"type": "MultiPolygon", "coordinates": [POLYGON["coordinates"]]}
    assert parse_geojson_upload(json.dumps(feature_collection).encode()) == expected_multi
    assert parse_kml_upload(kml) == POLYGON


def test_rejects_kml_entities() -> None:
    with pytest.raises(ValueError, match="entities"):
        parse_kml_upload(b"<!DOCTYPE kml [<!ENTITY x 'boom'>]><kml/>")
