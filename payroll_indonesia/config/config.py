# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-03 04:12:55 by dannyaudian

"""
Configuration utilities for Payroll Indonesia.
Provides functions to load configuration from defaults.json and live settings.
"""

import json
import os
from typing import Dict, Any, Optional

import frappe
from payroll_indonesia.frappe_helpers import logger

__all__ = [
    "get_config",
    "get_live_config",
    "get_config_value",
    "reset_config_cache",
    "doctype_defined",
]

# Global cache for config
_config_cache: Optional[Dict[str, Any]] = None


def doctype_defined(doctype: str) -> bool:
    """
    Check if a DocType is defined in the system.

    Args:
        doctype: The DocType name to check

    Returns:
        bool: True if the DocType exists, False otherwise
    """
    return bool(frappe.db.exists("DocType", doctype))


def get_config() -> Dict[str, Any]:
    """
    Load and cache defaults.json configuration.

    Returns:
        Dict[str, Any]: Configuration dictionary

    Raises:
        FileNotFoundError: If defaults.json is missing or invalid
    """
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    try:
        config_path = os.path.join(os.path.dirname(__file__), "defaults.json")
        if not os.path.exists(config_path):
            error_msg = f"Configuration file not found: {config_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        with open(config_path, "r", encoding="utf-8") as f:
            _config_cache = json.load(f)
            logger.info(f"Successfully loaded configuration from {config_path}")
            return _config_cache
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in configuration file: {str(e)}"
        logger.error(error_msg)
        raise ValueError(error_msg) from e
    except Exception as e:
        error_msg = f"Error loading configuration: {str(e)}"
        logger.error(error_msg)
        raise


def get_live_config() -> Dict[str, Any]:
    """
    Get configuration, preferring DocType 'Payroll Indonesia Settings' if available.
    Falls back to defaults.json if DocType is not available or there's an error.

    Returns:
        Dict[str, Any]: Configuration dictionary with live settings if available
    """
    # First load the default config
    config = get_config()

    try:
        # Check if DocType exists using the new helper
        if doctype_defined("Payroll Indonesia Settings"):
            settings_name = "Payroll Indonesia Settings"

            # Check if settings document exists
            if frappe.db.exists(settings_name, settings_name):
                # Get the document
                live_settings = frappe.get_doc(settings_name, settings_name)

                if live_settings:
                    # Merge config with live settings
                    # Priority is given to live settings values
                    merged_config = {**config}  # Create a copy of default config

                    # Convert live settings to dict
                    live_dict = live_settings.as_dict()

                    # Update default config with live settings
                    for key, value in live_dict.items():
                        # Skip internal fields
                        if not key.startswith("_") and value is not None:
                            merged_config[key] = value

                    logger.info("Successfully merged live settings with default configuration")
                    return merged_config
                else:
                    logger.warning("Live settings document exists but could not be loaded")
    except ImportError:
        logger.warning("Frappe not available, falling back to default config")
    except Exception as e:
        logger.warning(f"Error getting live config: {str(e)}, falling back to default config")

    return config


def get_config_value(key: str, default: Any = None) -> Any:
    """
    Get a specific configuration value by key.

    Args:
        key: The configuration key to retrieve
        default: Default value if key is not found

    Returns:
        Any: The configuration value or default if not found
    """
    try:
        config = get_live_config()
        if key in config:
            return config[key]

        # Try nested keys (dot notation)
        if "." in key:
            parts = key.split(".")
            current = config
            for part in parts:
                if part in current:
                    current = current[part]
                else:
                    return default
            return current

        logger.debug(f"Configuration key '{key}' not found, using default value")
        return default
    except Exception as e:
        logger.error(f"Error retrieving config value for '{key}': {str(e)}")
        return default


def reset_config_cache() -> None:
    """
    Reset the configuration cache.
    Call this when configuration might have changed.
    """
    global _config_cache
    _config_cache = None
    logger.debug("Configuration cache has been reset")