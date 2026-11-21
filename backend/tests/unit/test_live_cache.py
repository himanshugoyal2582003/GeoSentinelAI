from __future__ import annotations

import json
import os
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app import main


def _write_cache(path, timestamp: float) -> None:
    path.write_text(
        json.dumps({
            "source": {
                "provider": "Sentinel-2",
                "note": "Fresh scan",
                "monitoringIntervalMinutes": 10,
            },
        }),
        encoding="utf-8",
    )
    os.utime(path, (timestamp, timestamp))


def test_recent_live_cache_is_marked_cached_with_age(tmp_path) -> None:
    cache_file = tmp_path / "last-result.json"
    now = time.time()
    _write_cache(cache_file, now - 120)

    result = main._read_recent_live_cache(cache_file, now=now)

    assert result is not None
    assert result["source"]["stale"] is True
    assert result["source"]["cacheAgeSeconds"] == 120
    assert result["source"]["monitoringIntervalMinutes"] == 30
    assert "2 minutes ago" in result["source"]["note"]


def test_recent_live_cache_expires_after_thirty_minutes(tmp_path) -> None:
    cache_file = tmp_path / "last-result.json"
    now = time.time()
    _write_cache(cache_file, now - main.LIVE_SCAN_CACHE_TTL_SECONDS)

    assert main._read_recent_live_cache(cache_file, now=now) is None


def test_automatic_live_request_reuses_recent_result(monkeypatch) -> None:
    cached = {"source": {"stale": True}}
    read_cache = Mock(return_value=cached)
    execute = Mock()
    monkeypatch.setattr(main, "_LAST_LIVE_SCAN_ATTEMPT", None)
    monkeypatch.setattr(main, "_read_recent_live_cache", read_cache)
    monkeypatch.setattr(main, "_execute_live_detect", execute)

    result = main._run_live_detect_request(None, allow_recent_cache=True)

    assert result is cached
    read_cache.assert_called_once_with()
    execute.assert_not_called()


def test_manual_live_request_bypasses_shared_cache(monkeypatch) -> None:
    fresh = {"scanId": "fresh"}
    read_cache = Mock()
    execute = Mock(return_value=fresh)
    monkeypatch.setattr(main, "_LAST_LIVE_SCAN_ATTEMPT", None)
    monkeypatch.setattr(main, "_read_recent_live_cache", read_cache)
    monkeypatch.setattr(main, "_execute_live_detect", execute)

    result = main._run_live_detect_request(None, allow_recent_cache=False)

    assert result is fresh
    read_cache.assert_not_called()
    execute.assert_called_once_with(idempotency_key=None)


def test_failed_live_request_is_throttled_for_thirty_minutes(monkeypatch) -> None:
    times = iter((1000.0, 1001.0))
    monkeypatch.setattr(main, "time", SimpleNamespace(monotonic=lambda: next(times)))
    monkeypatch.setattr(main, "_LAST_LIVE_SCAN_ATTEMPT", None)
    monkeypatch.setattr(main, "_read_recent_live_cache", lambda: None)
    monkeypatch.setattr(main, "_read_live_cache", lambda: None)
    execute = Mock(side_effect=RuntimeError("provider unavailable"))
    monkeypatch.setattr(main, "_execute_live_detect", execute)

    with pytest.raises(RuntimeError, match="provider unavailable"):
        main._run_live_detect_request(None, allow_recent_cache=True)

    with pytest.raises(HTTPException) as error:
        main._run_live_detect_request(None, allow_recent_cache=True)

    assert error.value.status_code == 429
    assert int(error.value.headers["Retry-After"]) > 0
    execute.assert_called_once()
