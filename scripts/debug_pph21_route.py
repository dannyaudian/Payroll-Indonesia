from __future__ import annotations

import frappe

from payroll_indonesia.payroll_indonesia import salary_slip_functions as ssf


def main() -> None:
    frappe.connect(site="itb_dev_lokal")  # ganti site Anda

    # 1. Ensure settings
    settings = frappe.get_cached_doc("Payroll Indonesia Settings")
    settings.use_ter = 1
    settings.tax_calculation_method = "TER"
    settings.save(ignore_permissions=True)

    # 2. Dummy employee
    emp = frappe.new_doc("Employee")
    emp.employee_name = "Debug TK1"
    emp.status_pajak = "TK1"
    emp.insert(ignore_permissions=True)

    # 3. Dummy slip doc object (minimal attrs needed)
    class DummySlip:
        name = "SLIP-DEBUG"
        employee = emp.name
        status_pajak = emp.status_pajak
        gross_pay = 10_000_000

    tax = ssf.calculate_pph21(DummySlip())
    print("Result tax:", tax)


if __name__ == "__main__":
    main()
