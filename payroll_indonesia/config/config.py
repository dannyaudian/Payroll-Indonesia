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
from typing import Dict, Any, Optional, List, Union

import frappe
from payroll_indonesia.frappe_helpers import logger

__all__ = [
    "get_config",
    "get_live_config",
    "get_config_value",
    "reset_config_cache",
    "doctype_defined",
    "get_tax_effect_types",
    "get_component_tax_effect",
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

                    # Handle special cases for table fields
                    if hasattr(live_settings, "ptkp_table") and live_settings.ptkp_table:
                        merged_config["ptkp"] = {row.status_pajak: row.ptkp_amount for row in live_settings.ptkp_table}
                    
                    if hasattr(live_settings, "ptkp_ter_mapping_table") and live_settings.ptkp_ter_mapping_table:
                        merged_config["ptkp_to_ter_mapping"] = {
                            row.ptkp_status: row.ter_category for row in live_settings.ptkp_ter_mapping_table
                        }
                    
                    if hasattr(live_settings, "tax_brackets_table") and live_settings.tax_brackets_table:
                        merged_config["tax_brackets"] = [
                            {
                                "income_from": row.income_from,
                                "income_to": row.income_to,
                                "tax_rate": row.tax_rate
                            } 
                            for row in live_settings.tax_brackets_table
                        ]

                    # Process tax component mapping if available
                    if hasattr(live_settings, "tax_component_mapping_json") and live_settings.tax_component_mapping_json:
                        try:
                            tax_component_mapping = json.loads(live_settings.tax_component_mapping_json)
                            if isinstance(tax_component_mapping, dict):
                                merged_config["tax_component_config"] = tax_component_mapping
                        except Exception as e:
                            logger.warning(f"Error parsing tax_component_mapping_json: {str(e)}")

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


def get_tax_effect_types() -> Dict[str, Any]:
    """
    Get tax effect type definitions from config.
    
    Returns:
        Dict containing tax effect types configuration
    """
    try:
        config = get_live_config()
        tax_effect_types = config.get("tax", {}).get("tax_effect_types", {})
        
        if not tax_effect_types:
            # Fallback defaults
            return {
                "default_earning_tax_effect": "Penambah Bruto/Objek Pajak",
                "default_deduction_tax_effect": "Pengurang Netto/Tax Deduction",
                "options": [
                    "Penambah Bruto/Objek Pajak",
                    "Pengurang Netto/Tax Deduction",
                    "Tidak Berpengaruh ke Pajak",
                    "Natura/Fasilitas (Objek Pajak)",
                    "Natura/Fasilitas (Non-Objek Pajak)"
                ]
            }
            
        return tax_effect_types
    except Exception as e:
        logger.error(f"Error retrieving tax effect types: {str(e)}")
        # Return minimal fallback
        return {
            "default_earning_tax_effect": "Penambah Bruto/Objek Pajak",
            "default_deduction_tax_effect": "Pengurang Netto/Tax Deduction",
            "options": ["Penambah Bruto/Objek Pajak", "Pengurang Netto/Tax Deduction", "Tidak Berpengaruh ke Pajak"]
        }


def get_component_tax_effect(component_name: str, component_type: str = "Earning") -> str:
    """
    Get the tax effect for a salary component based on configuration.
    
    Args:
        component_name: The name of the salary component
        component_type: Whether the component is used as 'Earning' or 'Deduction'
        
    Returns:
        str: The appropriate tax effect type
    """
    try:
        config = get_live_config()
        
        # First check if the component is explicitly categorized in tax_component_config
        tax_component_config = config.get("tax_component_config", {}).get("tax_components", {})
        
        for category, components in tax_component_config.items():
            if component_name in components:
                if category == "penambah_bruto":
                    return "Penambah Bruto/Objek Pajak"
                elif category == "pengurang_netto":
                    return "Pengurang Netto/Tax Deduction"
                elif category == "tidak_berpengaruh":
                    return "Tidak Berpengaruh ke Pajak"
                elif category == "natura_objek":
                    return "Natura/Fasilitas (Objek Pajak)"
                elif category == "natura_non_objek":
                    return "Natura/Fasilitas (Non-Objek Pajak)"
                
        # Next check if component is defined in salary_components
        salary_components = config.get("salary_components", {})
        component_list = []
        
        if component_type == "Earning":
            component_list = salary_components.get("earnings", [])
        else:
            component_list = salary_components.get("deductions", [])
            
        for comp in component_list:
            if comp.get("name") == component_name:
                tax_effects = comp.get("tax_effect_by_type", [])
                for effect in tax_effects:
                    if effect.get("component_type") == component_type:
                        return effect.get("tax_effect_type")
        
        # If not found, use defaults based on component type
        tax_effect_types = get_tax_effect_types()
        if component_type == "Earning":
            return tax_effect_types.get("default_earning_tax_effect", "Penambah Bruto/Objek Pajak")
        else:
            return tax_effect_types.get("default_deduction_tax_effect", "Pengurang Netto/Tax Deduction")
            
    except Exception as e:
        logger.error(f"Error getting tax effect for {component_name} as {component_type}: {str(e)}")
        # Fallback to sensible defaults
        if component_type == "Earning":
            return "Penambah Bruto/Objek Pajak"
        else:
            return "Pengurang Netto/Tax Deduction"