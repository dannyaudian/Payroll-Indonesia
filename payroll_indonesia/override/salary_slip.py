try:
    from erpnext.payroll.doctype.salary_slip.salary_slip import SalarySlip
except Exception:  # pragma: no cover - erpnext may not be installed during tests
    SalarySlip = object  # type: ignore

import frappe

from payroll_indonesia.config import pph21_ter, pph21_ter_december


class CustomSalarySlip(SalarySlip):
    """Salary Slip with Indonesian income tax calculations."""

    def calculate_income_tax(self):
        """Calculate income tax using Indonesian rules."""
        if getattr(self, "run_payroll_indonesia_december", False):
            frappe.logger().info("Salary Slip: calculating PPh21 December mode.")
            result = pph21_ter_december.calculate_pph21_TER_december(
                self.employee, self
            )
            self.pph21_info = result
            self.tax = result.get("pph21_month", 0)
            self.tax_type = "DECEMBER"
            return self.tax

        if getattr(self, "run_payroll_indonesia", False):
            frappe.logger().info("Salary Slip: calculating PPh21 TER mode.")
            result = pph21_ter.calculate_pph21_TER(self.employee, self)
            self.pph21_info = result
            self.tax = result.get("pph21", 0)
            self.tax_type = "TER"
            return self.tax

        return super().calculate_income_tax()
