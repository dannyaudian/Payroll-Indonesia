import types
import frappe

if not hasattr(frappe.utils, "file_lock"):
    frappe.utils.file_lock = lambda *a, **k: None

from payroll_indonesia.override.salary_slip import CustomSalarySlip


def test_manual_totals_respects_exclusion_flags():
    slip = CustomSalarySlip()
    slip.name = "SS-TEST"
    slip.currency = "IDR"

    slip.earnings = [
        types.SimpleNamespace(amount=1000),
        types.SimpleNamespace(amount=200, do_not_include_in_total=1),
        types.SimpleNamespace(amount=300, statistical_component=1),
    ]

    slip.deductions = [
        types.SimpleNamespace(amount=100),
        types.SimpleNamespace(amount=50, do_not_include_in_total=1),
        types.SimpleNamespace(amount=80, statistical_component=1),
    ]

    # Predefine attributes to ensure they get updated
    slip.rounded_total = 0
    slip.total = 0

    slip._manual_totals_calculation()

    assert slip.gross_pay == 1000
    assert slip.total_deduction == 100
    assert slip.net_pay == 900
    assert slip.rounded_total == 900
    assert slip.total == 900
