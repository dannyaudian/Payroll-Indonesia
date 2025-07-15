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
from frappe.utils import cint  # Tambahkan import untuk fungsi cint
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

_config_cache: Optional[Dict[str, Any]] = None

def doctype_defined(doctype: str) -> bool:
    return bool(frappe.db.exists("DocType", doctype))

def get_config() -> Dict[str, Any]:
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
    config = get_config()

    try:
        if doctype_defined("Payroll Indonesia Settings"):
            settings_name = "Payroll Indonesia Settings"

            if frappe.db.exists(settings_name, settings_name):
                live_settings = frappe.get_doc(settings_name, settings_name)

                if live_settings:
                    merged_config = {**config}
                    live_dict = live_settings.as_dict()
                    for key, value in live_dict.items():
                        if not key.startswith("_") and value is not None:
                            merged_config[key] = value

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
    try:
        config = get_live_config()
        if key in config:
            return config[key]

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
    global _config_cache
    _config_cache = None
    logger.debug("Configuration cache has been reset")

def get_tax_effect_types() -> Dict[str, Any]:
    try:
        config = get_live_config()
        tax_effect_types = config.get("tax", {}).get("tax_effect_types", {})
        
        if not tax_effect_types:
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
        return {
            "default_earning_tax_effect": "Penambah Bruto/Objek Pajak",
            "default_deduction_tax_effect": "Pengurang Netto/Tax Deduction",
            "options": ["Penambah Bruto/Objek Pajak", "Pengurang Netto/Tax Deduction", "Tidak Berpengaruh ke Pajak"]
        }

def get_component_tax_effect(component_name: str, component_type: Optional[str] = None) -> str:
    try:
        tax_effect = frappe.db.get_value("Salary Component", component_name, "tax_effect_type")

        if tax_effect:
            return tax_effect

        is_tax_applicable = cint(frappe.db.get_value("Salary Component", component_name, "is_tax_applicable"))
        if component_type == "Earning":
            return "Penambah Bruto/Objek Pajak" if is_tax_applicable else "Tidak Berpengaruh ke Pajak"
        elif component_type == "Deduction":
            return "Pengurang Netto/Tax Deduction" if is_tax_applicable else "Tidak Berpengaruh ke Pajak"
        else:
            return "Tidak Berpengaruh ke Pajak"
    except Exception as e:
        logger.exception(f"Error getting tax effect for component {component_name}: {str(e)}")
        return ""