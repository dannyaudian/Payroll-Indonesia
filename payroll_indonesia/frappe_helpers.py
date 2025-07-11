# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Common Frappe helper functions for Payroll Indonesia.

This module provides utility functions for consistent logging across the application.
It can be safely imported from any context, including:
- Web requests
- Background jobs
- CLI commands
- Tests

Usage:
    from payroll_indonesia.frappe_helpers import get_logger

    logger = get_logger("my_module")
    logger.info("This is an info message")
    logger.error("This is an error message")
"""

import logging
from functools import wraps
from typing import Any, Callable, Dict, TypeVar, Union, Optional

try:
    import frappe
    FRAPPE_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    FRAPPE_AVAILABLE = False

T = TypeVar("T")
DocType = Union['Document', Dict[str, Any]]
DocIdentifier = Union[str, Dict[str, str]]

def get_logger(name: str, fallback_level: int = logging.INFO) -> logging.Logger:
    """
    Get a logger that integrates with Frappe's logging system when available.

    Creates a logger that will:
    1. Use frappe.logger() in web request contexts
    2. Fall back to standard Python logging when frappe isn't fully initialized
    3. Configure proper log levels and formatting
    Args:
        name: The name of the logger, typically the module name
        fallback_level: Default log level when not using Frappe's logger
    Returns:
        logging.Logger: A configured logger instance
    """
    if not name.startswith('payroll_indonesia.'):
        logger_name = f'payroll_indonesia.{name}'
    else:
        logger_name = name

    if FRAPPE_AVAILABLE and hasattr(frappe, 'logger'):
        try:
            logger = frappe.logger(logger_name)
            return logger
        except Exception:
            pass

    logger = logging.getLogger(logger_name)

    if not logger.handlers:
        logger.setLevel(fallback_level)

        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        def log_to_frappe(msg, level=logging.INFO):
            if FRAPPE_AVAILABLE:
                try:
                    if level >= logging.ERROR:
                        frappe.log_error(msg, f"{name} Error")
                    else:
                        frappe.log(msg)
                except Exception:
                    pass

        logger.log_to_frappe = log_to_frappe

    return logger

logger = get_logger(__name__)

def doc_exists(doctype: str, name: str) -> bool:
    if FRAPPE_AVAILABLE:
        try:
            return frappe.db.exists(doctype, name)
        except Exception as e:
            logger.error(f"Error checking if document exists: {doctype}/{name}: {str(e)}")
    return False

def ensure_doc_exists(doctype: str, name: str) -> None:
    if not doc_exists(doctype, name):
        msg = f"Document {doctype}/{name} does not exist"
        logger.error(msg)
        if FRAPPE_AVAILABLE:
            frappe.throw(msg, frappe.DoesNotExistError)

def safe_execute(
    default_value: T = None, log_exception: bool = True
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_exception:
                    logger.exception(f"Exception in {func.__name__}: {str(e)}")
                return default_value
        return wrapper
    return decorator
