# -*- coding: utf-8 -*-
"""Persistent install flag helpers for Payroll Indonesia."""

import frappe

FLAG_KEY = "payroll_indonesia_install_complete"

__all__ = [
    "is_installation_complete",
    "mark_installation_complete",
    "clear_installation_flag",
]


def is_installation_complete() -> bool:
    """Return True if the installation has already run."""
    try:
        return bool(frappe.db.get_default(FLAG_KEY))
    except Exception:
        return False


def mark_installation_complete() -> None:
    """Mark the installation as completed."""
    try:
        frappe.db.set_default(FLAG_KEY, "1")
    except Exception:
        pass


def clear_installation_flag() -> None:
    """Remove the persistent installation flag."""
    try:
        frappe.db.delete("DefaultValue", {"defkey": FLAG_KEY})
    except Exception:
        pass
