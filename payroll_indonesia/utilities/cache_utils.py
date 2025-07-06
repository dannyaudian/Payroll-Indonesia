# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-05 by dannyaudian

import frappe
from frappe.utils import now_datetime, add_to_date
import hashlib
import json
import functools
from typing import Any, List, Optional, Dict, Union

__all__ = [
    "get_cache",
    "set_cache",
    "delete_cache",
    "clear_pattern",
    "get_cached_value",
    "cache_value",
    "clear_cache",
    "clear_all_caches",
    "memoize_with_ttl",
]


# Main cache implementation as a class
class CacheManager:
    """Cache manager for Payroll Indonesia module with namespace support"""

    # Cache storage
    _storage = {}
    _clear_timestamps = {}

    # Default TTL values for different cache types
    DEFAULT_TTL = {
        "ter_rate": 1800,  # 30 minutes
        "ytd": 3600,  # 1 hour
        "ptkp_mapping": 3600,  # 1 hour
        "tax_settings": 3600,  # 1 hour
        "employee": 3600,  # 1 hour
        "fiscal_year": 86400,  # 24 hours
        "salary_slip": 3600,  # 1 hour
        "default": 1800,  # 30 minutes (fallback)
    }

    @classmethod
    def get(cls, cache_key: str, ttl: Optional[int] = None) -> Any:
        """
        Get a value from cache with expiry checking

        Args:
            cache_key (str): Cache key
            ttl (int, optional): Time-to-live in seconds

        Returns:
            any: Cached value or None if not found or expired
        """
        # Get cache namespace from key prefix
        namespace = cls._get_namespace_from_key(cache_key)

        # Check if namespace needs clearing
        cls._check_and_clear_namespace_if_needed(namespace)

        # Normalize key to handle complex objects
        if not isinstance(cache_key, str):
            cache_key = cls._normalize_key(cache_key)

        # Return value if present, None otherwise
        entry = cls._storage.get(cache_key)
        if not entry:
            return None

        # Check if entry has expired
        now = now_datetime()
        if (now - entry.get("timestamp")).total_seconds() > entry.get(
            "ttl", cls.DEFAULT_TTL["default"]
        ):
            del cls._storage[cache_key]  # FIXED: was del cls._storage[key]
            return None

        # Log hit if debug mode is on
        if frappe.conf.get("developer_mode"):
            frappe.logger().debug(f"Cache hit for key: {cache_key}")

        return entry.get("value")

    @classmethod
    def set(cls, cache_key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Store a value in cache with expiry time

        Args:
            cache_key (str): Cache key
            value (any): Value to cache
            ttl (int, optional): Time-to-live in seconds
        """
        if value is None:
            # Don't cache None values
            return

        # Get cache namespace from key prefix
        namespace = cls._get_namespace_from_key(cache_key)

        # Get default TTL for this namespace
        if ttl is None:
            ttl = cls.DEFAULT_TTL.get(namespace, cls.DEFAULT_TTL["default"])

        # Normalize key to handle complex objects
        if not isinstance(cache_key, str):
            cache_key = cls._normalize_key(cache_key)

        # Store with timestamp and ttl
        cls._storage[cache_key] = {
            "value": value,
            "timestamp": now_datetime(),
            "ttl": ttl,
            "namespace": namespace,
        }

        # Log if debug mode is on
        if frappe.conf.get("developer_mode"):
            frappe.logger().debug(
                f"Cached value for key: {cache_key}, namespace: {namespace}, TTL: {ttl}s"
            )

    @classmethod
    def delete(cls, cache_key: str) -> None:
        """
        Delete a cache entry by key

        Args:
            cache_key (str): Cache key
        """
        if not isinstance(cache_key, str):
            cache_key = cls._normalize_key(cache_key)
        if cache_key in cls._storage:
            del cls._storage[cache_key]
            if frappe.conf.get("developer_mode"):
                frappe.logger().debug(f"Deleted cache for key: {cache_key}")

    @classmethod
    def clear(cls, prefix: Optional[str] = None) -> Union[int, None]:
        """
        Clear all cache entries with a specific prefix or namespace

        Args:
            prefix (str, optional): Key prefix to clear. If None, clear all caches.

        Returns:
            int or None: Number of keys cleared, or None if all cleared
        """
        if prefix is None:
            # Clear all caches
            count = len(cls._storage)
            cls._storage.clear()
            cls._clear_timestamps.clear()
            frappe.logger().info("All caches cleared")
            return count

        # Normalize prefix for exact matches
        if not prefix.endswith(":") and ":" in prefix:
            prefix += ":"

        # Find namespace from prefix
        namespace = cls._get_namespace_from_key(prefix)

        # Clear all entries with matching prefix
        keys_to_delete = [k for k in cls._storage if k.startswith(prefix)]
        for key in keys_to_delete:
            del cls._storage[key]

        # Update clear timestamp for namespace
        cls._clear_timestamps[namespace] = now_datetime()

        frappe.logger().info(
            f"Cache cleared for prefix: {prefix}, keys cleared: {len(keys_to_delete)}"
        )
        return len(keys_to_delete)

    @classmethod
    def clear_all(cls) -> None:
        """Clear all caches related to payroll calculations"""
        # Clear our unified cache
        cls._storage.clear()
        cls._clear_timestamps.clear()

        # Also clear frappe caches for tax and payroll related keys
        cache_keys = [
            "tax_calculator_cache",
            "ter_calculator_cache",
            "ptkp_mapping",
            "ytd_tax_data",
        ]

        for key in cache_keys:
            frappe.cache().delete_key(key)

        frappe.logger().info("All payroll caches cleared")

    @classmethod
    def _get_namespace_from_key(cls, key: str) -> str:
        """
        Extract namespace from a cache key

        Args:
            key (str): Cache key

        Returns:
            str: Namespace (first part before colon or "default")
        """
        if not isinstance(key, str):
            return "default"

        if ":" in key:
            return key.split(":", 1)[0]

        return "default"

    @classmethod
    def _check_and_clear_namespace_if_needed(cls, namespace: str) -> None:
        """
        Check if a namespace needs clearing based on TTL

        Args:
            namespace (str): Cache namespace
        """
        now = now_datetime()
        last_clear = cls._clear_timestamps.get(namespace)

        if last_clear is None:
            # First time - set timestamp
            cls._clear_timestamps[namespace] = now
            return

        namespace_ttl = cls.DEFAULT_TTL.get(namespace, cls.DEFAULT_TTL["default"])

        if (now - last_clear).total_seconds() > namespace_ttl:
            # Clear all entries for this namespace
            keys_to_delete = [k for k, v in cls._storage.items() if v.get("namespace") == namespace]
            for key in keys_to_delete:
                del cls._storage[key]

            # Update timestamp
            cls._clear_timestamps[namespace] = now
            frappe.logger().debug(
                f"Auto-cleared cache namespace: {namespace}, keys: {len(keys_to_delete)}"
            )

    @staticmethod
    def _normalize_key(obj: Any) -> str:
        """
        Normalize complex objects into stable string keys

        Args:
            obj: Any object to use as a cache key

        Returns:
            str: Normalized string key
        """
        if isinstance(obj, str):
            return obj

        try:
            # Try to convert to JSON and hash
            json_str = json.dumps(obj, sort_keys=True)
            return hashlib.md5(json_str.encode()).hexdigest()
        except (TypeError, ValueError):
            # Fallback to string representation
            return hashlib.md5(str(obj).encode()).hexdigest()


# --------- Public cache helpers (frappe + memory fallback) ----------


def get_cache(cache_key, ttl=None):
    """
    Get a value from frappe.cache(), fallback to in-memory if unavailable.
    """
    try:
        value = frappe.cache().get_value(cache_key)
        if value is not None:
            if frappe.conf.get("developer_mode"):
                frappe.logger().debug(f"frappe.cache() hit for key: {cache_key}")
            return value
    except Exception:
        pass
    # fallback in-memory
    return CacheManager.get(cache_key, ttl)


def set_cache(cache_key, value, ttl=None):
    """
    Set a value in frappe.cache() and in-memory.
    """
    try:
        frappe.cache().set_value(cache_key, value)
        if frappe.conf.get("developer_mode"):
            frappe.logger().debug(f"frappe.cache() set for key: {cache_key}")
    except Exception:
        pass
    CacheManager.set(cache_key, value, ttl)


def delete_cache(cache_key):
    """
    Delete a value from frappe.cache() and from in-memory.
    """
    try:
        frappe.cache().delete_key(cache_key)
        if frappe.conf.get("developer_mode"):
            frappe.logger().debug(f"frappe.cache() delete for key: {cache_key}")
    except Exception:
        pass
    CacheManager.delete(cache_key)


def clear_pattern(pattern: str) -> Union[int, None]:
    """
    Delete Redis keys based on a wildcard pattern using frappe.cache().delete_pattern.
    Also clears in-memory entries matching the pattern.
    """
    if not pattern:
        return None
    deleted_count = None
    try:
        deleted_count = frappe.cache().delete_pattern(pattern)
        if frappe.conf.get("developer_mode"):
            frappe.logger().info(f"frappe.cache().delete_pattern run for: {pattern}")
    except Exception:
        pass
    # fallback: clear in-memory by pattern
    try:
        count = clear_cache(pattern)
        if deleted_count is not None:
            return deleted_count + (count or 0)
        return count
    except Exception:
        return deleted_count


# --------- Memoization decorator ----------


def memoize_with_ttl(ttl=None, namespace=None):
    """
    Decorator to memoize a function with TTL (time-to-live) caching

    Args:
        ttl (int, optional): Time-to-live in seconds
        namespace (str, optional): Cache namespace to use

    Returns:
        function: Decorated function with caching
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Generate a cache key from function name, args and kwargs
            key_parts = [func.__module__, func.__name__]

            # Add args to key
            for arg in args:
                key_parts.append(str(arg))

            # Add sorted kwargs to key for stable hashing
            sorted_kwargs = sorted(kwargs.items())
            for k, v in sorted_kwargs:
                key_parts.append(f"{k}:{v}")

            # Generate the cache key
            cache_key = ":".join(key_parts)

            # Set namespace prefix
            if namespace:
                cache_key = f"{namespace}:{cache_key}"

            # Try to get value from cache
            cached_result = get_cache(cache_key, ttl)
            if cached_result is not None:
                return cached_result

            # Calculate and cache result
            result = func(*args, **kwargs)
            set_cache(cache_key, result, ttl)
            return result

        return wrapper

    return decorator


# --------- Legacy compatibility public API ---------


def get_cached_value(cache_key, ttl=None):
    """
    Get a value from cache with expiry checking

    Args:
        cache_key (str): Cache key
        ttl (int, optional): Time-to-live in seconds

    Returns:
        any: Cached value or None if not found or expired
    """
    return get_cache(cache_key, ttl)


def cache_value(cache_key, value, ttl=None):
    """
    Store a value in cache with expiry time

    Args:
        cache_key (str): Cache key
        value (any): Value to cache
        ttl (int, optional): Time-to-live in seconds
    """
    set_cache(cache_key, value, ttl)


def clear_cache(prefix=None):
    """
    Clear all cache entries with a specific prefix or namespace

    Args:
        prefix (str, optional): Key prefix to clear. If None, clear all caches.
    """
    return CacheManager.clear(prefix)


def clear_all_caches():
    """Clear all caches related to payroll calculations"""
    CacheManager.clear_all()


# --------- Minimal self-test ---------
if __name__ == "__main__":
    import time

    print("Testing CacheManager and helpers...")

    set_cache("test:key1", "val1", ttl=2)
    assert get_cache("test:key1") == "val1"
    time.sleep(2.2)
    assert get_cache("test:key1") is None

    set_cache("test:key2", "val2")
    assert get_cache("test:key2") == "val2"
    delete_cache("test:key2")
    assert get_cache("test:key2") is None

    set_cache("pattern:test1", 1)
    set_cache("pattern:test2", 2)
    clear_pattern("pattern:*")
    assert get_cache("pattern:test1") is None
    assert get_cache("pattern:test2") is None

    print("All cache helper tests passed.")
