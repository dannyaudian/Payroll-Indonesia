import types
import sys


def test_get_or_create_creates(monkeypatch):
    frappe = sys.modules.get("frappe")

    from payroll_indonesia.utils.sync_annual_payroll_history import (
        get_or_create_annual_payroll_history,
    )

    doc = get_or_create_annual_payroll_history("EMP001", "2024")
    expected_name = "-".join(["EMP001", "2024"])
    assert doc.name == expected_name
    assert doc.fiscal_year == "2024"


def test_get_or_create_returns_existing(monkeypatch):
    frappe = sys.modules.get("frappe")

    from payroll_indonesia.utils.sync_annual_payroll_history import (
        get_or_create_annual_payroll_history,
    )

    expected_name = "-".join(["EMP001", "2024"])
    existing = types.SimpleNamespace(name=expected_name)
    frappe.get_doc = lambda dt, name: existing
    frappe.db.get_value = lambda dt, filters, field: expected_name

    doc = get_or_create_annual_payroll_history("EMP001", "2024")
    assert doc is existing
