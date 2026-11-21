"""Evidence storage service for GeoSentinelAI.

Handles evidence asset storage abstraction with content-addressable SHA-256
hashing, local file persistence, and metadata recording in Neo4j.
"""
from __future__ import annotations

import abc
import hashlib
import logging
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "data" / "evidence"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


class EvidenceStorage(abc.ABC):
    """Abstract interface for evidence asset storage."""

    @abc.abstractmethod
    def store_bytes(self, data: bytes, filename: str) -> tuple[str, str, int]:
        """Store raw bytes and return (uri, sha256_hex, file_size_bytes)."""

    @abc.abstractmethod
    def read_bytes(self, uri: str) -> bytes:
        """Retrieve bytes by storage URI."""


class LocalEvidenceStorage(EvidenceStorage):
    """Local filesystem implementation of EvidenceStorage."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or EVIDENCE_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def store_bytes(self, data: bytes, filename: str) -> tuple[str, str, int]:
        sha256 = hashlib.sha256(data).hexdigest()
        file_size = len(data)
        ext = Path(filename).suffix or ".bin"
        safe_filename = f"{sha256[:16]}_{Path(filename).stem}{ext}"
        target_path = self.base_dir / safe_filename
        if not target_path.exists():
            target_path.write_bytes(data)
        uri = f"/media/evidence/{safe_filename}"
        return uri, sha256, file_size

    def read_bytes(self, uri: str) -> bytes:
        filename = Path(uri).name
        target_path = self.base_dir / filename
        if not target_path.exists():
            raise FileNotFoundError(f"Evidence file not found: {uri}")
        return target_path.read_bytes()


_default_storage = LocalEvidenceStorage()


def get_default_storage() -> EvidenceStorage:
    return _default_storage


def register_image_asset(
    storage: EvidenceStorage,
    driver: Any,
    detection_id: str,
    file_bytes: bytes,
    filename: str,
    asset_type: str = "diff_image",
) -> str:
    """Store asset file and link EvidenceAsset node to FindingObservation."""
    asset_id = f"asset-{uuid4().hex}"
    uri, sha256, file_size = storage.store_bytes(file_bytes, filename)
    media_type, _ = mimetypes.guess_type(filename)
    media_type = media_type or "application/octet-stream"
    now = datetime.now(timezone.utc).isoformat()

    cypher = """
    MERGE (a:EvidenceAsset {asset_id: $asset_id})
    ON CREATE SET
        a.uri        = $uri,
        a.sha256     = $sha256,
        a.media_type = $media_type,
        a.file_size  = $file_size,
        a.asset_type = $asset_type,
        a.created_at = $created_at
    WITH a
    MATCH (f:FindingObservation {detection_id: $detection_id})
    MERGE (f)-[:SUPPORTED_BY]->(a)
    RETURN a.asset_id AS asset_id
    """
    try:
        with driver.session() as session:
            session.run(
                cypher,
                asset_id=asset_id,
                uri=uri,
                sha256=sha256,
                media_type=media_type,
                file_size=file_size,
                asset_type=asset_type,
                created_at=now,
                detection_id=detection_id,
            )
    except Exception as exc:
        logger.warning("Failed to link EvidenceAsset to FindingObservation in Neo4j: %s", exc)
    return asset_id
