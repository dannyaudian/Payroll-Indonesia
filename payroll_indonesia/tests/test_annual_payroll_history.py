import types
import sys


def test_get_or_create_creates(monkeypatch):
    frappe = sys.modules.get("frappe")

    from payroll_indonesia.utils.sync_annual_payroll_history import (
        get_or_create_annual_payroll_history,
    )

    captured = {}

    def fake_make_autoname(key):
        captured["key"] = key
        return f"AUTO-{key}"

    monkeypatch.setattr(
        "payroll_indonesia.utils.sync_annual_payroll_history.make_autoname",
        fake_make_autoname,
    )

    doc = get_or_create_annual_payroll_history(employee_id="EMP001", fiscal_year="2024")
    assert doc.name == "AUTO-EMP001-2024"
    assert captured["key"] == "EMP001-2024"
    assert doc.fiscal_year == "2024"


def test_get_or_create_returns_existing(monkeypatch):
    frappe = sys.modules.get("frappe")

    from payroll_indonesia.utils.sync_annual_payroll_history import (
        get_or_create_annual_payroll_history,
    )

    expected_name = "-".join(["EMP001", "2024"])
    existing = types.SimpleNamespace(name=expected_name)
    monkeypatch.setattr(frappe, "get_doc", lambda dt, name: existing)
    monkeypatch.setattr(
        frappe.db, "get_value", lambda dt, filters, field: expected_name
    )

    calls = {"count": 0}

    def fake_make_autoname(key):
        calls["count"] += 1
        return key

    monkeypatch.setattr(
        "payroll_indonesia.utils.sync_annual_payroll_history.make_autoname",
        fake_make_autoname,
    )

    doc = get_or_create_annual_payroll_history(employee_id="EMP001", fiscal_year="2024")
    assert doc is existing
    assert calls["count"] == 0
