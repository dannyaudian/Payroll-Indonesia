# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-02 17:18:47 by dannyaudian

import frappe
from frappe.utils import now_datetime, add_to_date
import hashlib
import json
import functools
from typing import Any, List, Optional, Dict, Union


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
            del cls._storage[key]
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
    def clear(cls, prefix: Optional[str] = None) -> None:
        """
        Clear all cache entries with a specific prefix or namespace

        Args:
            prefix (str, optional): Key prefix to clear. If None, clear all caches.
        """
        if prefix is None:
            # Clear all caches
            cls._storage.clear()
            cls._clear_timestamps.clear()
            frappe.logger().info("All caches cleared")
            return

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


# Create decorator for memoization with TTL
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
            cached_result = get_cached_value(cache_key, ttl)
            if cached_result is not None:
                return cached_result

            # Calculate and cache result
            result = func(*args, **kwargs)
            cache_value(cache_key, result, ttl)
            return result

        return wrapper

    return decorator


# Schedule a background job to clear all caches
def schedule_cache_clearing(minutes=30):
    """
    Schedule a background job to clear all caches after specified minutes

    Args:
        minutes (int): Minutes after which to clear caches
    """
    try:
        # Use enqueue to schedule the job
        frappe.enqueue(
            clear_all_caches,
            queue="long",
            is_async=True,
            job_name="clear_payroll_caches",
            enqueue_after=add_to_date(now_datetime(), minutes=minutes),
        )
        frappe.logger().debug(f"Scheduled cache clearing in {minutes} minutes")
        return True
    except Exception as e:
        frappe.logger().error(f"Error scheduling cache clearing: {str(e)}")
        return False


# Public API functions that use the CacheManager but maintain the same interface
def get_cached_value(cache_key, ttl=None):
    """
    Get a value from cache with expiry checking

    Args:
        cache_key (str): Cache key
        ttl (int, optional): Time-to-live in seconds

    Returns:
        any: Cached value or None if not found or expired
    """
    return CacheManager.get(cache_key, ttl)


def cache_value(cache_key, value, ttl=None):
    """
    Store a value in cache with expiry time

    Args:
        cache_key (str): Cache key
        value (any): Value to cache
        ttl (int, optional): Time-to-live in seconds
    """
    CacheManager.set(cache_key, value, ttl)


def clear_cache(prefix=None):
    """
    Clear all cache entries with a specific prefix or namespace

    Args:
        prefix (str, optional): Key prefix to clear. If None, clear all caches.
    """
    return CacheManager.clear(prefix)


def clear_pattern(pattern: str) -> Union[int, None]:
    """
    Delete Redis keys based on a wildcard pattern

    This function searches for Redis keys matching the provided pattern and deletes them.
    It uses the scan_iter command to find matching keys, which is safe for production
    environments as it doesn't block the Redis server.

    Args:
        pattern (str): Redis wildcard pattern to match keys (e.g., "user:*:profile")
                      See Redis documentation for pattern syntax

    Returns:
        Union[int, None]: Number of keys deleted or None if no keys were found/deleted

    Examples:
        >>> clear_pattern("user:*:profile")  # Deletes all user profile keys
        >>> clear_pattern("cache:payroll:*")  # Deletes all payroll cache keys
    """
    if not pattern:
        return None

    try:
        # Get Redis connection from Frappe
        redis_connection = frappe.cache().redis

        if not redis_connection:
            # If Redis is not available, try to clear from local CacheManager
            return clear_cache(pattern)

        # Use scan_iter to find matching keys safely (non-blocking)
        keys_to_delete: List[str] = []
        for key in redis_connection.scan_iter(pattern):
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            keys_to_delete.append(key)

        # If keys found, delete them
        deleted_count = 0
        if keys_to_delete:
            # Delete in batches of 1000 to avoid blocking Redis
            batch_size = 1000
            for i in range(0, len(keys_to_delete), batch_size):
                batch = keys_to_delete[i : i + batch_size]
                deleted_count += redis_connection.delete(*batch)

        # Also try to clear from CacheManager for completeness
        # This ensures both Redis and local cache are cleared
        try:
            clear_cache(pattern)
        except Exception:
            # Ignore errors from local cache clearing
            pass

        return deleted_count if deleted_count > 0 else None

    except Exception as e:
        # Log the error but don't raise it
        frappe.logger().error(f"Error clearing Redis pattern '{pattern}': {str(e)}")
        return None


def clear_all_caches():
    """Clear all caches related to payroll calculations"""
    CacheManager.clear_all()


# Backward compatibility functions for older code
def get_ter_rate_cache():
    """
    Legacy function for backwards compatibility

    Returns:
        dict: Empty dict, as cache storage is now handled internally
    """
    frappe.logger().warning(
        "Deprecated: get_ter_rate_cache() called - use get_cached_value() instead"
    )
    return {}


def get_ytd_cache():
    """Legacy function for backwards compatibility"""
    frappe.logger().warning("Deprecated: get_ytd_cache() called - use get_cached_value() instead")
    return {}


def get_ptkp_mapping_cache():
    """Legacy function for backwards compatibility"""
    frappe.logger().warning(
        "Deprecated: get_ptkp_mapping_cache() called - use get_cached_value() instead"
    )
    return {}


def get_tax_settings_cache():
    """Legacy function for backwards compatibility"""
    frappe.logger().warning(
        "Deprecated: get_tax_settings_cache() called - use get_cached_value() instead"
    )
    return {}


def clear_ter_cache():
    """Legacy function for backwards compatibility"""
    frappe.logger().warning(
        "Deprecated: clear_ter_cache() called - use clear_cache('ter_rate:') instead"
    )
    clear_cache("ter_rate:")


def clear_ytd_cache():
    """Legacy function for backwards compatibility"""
    frappe.logger().warning(
        "Deprecated: clear_ytd_cache() called - use clear_cache('ytd:') instead"
    )
    clear_cache("ytd:")


def clear_ptkp_mapping_cache():
    """Legacy function for backwards compatibility"""
    frappe.logger().warning(
        "Deprecated: clear_ptkp_mapping_cache() called - use clear_cache('ptkp_mapping:') instead"
    )
    clear_cache("ptkp_mapping:")


def clear_tax_settings_cache():
    """Legacy function for backwards compatibility"""
    frappe.logger().warning(
        "Deprecated: clear_tax_settings_cache() called - use clear_cache('tax_settings:') instead"
    )
    clear_cache("tax_settings:")


# Legacy cache getter/setter functions for backward compatibility
def cache_ter_rate(ter_category, income_bracket, rate_value):
    """Legacy function for backwards compatibility"""
    cache_key = f"ter_rate:{ter_category}:{income_bracket}"
    cache_value(cache_key, rate_value)


def get_cached_ter_rate(ter_category, income_bracket):
    """Legacy function for backwards compatibility"""
    cache_key = f"ter_rate:{ter_category}:{income_bracket}"
    return get_cached_value(cache_key)


def cache_ytd_data(employee, year, month, data):
    """Legacy function for backwards compatibility"""
    cache_key = f"ytd:{employee}:{year}:{month}"
    cache_value(cache_key, data)


def get_cached_ytd_data(employee, year, month):
    """Legacy function for backwards compatibility"""
    cache_key = f"ytd:{employee}:{year}:{month}"
    return get_cached_value(cache_key)


def cache_ptkp_mapping(mapping):
    """Legacy function for backwards compatibility"""
    cache_value("ptkp_mapping:global", mapping)


def get_cached_ptkp_mapping():
    """Legacy function for backwards compatibility"""
    return get_cached_value("ptkp_mapping:global")


def cache_tax_settings(key, value, expiry_seconds=None):
    """Legacy function for backwards compatibility"""
    cache_key = f"tax_settings:{key}"
    cache_value(cache_key, value, expiry_seconds)


def get_cached_tax_settings(key):
    """Legacy function for backwards compatibility"""
    cache_key = f"tax_settings:{key}"
    return get_cached_value(cache_key)


@frappe.whitelist()
def clear_salary_slip_caches() -> Dict[str, Any]:
    """
    Clear salary slip related caches to prevent memory bloat.

    This function is designed to be called by the scheduler (daily or cron) only.
    It does NOT schedule itself to avoid race conditions.

    If you need to call this function manually, use:
        frappe.enqueue(method="payroll_indonesia.utilities.cache_utils.clear_salary_slip_caches",
                      queue='long', job_name='clear_payroll_caches')

    Returns:
        Dict[str, Any]: Status and details about cleared caches
    """
    try:
        # Define prefixes that are related to salary slip functions
        prefixes_to_clear = [
            "employee_doc:",
            "fiscal_year:",
            "salary_slip:",
            "ytd_tax:",
            "ter_category:",
            "ter_rate:",
        ]

        # Log the start of cache clearing operation
        frappe.logger().info(
            f"Starting cache clearing operation for prefixes: {', '.join(prefixes_to_clear)}"
        )

        # Clear internal caches stored in CacheManager
        cleared_count = 0
        for prefix in prefixes_to_clear:
            count = clear_cache(prefix)
            cleared_count += count or 0

        # Clear Frappe document cache for Salary Slip
        frappe.clear_document_cache("Salary Slip")

        # Clear general cache for good measure
        # This is optional and may not be needed in all cases
        # frappe.clear_cache()

        # Log completion
        frappe.logger().info(f"Cleared {cleared_count} cached items from salary slip caches")

        return {
            "status": "success",
            "cleared_count": cleared_count,
            "prefixes": prefixes_to_clear,
            "doctype_cache_cleared": "Salary Slip",
        }

    except Exception as e:
        # Non-critical error - log and continue
        frappe.logger().exception(f"Error clearing salary slip caches: {e}")
        return {"status": "error", "message": str(e)}
