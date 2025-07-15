import sys
import types
import pytest

pytest.importorskip("frappe")


def test_update_custom_fields_sets_values(monkeypatch):
    frappe = types.ModuleType("frappe")
    frappe.get_doc = lambda *args, **kwargs: types.SimpleNamespace(npwp_gabung_suami=0)
    frappe.utils = types.ModuleType("frappe.utils")
    frappe.utils.flt = float
    frappe.utils.cint = int
    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = frappe.utils

    import importlib
    ssf = importlib.import_module("payroll_indonesia.override.salary_slip_functions")

    monkeypatch.setattr(ssf, "calculate_taxable_earnings", lambda doc: 10000000)
    monkeypatch.setattr(ssf, "get_slip_year_month", lambda doc: (2025, 1))
    monkeypatch.setattr(ssf, "get_ytd_totals", lambda doc: {"gross": 0, "bpjs": 0, "pph21": 0})
    monkeypatch.setattr(ssf, "is_december_calculation", lambda doc: False)
    monkeypatch.setattr(ssf, "categorize_components_by_tax_effect", lambda doc: {"totals": {ssf.TAX_OBJEK_EFFECT: 10000000, ssf.NATURA_OBJEK_EFFECT: 0, ssf.TAX_DEDUCTION_EFFECT: 1000000}})

    doc = types.SimpleNamespace(
        employee="EMP-1",
        gross_pay=10000000,
        net_pay=0,
        total_deduction=1000000,
        deductions=[],
        earnings=[],
        taxable_earnings=0,
        base_gross_pay=0,
        base_net_pay=0,
        base_total_deduction=0,
        salary_year=0,
        salary_month=0,
        ytd_gross=0,
        ytd_bpjs=0,
        ytd_pph21=0,
        is_december_slip=0,
        is_final_gabung_suami=0,
        netto=0,
        biaya_jabatan=0,
        annual_taxable_income=0,
        annual_pkp=0,
    )

    ssf._update_custom_fields(doc)

    assert doc.netto == 9000000
    assert doc.biaya_jabatan > 0
    assert doc.annual_taxable_income == 10000000 * ssf.MONTHS_PER_YEAR
    assert doc.annual_pkp >= 0
