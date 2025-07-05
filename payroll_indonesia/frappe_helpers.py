"""
Common Frappe helper functions for Payroll Indonesia.
Provides utilities for document existence checks and safe execution.
"""

import logging
from functools import wraps
from typing import Any, Callable, Dict, TypeVar, Union

import frappe
from frappe.model.document import Document

# Setup logging
logger = logging.getLogger(__name__)

T = TypeVar("T")
DocType = Union[Document, Dict[str, Any]]
DocIdentifier = Union[str, Dict[str, str]]


def doc_exists(doctype: str, name: str) -> bool:
    """
    Check if a document exists in the database.

    Args:
        doctype: The document type to check
        name: The name (ID) of the document

    Returns:
        bool: True if the document exists, False otherwise
    """
    try:
        return frappe.db.exists(doctype, name)
    except Exception as e:
        logger.error(f"Error checking if document exists: {doctype}/{name}: {str(e)}")
        return False


def ensure_doc_exists(doctype: str, name: str) -> None:
    """
    Ensure a document exists, raising an exception if it doesn't.

    Args:
        doctype: The document type to check
        name: The name (ID) of the document

    Raises:
        frappe.DoesNotExistError: If the document doesn't exist
    """
    if not doc_exists(doctype, name):
        msg = f"Document {doctype}/{name} does not exist"
        logger.error(msg)
        frappe.throw(msg, frappe.DoesNotExistError)


def safe_execute(
    default_value: T = None, log_exception: bool = True
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to safely execute a function, catching and logging exceptions.

    Args:
        default_value: Value to return if an exception occurs
        log_exception: Whether to log the exception when it occurs

    Returns:
        Decorator function that wraps the target function

    Example:
        @safe_execute(default_value=False)
        def risky_operation():
            # Some code that might raise an exception
            return True
    """

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
