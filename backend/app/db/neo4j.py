"""
Neo4j driver singleton for GeoSentinelAI.

Usage:
    from app.db.neo4j import get_session, verify_connectivity

    with get_session() as session:
        result = session.run("MATCH (n) RETURN count(n) AS cnt")
        ...
"""
from __future__ import annotations

import logging
import socket
from urllib.parse import urlparse
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Generator

from neo4j import GraphDatabase, Driver, AsyncGraphDatabase
from neo4j.exceptions import (
    AuthError,
    ServiceUnavailable,
    ConfigurationError,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class DatabaseSettings(BaseSettings):
    """Neo4j connection settings — read from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="NEO4J_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    uri: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: str = "neo4j"
    database: str = "neo4j"

    # Connection pool / timeout config
    max_connection_pool_size: int = 50
    connection_timeout: float = 5.0
    max_transaction_retry_time: float = 5.0
    connection_acquisition_timeout: float = 10.0

    @property
    def uses_tls(self) -> bool:
        """True when the URI uses encrypted transport (AuraDB bolt+s:// etc.)."""
        return self.uri.startswith(("bolt+s://", "bolt+ssc://", "neo4j+s://", "neo4j+ssc://"))


# Lazy singleton — created on first access, never during import
neo4j_settings = DatabaseSettings()

# ---------------------------------------------------------------------------
# Driver singleton
# ---------------------------------------------------------------------------

_driver: Driver | None = None


def get_driver() -> Driver:
    """Return the shared Neo4j driver, initialising it on the first call.

    The driver is thread-safe and should be reused across the application
    lifetime. It is NOT connected yet — sessions are opened lazily.
    """
    global _driver
    if _driver is None:
        _driver = _build_driver()
    return _driver


def _build_driver() -> Driver:
    """Construct (but do not connect) the Neo4j driver from current settings."""
    cfg = neo4j_settings

    # Encrypted URIs (bolt+s, neo4j+s) use TLS automatically; plain URIs need
    # explicit trust decisions. We surface the scheme choice to the operator
    # and never log the password.
    logger.info(
        "Creating Neo4j driver: uri=%s user=%s database=%s tls=%s",
        cfg.uri,
        cfg.username,
        # password intentionally omitted
        cfg.database,
        cfg.uses_tls,
    )

    driver = GraphDatabase.driver(
        cfg.uri,
        auth=(cfg.username, cfg.password),
        max_connection_pool_size=cfg.max_connection_pool_size,
        connection_timeout=cfg.connection_timeout,
        max_transaction_retry_time=cfg.max_transaction_retry_time,
        connection_acquisition_timeout=cfg.connection_acquisition_timeout,
    )
    return driver


def close_driver() -> None:
    """Close and discard the shared driver. Safe to call multiple times."""
    global _driver
    if _driver is not None:
        try:
            _driver.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error while closing Neo4j driver: %s", exc)
        finally:
            _driver = None
        logger.info("Neo4j driver closed.")


@contextmanager
def get_session(**kwargs: Any) -> Generator[Any, None, None]:
    """Context manager that opens a *new* session and closes it afterwards.

    One session per operation — never share sessions between threads or requests.

    Example::

        with get_session() as session:
            session.run("CREATE (n:Test) RETURN n")
    """
    driver = get_driver()
    database = kwargs.pop("database", neo4j_settings.database)
    session = driver.session(database=database, **kwargs)
    try:
        yield session
    finally:
        session.close()


def _is_port_reachable(uri: str, timeout: float = 0.5) -> bool:
    """Fast check whether target host and port are listening."""
    if not uri or "your-instance" in uri or "example.com" in uri:
        return False
    try:
        # Handle schemes like bolt://, bolt+s://, neo4j+s://
        clean_uri = uri.replace("bolt+s://", "http://").replace("bolt://", "http://").replace("neo4j+s://", "http://").replace("neo4j://", "http://")
        parsed = urlparse(clean_uri)
        host = parsed.hostname or "localhost"
        port = parsed.port or 7687
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def verify_connectivity() -> dict[str, Any]:
    """Verify that the database is reachable and return basic server info.

    Returns a dict with keys ``status`` (``"ok"`` or ``"error"``), and on
    success ``server_info`` / ``database``.  Never raises.
    """
    if not _is_port_reachable(neo4j_settings.uri, timeout=0.5):
        return {
            "status": "error",
            "error": "service_unavailable",
            "detail": f"Neo4j endpoint {neo4j_settings.uri} is not reachable",
        }

    try:
        driver = get_driver()
        driver.verify_connectivity()
        return {
            "status": "ok",
            "database": neo4j_settings.database,
            "uri": neo4j_settings.uri,
        }
    except AuthError as exc:
        logger.error("Neo4j authentication failed — check NEO4J_USERNAME / NEO4J_PASSWORD")
        return {"status": "error", "error": "authentication_failed", "detail": str(exc)}
    except ServiceUnavailable as exc:
        logger.warning("Neo4j service unavailable: %s", exc)
        return {"status": "error", "error": "service_unavailable", "detail": str(exc)}
    except ConfigurationError as exc:
        logger.error("Neo4j configuration error: %s", exc)
        return {"status": "error", "error": "configuration_error", "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.error("Neo4j connectivity check failed: %s", exc)
        return {"status": "error", "error": "unknown", "detail": str(exc)}


# ---------------------------------------------------------------------------
# FastAPI lifespan helpers
# ---------------------------------------------------------------------------


@asynccontextmanager
async def neo4j_lifespan(_app: Any):  # type: ignore[misc]
    """AsyncContextManager suitable for FastAPI ``lifespan=`` parameter.

    Usage in main.py::

        from app.db.neo4j import neo4j_lifespan

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            async with neo4j_lifespan(app):
                yield

        app = FastAPI(lifespan=lifespan)
    """
    logger.info("GeoSentinelAI startup — initialising Neo4j driver …")
    # Eagerly build driver so startup problems surface immediately
    try:
        get_driver()
        info = verify_connectivity()
        if info["status"] == "ok":
            logger.info("Neo4j connected: database=%s", info.get("database"))
        else:
            logger.warning("Neo4j not reachable at startup — running in degraded mode: %s", info)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Neo4j initialisation error at startup (non-fatal): %s", exc)

    try:
        yield
    finally:
        logger.info("GeoSentinelAI shutdown — closing Neo4j driver …")
        close_driver()


__all__ = [
    "DatabaseSettings",
    "neo4j_settings",
    "get_driver",
    "close_driver",
    "get_session",
    "verify_connectivity",
    "neo4j_lifespan",
]
