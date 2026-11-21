"""
Unit tests for the GeoSentinelAI repository layer.

All Neo4j interaction is mocked; no live database is required.
Tests verify:
  - Correct Cypher constants are used (never built via f-string / .format()).
  - Parameterized dicts contain the expected keys.
  - Return values are shaped correctly.
  - Duplicate-safe logic (MERGE / duplicate-prevention) is wired up.
  - ServiceUnavailable / TransientError are re-raised as RuntimeError.
  - Spatial query structure is correct.
"""
from __future__ import annotations

import ast
import importlib
import inspect
import types
import unittest
from unittest.mock import MagicMock, patch, call

from neo4j.exceptions import ServiceUnavailable, TransientError


# ---------------------------------------------------------------------------
# Helper: build a mock session whose .run() returns a mock result.
# ---------------------------------------------------------------------------

def _make_session(records=None):
    """Return a MagicMock session pre-wired with a result."""
    session = MagicMock()
    result = MagicMock()
    if records is None:
        records = []
    result.__iter__ = MagicMock(return_value=iter(records))
    result.single = MagicMock(return_value=records[0] if records else None)
    session.run = MagicMock(return_value=result)
    return session


def _make_record(**kwargs):
    """Return a dict-like MagicMock whose __getitem__ returns the given kwargs."""
    record = MagicMock()
    record.__getitem__ = MagicMock(side_effect=lambda k: kwargs[k])
    return record


# ===========================================================================
# 1. scan_repository
# ===========================================================================

class TestScanRepository(unittest.TestCase):

    def setUp(self):
        import app.repositories.scan_repository as mod
        self.mod = mod

    # --- create_scan ---------------------------------------------------------

    def test_create_scan_returns_scan_id(self):
        """create_scan returns the scan_id string from the MERGE result."""
        record = _make_record(scan_id="scan-abc")
        session = _make_session([record])
        result = self.mod.create_scan(session, {"scan_id": "scan-abc", "status": "pending"})
        self.assertEqual(result, "scan-abc")
        session.run.assert_called_once()

    def test_create_scan_calls_run_with_params(self):
        """create_scan passes all fields as keyword params, not injected into Cypher."""
        record = _make_record(scan_id="s1")
        session = _make_session([record])
        self.mod.create_scan(session, {
            "scan_id": "s1",
            "region_id": "r1",
            "mode": "static",
            "status": "done",
        })
        _, kwargs = session.run.call_args
        # The Cypher string must be the first positional argument
        cypher_string = session.run.call_args[0][0]
        # Verify user data is NOT in the Cypher string
        self.assertNotIn("s1", cypher_string)
        self.assertNotIn("r1", cypher_string)

    def test_create_scan_uses_merge_cypher(self):
        """The Cypher constant for create_scan must include MERGE."""
        self.assertIn("MERGE", self.mod._MERGE_SCAN)

    def test_create_scan_service_unavailable_raises_runtime(self):
        session = MagicMock()
        session.run.side_effect = ServiceUnavailable("down")
        with self.assertRaises(RuntimeError):
            self.mod.create_scan(session, {"scan_id": "x"})

    def test_create_scan_transient_error_raises_runtime(self):
        session = MagicMock()
        session.run.side_effect = TransientError()
        with self.assertRaises(RuntimeError):
            self.mod.create_scan(session, {"scan_id": "x"})

    # --- get_scan ------------------------------------------------------------

    def test_get_scan_returns_dict_when_found(self):
        inner = {"scan_id": "s1", "status": "done"}
        record = _make_record(scan=inner)
        record.__getitem__.side_effect = lambda k: inner if k == "scan" else None
        session = _make_session([record])
        result = self.mod.get_scan(session, "s1")
        self.assertIsInstance(result, dict)

    def test_get_scan_returns_none_when_missing(self):
        session = _make_session([])
        result = self.mod.get_scan(session, "missing")
        self.assertIsNone(result)

    # --- list_scans ----------------------------------------------------------

    def test_list_scans_no_region_id(self):
        session = _make_session([])
        result = self.mod.list_scans(session, region_id=None, limit=10, offset=0)
        self.assertIsInstance(result, list)
        # Should have called the ALL variant (no region_id parameter in kwargs)
        cypher = session.run.call_args[0][0]
        self.assertNotIn("region_id", cypher.split("$")[0].lower() if "$region_id" not in cypher.split("MATCH")[0] else "")

    def test_list_scans_with_region_id_uses_region_query(self):
        session = _make_session([])
        self.mod.list_scans(session, region_id="region-1", limit=5, offset=0)
        _, kw = session.run.call_args
        # kwargs should include region_id
        self.assertIn("region_id", kw)
        self.assertEqual(kw["region_id"], "region-1")

    # --- count_scans ---------------------------------------------------------

    def test_count_scans_returns_int(self):
        record = _make_record(total=42)
        session = _make_session([record])
        result = self.mod.count_scans(session)
        self.assertEqual(result, 42)

    # --- update_scan_status --------------------------------------------------

    def test_update_scan_status_runs_query(self):
        session = _make_session([])
        self.mod.update_scan_status(session, "s1", "complete")
        session.run.assert_called_once()
        _, kw = session.run.call_args
        self.assertEqual(kw.get("scan_id"), "s1")
        self.assertEqual(kw.get("status"), "complete")

    # --- get_scan_by_idempotency_key -----------------------------------------

    def test_idempotency_key_lookup_passes_key_as_param(self):
        session = _make_session([])
        self.mod.get_scan_by_idempotency_key(session, "ikey-123")
        _, kw = session.run.call_args
        self.assertEqual(kw.get("idempotency_key"), "ikey-123")
        # Key must NOT be in the Cypher string
        cypher = session.run.call_args[0][0]
        self.assertNotIn("ikey-123", cypher)


# ===========================================================================
# 2. finding_repository
# ===========================================================================

class TestFindingRepository(unittest.TestCase):

    def setUp(self):
        import app.repositories.finding_repository as mod
        self.mod = mod

    def test_create_findings_batch_returns_ids(self):
        r1 = _make_record(detection_id="d1")
        r2 = _make_record(detection_id="d2")
        result_mock = MagicMock()
        result_mock.__iter__ = MagicMock(return_value=iter([r1, r2]))
        session = MagicMock()
        session.run.return_value = result_mock
        ids = self.mod.create_findings_batch(session, [{"detection_id": "d1"}, {"detection_id": "d2"}])
        self.assertEqual(ids, ["d1", "d2"])

    def test_create_findings_batch_empty_list_no_db_call(self):
        session = MagicMock()
        ids = self.mod.create_findings_batch(session, [])
        session.run.assert_not_called()
        self.assertEqual(ids, [])

    def test_create_findings_batch_uses_unwind(self):
        self.assertIn("UNWIND", self.mod._CREATE_FINDINGS_BATCH)

    def test_bbox_query_uses_lat_lon_params(self):
        """find_in_bbox passes all four bbox corners as named params, not injected."""
        session = _make_session([])
        self.mod.find_in_bbox(session, 10.0, 20.0, 11.0, 21.0, limit=5)
        _, kw = session.run.call_args
        self.assertEqual(kw["min_lat"], 10.0)
        self.assertEqual(kw["min_lon"], 20.0)
        self.assertEqual(kw["max_lat"], 11.0)
        self.assertEqual(kw["max_lon"], 21.0)
        # None of these values should appear raw in the Cypher string
        cypher = session.run.call_args[0][0]
        self.assertNotIn("10.0", cypher)
        self.assertNotIn("20.0", cypher)

    def test_find_in_radius_uses_point_distance(self):
        """The spatial radius query must use point.distance()."""
        self.assertIn("point.distance", self.mod._FIND_IN_RADIUS)
        self.assertIn("WGS-84", self.mod._FIND_IN_RADIUS)

    def test_find_in_radius_passes_lat_lon_as_params(self):
        session = _make_session([])
        self.mod.find_in_radius(session, 48.85, 2.35, 500.0, limit=10)
        _, kw = session.run.call_args
        self.assertEqual(kw["lat"], 48.85)
        self.assertEqual(kw["lon"], 2.35)
        self.assertEqual(kw["radius_m"], 500.0)
        cypher = session.run.call_args[0][0]
        self.assertNotIn("48.85", cypher)

    def test_get_finding_history_uses_wgs84(self):
        self.assertIn("WGS-84", self.mod._GET_FINDING_HISTORY)

    def test_service_unavailable_in_finding_raises_runtime(self):
        session = MagicMock()
        session.run.side_effect = ServiceUnavailable("down")
        with self.assertRaises(RuntimeError):
            self.mod.get_finding(session, "d1")


# ===========================================================================
# 3. scene_repository
# ===========================================================================

class TestSceneRepository(unittest.TestCase):

    def setUp(self):
        import app.repositories.scene_repository as mod
        self.mod = mod

    def test_merge_scene_returns_scene_id(self):
        record = _make_record(scene_id="sc-1")
        session = _make_session([record])
        result = self.mod.merge_scene(session, {"scene_id": "sc-1"})
        self.assertEqual(result, "sc-1")

    def test_merge_scene_uses_merge_cypher(self):
        self.assertIn("MERGE", self.mod._MERGE_SCENE)

    def test_list_scenes_for_scan_passes_scan_id(self):
        session = _make_session([])
        self.mod.list_scenes_for_scan(session, "scan-99")
        _, kw = session.run.call_args
        self.assertEqual(kw["scan_id"], "scan-99")


# ===========================================================================
# 4. evidence_repository
# ===========================================================================

class TestEvidenceRepository(unittest.TestCase):

    def setUp(self):
        import app.repositories.evidence_repository as mod
        self.mod = mod

    def test_create_evidence_asset_returns_asset_id(self):
        record = _make_record(asset_id="ea-1")
        session = _make_session([record])
        result = self.mod.create_evidence_asset(session, {"asset_id": "ea-1"})
        self.assertEqual(result, "ea-1")

    def test_link_evidence_runs_merge(self):
        session = _make_session([])
        self.mod.link_evidence_to_finding(session, "d1", "ea-1")
        session.run.assert_called_once()
        _, kw = session.run.call_args
        self.assertEqual(kw["detection_id"], "d1")
        self.assertEqual(kw["asset_id"], "ea-1")
        cypher = session.run.call_args[0][0]
        self.assertIn("MERGE", cypher)


# ===========================================================================
# 5. case_repository
# ===========================================================================

class TestCaseRepository(unittest.TestCase):

    def setUp(self):
        import app.repositories.case_repository as mod
        self.mod = mod

    def test_create_case_returns_case_id(self):
        record = _make_record(case_id="case-1")
        session = _make_session([record])
        result = self.mod.create_case(session, {"case_id": "case-1", "title": "Test"})
        self.assertEqual(result, "case-1")

    def test_add_observation_duplicate_prevention(self):
        """
        add_observation_to_case should return False when the relationship
        already exists (record is None → no new rel created).
        """
        session = _make_session([])  # single() returns None → not added
        result = self.mod.add_observation_to_case(session, "case-1", "d1")
        self.assertFalse(result)

    def test_add_observation_new_link_returns_true(self):
        """
        add_observation_to_case should return True when the MERGE creates a
        new relationship.
        """
        record = _make_record(added=True)
        session = _make_session([record])
        result = self.mod.add_observation_to_case(session, "case-1", "d2")
        self.assertTrue(result)

    def test_case_cypher_uses_merge(self):
        self.assertIn("MERGE", self.mod._CREATE_CASE)

    def test_list_observations_passes_case_id(self):
        session = _make_session([])
        self.mod.list_observations_for_case(session, "case-99")
        _, kw = session.run.call_args
        self.assertEqual(kw["case_id"], "case-99")


# ===========================================================================
# 6. region_repository
# ===========================================================================

class TestRegionRepository(unittest.TestCase):

    def setUp(self):
        import app.repositories.region_repository as mod
        self.mod = mod

    def test_merge_region_returns_region_id(self):
        record = _make_record(region_id="reg-1")
        session = _make_session([record])
        result = self.mod.merge_region(session, {"region_id": "reg-1", "name": "Area"})
        self.assertEqual(result, "reg-1")

    def test_get_region_none_when_missing(self):
        session = _make_session([])
        result = self.mod.get_region(session, "no-such-region")
        self.assertIsNone(result)

    def test_get_region_graph_returns_expected_shape(self):
        """get_region_graph always returns a dict with region/scans/findings."""
        session = _make_session([])
        result = self.mod.get_region_graph(session, "reg-x")
        self.assertIn("region", result)
        self.assertIn("scans", result)
        self.assertIn("findings", result)


# ===========================================================================
# 7. No f-string / .format() injection in any Cypher constant
# ===========================================================================

class TestNoCypherInjection(unittest.TestCase):
    """
    Parse the AST of each repository module and assert that no f-string
    (JoinedStr) is used in module-level string assignments whose name
    starts with underscore (our Cypher constants).
    """

    MODULES = [
        "app.repositories.scan_repository",
        "app.repositories.finding_repository",
        "app.repositories.scene_repository",
        "app.repositories.evidence_repository",
        "app.repositories.case_repository",
        "app.repositories.region_repository",
    ]

    def _get_source(self, module_name: str) -> str:
        mod = importlib.import_module(module_name)
        return inspect.getsource(mod)

    def _assert_no_fstring_in_constants(self, module_name: str):
        source = self._get_source(module_name)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            # Look for assignments of module-level Cypher constants
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.startswith("_"):
                        # The value must NOT be a JoinedStr (f-string)
                        if isinstance(node.value, ast.JoinedStr):
                            self.fail(
                                f"f-string used in Cypher constant {target.id!r} in {module_name}"
                            )

    def test_no_fstring_in_scan_constants(self):
        self._assert_no_fstring_in_constants("app.repositories.scan_repository")

    def test_no_fstring_in_finding_constants(self):
        self._assert_no_fstring_in_constants("app.repositories.finding_repository")

    def test_no_fstring_in_scene_constants(self):
        self._assert_no_fstring_in_constants("app.repositories.scene_repository")

    def test_no_fstring_in_evidence_constants(self):
        self._assert_no_fstring_in_constants("app.repositories.evidence_repository")

    def test_no_fstring_in_case_constants(self):
        self._assert_no_fstring_in_constants("app.repositories.case_repository")

    def test_no_fstring_in_region_constants(self):
        self._assert_no_fstring_in_constants("app.repositories.region_repository")


if __name__ == "__main__":
    unittest.main()
