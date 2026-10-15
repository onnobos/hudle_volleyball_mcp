"""Local Persistent Caching for Hudl MCP using diskcache & platformdirs.

Caches historical match play-by-play and box scores for 7+ days (expire=604800)
and live/season schedule and team endpoints for 15 minutes (expire=900) to protect
user accounts and minimize redundant requests across LLM tool loops.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional
import diskcache
import platformdirs

logger = logging.getLogger(__name__)

# TTL Policies in Seconds
TTL_HISTORICAL_MATCH: int = 604800  # 7 Days
TTL_SCHEDULE_TEAM: int = 900        # 15 Minutes


def get_cache_directory() -> Path:
    """Determine the optimal cache directory respecting OS conventions and sandbox constraints."""
    custom_dir = os.getenv("HUDL_CACHE_DIR")
    if custom_dir:
        p = Path(custom_dir).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    # Standard OS user cache directory
    try:
        user_cache = Path(platformdirs.user_cache_dir("hudl-volleyball-mcp")) / "cache"
        user_cache.mkdir(parents=True, exist_ok=True)
        return user_cache
    except (PermissionError, OSError):
        # Fallback to project root .cache for sandboxed or containerized environments
        project_cache = Path(__file__).resolve().parents[2] / ".cache" / "hudl_mcp"
        project_cache.mkdir(parents=True, exist_ok=True)
        return project_cache


_CACHE_INSTANCE: Optional[diskcache.Cache] = None


def get_cache() -> diskcache.Cache:
    """Retrieve or initialize the global diskcache.Cache singleton instance."""
    global _CACHE_INSTANCE
    if _CACHE_INSTANCE is None:
        cache_dir = get_cache_directory()
        _CACHE_INSTANCE = diskcache.Cache(str(cache_dir))
    return _CACHE_INSTANCE


def compute_cache_key(prefix: str, payload: Any) -> str:
    """Generate a deterministic SHA-256 cache key for an endpoint and its parameters."""
    if isinstance(payload, (dict, list)):
        serialized = json.dumps(payload, sort_keys=True, default=str)
    else:
        serialized = str(payload)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def get_cached_response(key: str) -> Optional[Any]:
    """Retrieve an item from disk cache if still valid."""
    try:
        cache = get_cache()
        return cache.get(key)
    except Exception as exc:
        logger.debug(f"Cache get error for key {key}: {exc}")
        return None


def set_cached_response(key: str, value: Any, expire_seconds: int) -> None:
    """Store an item in disk cache with an expiration TTL."""
    try:
        cache = get_cache()
        cache.set(key, value, expire=expire_seconds)
    except Exception as exc:
        logger.debug(f"Cache set error for key {key}: {exc}")


def clear_all_cache() -> None:
    """Flush and clear all entries in the disk cache."""
    try:
        cache = get_cache()
        cache.clear()
    except Exception as exc:
        logger.debug(f"Cache clear error: {exc}")
