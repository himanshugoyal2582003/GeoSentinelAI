from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=True)

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


def test_create_site_persists_normalized_polygon() -> None:
    driver = MagicMock()
    with patch("app.api.sites.get_driver", return_value=driver), patch(
        "app.api.sites.region_repository.merge_region", return_value="site-id"
    ) as merge_region:
        response = client.post("/api/sites", json={"name": "  Test quarry ", "geometry": POLYGON})

    assert response.status_code == 201
    result = response.json()
    assert result["name"] == "Test quarry"
    assert result["geometry"] == POLYGON
    assert result["bbox"] == [73.82, 18.48, 73.86, 18.52]
    assert merge_region.call_args.args[1]["is_monitoring_site"] is True


def test_create_site_rejects_invalid_polygon_before_database_write() -> None:
    driver = MagicMock()
    unclosed = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1]]]}
    with patch("app.api.sites.get_driver", return_value=driver), patch(
        "app.api.sites.region_repository.merge_region"
    ) as merge_region:
        response = client.post("/api/sites", json={"name": "Bad site", "geometry": unclosed})

    assert response.status_code == 422
    merge_region.assert_not_called()


def test_import_site_accepts_geojson_upload() -> None:
    upload = {
        "type": "Feature",
        "properties": {},
        "geometry": POLYGON,
    }
    with patch(
        "app.api.sites._create_site",
        return_value={"siteId": "site-test", "name": "Imported site", "geometry": POLYGON},
    ) as create_site:
        response = client.post(
            "/api/sites/import",
            data={"name": "Imported site"},
            files={"file": ("boundary.geojson", json.dumps(upload), "application/geo+json")},
        )

    assert response.status_code == 201
    create_site.assert_called_once_with("Imported site", POLYGON)


def test_scan_site_passes_polygon_and_bbox_to_live_pipeline() -> None:
    site_id = "site-" + "a" * 32
    region = {
        "region_id": site_id,
        "name": "Test quarry",
        "is_monitoring_site": True,
        "active": True,
        "geometry_geojson": json.dumps(POLYGON),
    }
    expected = {"scanId": "scan-test"}
    with patch("app.main.get_driver", return_value=MagicMock()), patch(
        "app.main.region_repository.get_region", return_value=region
    ), patch("app.main._execute_live_detect", return_value=expected) as live_scan:
        response = client.post(f"/api/sites/{site_id}/scan")

    assert response.status_code == 200
    assert response.json() == expected
    live_scan.assert_called_once_with(
        idempotency_key=None,
        bbox=(73.82, 18.48, 73.86, 18.52),
        geometry=POLYGON,
        region_name="Test quarry",
        region_id=site_id,
    )


def test_delete_site_returns_empty_204_response() -> None:
    with patch("app.api.sites.get_driver", return_value=MagicMock()), patch(
        "app.api.sites.region_repository.deactivate_site", return_value=True
    ):
        response = client.delete("/api/sites/site-test")

    assert response.status_code == 204
    assert response.content == b""


def test_cors_allows_local_next_dev_server_on_alternate_port() -> None:
    response = client.options(
        "/api/sites",
        headers={
            "Origin": "http://localhost:3001",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3001"
