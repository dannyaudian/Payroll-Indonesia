import importlib
import sys
import types


def test_migrate_all_settings_rolls_back_on_step_failure(monkeypatch):
    calls = []
    frappe = types.ModuleType("frappe")
    frappe.utils = types.ModuleType("frappe.utils")
    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = frappe.utils

    frappe.db = types.SimpleNamespace(
        begin=lambda: calls.append("begin"),
        commit=lambda: calls.append("commit"),
        rollback=lambda: calls.append("rollback"),
    )
    frappe.get_single = lambda name: types.SimpleNamespace(
        ter_rate_table=[],
        ptkp_table=[],
        ptkp_ter_mapping_table=[],
        tax_brackets_table=[],
        tipe_karyawan=[],
        flags=types.SimpleNamespace(),
        save=lambda: calls.append("save"),
    )
    frappe.utils.flt = float
    frappe.utils.cint = int
    frappe.utils.now_datetime = lambda: None
    frappe._ = lambda x: x

    sm = importlib.import_module("payroll_indonesia.setup.settings_migration")

    monkeypatch.setattr(sm, "_load_defaults", lambda: {"dummy": True})
    monkeypatch.setattr(sm, "_seed_ter_rates", lambda *a, **k: (_ for _ in ()).throw(Exception("fail")))

    for fn in [
        "_seed_ptkp_values",
        "_seed_ptkp_ter_mapping",
        "_seed_tax_brackets",
        "_seed_tipe_karyawan",
        "_update_general_settings",
        "_update_bpjs_settings",
        "_seed_gl_account_mappings",
    ]:
        monkeypatch.setattr(sm, fn, lambda *a, **k: True)

    result = sm.migrate_all_settings()

    assert "rollback" in calls and "commit" not in calls
    assert result["ter_rates"] is False
