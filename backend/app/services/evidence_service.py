"""Evidence storage service for GeoSentinelAI.

Handles evidence asset storage abstraction with content-addressable SHA-256
hashing, local file persistence, and metadata recording in Neo4j.
"""
from __future__ import annotations

import abc
import hashlib
import logging
import mimetypes
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
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


class CloudflareR2Storage(EvidenceStorage):
    """S3-compatible durable storage for Cloudflare R2 buckets."""

    def __init__(
        self,
        bucket: str,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        client: Any | None = None,
    ) -> None:
        self.bucket = bucket
        if client is None:
            try:
                import boto3
            except ImportError as exc:
                raise RuntimeError("Install boto3 to use Cloudflare R2 evidence storage.") from exc
            client = boto3.client(
                "s3",
                endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
                region_name="auto",
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
            )
        self.client = client

    @classmethod
    def from_environment(cls) -> CloudflareR2Storage:
        required = {
            "CLOUDFLARE_R2_ACCOUNT_ID": os.getenv("CLOUDFLARE_R2_ACCOUNT_ID"),
            "CLOUDFLARE_R2_ACCESS_KEY_ID": os.getenv("CLOUDFLARE_R2_ACCESS_KEY_ID"),
            "CLOUDFLARE_R2_SECRET_ACCESS_KEY": os.getenv("CLOUDFLARE_R2_SECRET_ACCESS_KEY"),
            "CLOUDFLARE_R2_BUCKET": os.getenv("CLOUDFLARE_R2_BUCKET"),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise RuntimeError(
                "Cloudflare R2 is selected but required settings are missing: "
                + ", ".join(missing)
            )
        return cls(
            bucket=required["CLOUDFLARE_R2_BUCKET"] or "",
            account_id=required["CLOUDFLARE_R2_ACCOUNT_ID"] or "",
            access_key_id=required["CLOUDFLARE_R2_ACCESS_KEY_ID"] or "",
            secret_access_key=required["CLOUDFLARE_R2_SECRET_ACCESS_KEY"] or "",
        )

    def store_bytes(self, data: bytes, filename: str) -> tuple[str, str, int]:
        sha256 = hashlib.sha256(data).hexdigest()
        safe_filename = re.sub(r"[^A-Za-z0-9._-]", "-", Path(filename).name) or "evidence.bin"
        key = f"evidence/{sha256[:2]}/{sha256}/{safe_filename}"
        content_type = mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return f"r2://{self.bucket}/{key}", sha256, len(data)

    def read_bytes(self, uri: str) -> bytes:
        parsed = urlparse(uri)
        if parsed.scheme != "r2" or parsed.netloc != self.bucket or not parsed.path.strip("/"):
            raise ValueError("Evidence URI does not identify an object in the configured R2 bucket.")
        response = self.client.get_object(Bucket=self.bucket, Key=parsed.path.lstrip("/"))
        return response["Body"].read()


def get_default_storage() -> EvidenceStorage:
    provider = os.getenv("EVIDENCE_STORAGE_PROVIDER", "local").strip().lower()
    if provider == "local":
        return LocalEvidenceStorage()
    if provider in {"cloudflare-r2", "r2"}:
        return CloudflareR2Storage.from_environment()
    raise RuntimeError(f"Unsupported evidence storage provider: {provider}")


def read_evidence_bytes(uri: str) -> bytes:
    if uri.startswith("r2://"):
        return CloudflareR2Storage.from_environment().read_bytes(uri)
    if uri.startswith("/media/evidence/"):
        return LocalEvidenceStorage().read_bytes(uri)
    raise ValueError("Unsupported evidence URI.")


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
