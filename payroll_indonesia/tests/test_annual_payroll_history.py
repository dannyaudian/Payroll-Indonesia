import types
import sys


def test_get_or_create_creates(monkeypatch):
    frappe = sys.modules.get("frappe")

    from payroll_indonesia.utils.sync_annual_payroll_history import (
        get_or_create_annual_payroll_history,
    )

    doc = get_or_create_annual_payroll_history("EMP001", "2024")
    assert doc.name == "EMP001-2024"
    assert doc.fiscal_year == "2024"


def test_get_or_create_returns_existing(monkeypatch):
    frappe = sys.modules.get("frappe")

    from payroll_indonesia.utils.sync_annual_payroll_history import (
        get_or_create_annual_payroll_history,
    )

    existing = types.SimpleNamespace(name="EMP001-2024")
    frappe.get_doc = lambda dt, name: existing
    frappe.db.get_value = lambda dt, filters, field: "EMP001-2024"

    doc = get_or_create_annual_payroll_history("EMP001", "2024")
    assert doc is existing
