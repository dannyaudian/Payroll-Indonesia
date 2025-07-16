# -*- coding: utf-8 -*-
"""Utility helpers for updating documents safely."""

from typing import Any, Dict


def sanitize_update_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of ``data`` without immutable fields.

    Keys like ``creation`` or ``creation_on`` should never be passed to
    update functions as they would trigger ``CannotChangeConstantError`` in
    Frappe. This helper strips such keys before database operations.

    Args:
        data: Mapping of fields to update.

    Returns:
        Sanitized copy of ``data`` with disallowed keys removed.
    """
    if not isinstance(data, dict):
        return {}

    blocked_keys = {
        "creation",
        "creation_on",
        "modified",
        "modified_by",
        "modified_on",
        "owner",
        "doctype",
        "idx",
    }

    return {k: v for k, v in data.items() if k not in blocked_keys}
