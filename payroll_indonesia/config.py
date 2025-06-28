"""Configuration utilities for Payroll Indonesia."""
import json
import os
from pathlib import Path
from typing import Dict, Any

_config_cache = None


def get_config() -> Dict[str, Any]:
    """Load and cache defaults.json configuration.
    
    Returns:
        Dict[str, Any]: Configuration dictionary
        
    Raises:
        FileNotFoundError: If defaults.json is missing
    """
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    config_path = Path(__file__).parent / "config" / "defaults.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        _config_cache = json.load(f)
    return _config_cache


def get_live_config() -> Dict[str, Any]:
    """Get configuration, preferring DocType 'Payroll Indonesia Settings' if available.
    
    Returns:
        Dict[str, Any]: Configuration dictionary with live settings if available
    """
    config = get_config()
    try:
        from frappe.model.document import get_doc
        live_settings = get_doc("Payroll Indonesia Settings")
        if live_settings:
            return {**config, **live_settings.as_dict()}
    except (ImportError, Exception):
        pass
    return config
