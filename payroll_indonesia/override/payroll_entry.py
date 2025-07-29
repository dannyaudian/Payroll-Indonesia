try:
    from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry
except Exception:
    PayrollEntry = object  # fallback for tests/static analysis

import frappe
from payroll_indonesia.override.salary_slip import CustomSalarySlip
from payroll_indonesia.config import get_value

class CustomPayrollEntry(PayrollEntry):
    """
    Custom Payroll Entry for Payroll Indonesia.
    Override salary slip creation to use CustomSalarySlip with PPh21 TER/Desember logic.
    """

    def validate(self):
        super().validate()
        # Custom validation for Payroll Indonesia
        if getattr(self, "run_payroll_indonesia", False):
            frappe.logger().info("Payroll Entry: Run Payroll Indonesia is checked.")
            # Auto set pph21_method from settings if not set
            if hasattr(self, "pph21_method") and not self.pph21_method:
                self.pph21_method = get_value("pph21_method", "TER")
        if getattr(self, "run_payroll_indonesia_december", False):
            frappe.logger().info("Payroll Entry: Run Payroll Indonesia DECEMBER mode is checked.")
            # Add any December-specific validation if needed

    def create_salary_slips(self):
        """
        Override: generate salary slips with Indonesian tax logic.
        """
        if getattr(self, "run_payroll_indonesia_december", False):
            frappe.logger().info(
                "Payroll Entry: Running Salary Slip generation for Payroll Indonesia DECEMBER (final year) mode."
            )
            return self._create_salary_slips_indonesia_december()
        elif getattr(self, "run_payroll_indonesia", False):
            frappe.logger().info(
                "Payroll Entry: Running Salary Slip generation for Payroll Indonesia normal mode."
            )
            return self._create_salary_slips_indonesia()
        else:
            result = super().create_salary_slips()
            return result if result is not None else []

    def _create_salary_slips_indonesia(self):
        """
        Generate salary slips with PPh21 TER (monthly) logic.
        Always return a list (empty if no slip).
        """
        slips = super().create_salary_slips()
        if slips is None:
            slips = []
        for slip in slips:
            slip_obj = self._get_salary_slip_obj(slip)
            slip_obj.calculate_income_tax()
            if isinstance(slip, dict):
                slip["pph21_info"] = getattr(slip_obj, "pph21_info", {})
                slip["tax"] = getattr(slip_obj, "tax", 0)
                slip["tax_type"] = getattr(slip_obj, "tax_type", "TER")
        return slips

    def _create_salary_slips_indonesia_december(self):
        """
        Generate salary slips with PPh21 Desember (annual progressive) logic.
        Always return a list (empty if no slip).
        """
        slips = super().create_salary_slips()
        if slips is None:
            slips = []
        for slip in slips:
            slip_obj = self._get_salary_slip_obj(slip)
            slip_obj.calculate_income_tax()
            if isinstance(slip, dict):
                slip["pph21_info"] = getattr(slip_obj, "pph21_info", {})
                slip["tax"] = getattr(slip_obj, "tax", 0)
                slip["tax_type"] = getattr(slip_obj, "tax_type", "DECEMBER")
        return slips

    def _get_salary_slip_obj(self, slip):
        """
        Helper: get or construct a SalarySlip (or CustomSalarySlip) object for calculation.
        """
        if hasattr(slip, "calculate_income_tax"):
            return slip  # already a slip object
        elif isinstance(slip, dict):
            # Try fetch from DB if possible, else construct from dict
            if "name" in slip:
                try:
                    slip_obj = frappe.get_doc("Salary Slip", slip["name"])
                except Exception:
                    slip_obj = CustomSalarySlip(**slip)
            else:
                slip_obj = CustomSalarySlip(**slip)
            return slip_obj
        else:
            return slip  # fallback

    def _get_employee_doc(self, slip):
        """
        Helper to get employee doc/dict from slip.
        """
        if hasattr(slip, "employee"):
            if isinstance(slip.employee, dict):
                return slip.employee
            try:
                return frappe.get_doc("Employee", slip.employee)
            except Exception:
                return {}
        if isinstance(slip, dict) and "employee" in slip:
            if isinstance(slip["employee"], dict):
                return slip["employee"]
            try:
                return frappe.get_doc("Employee", slip["employee"])
            except Exception:
                return {}
        return {}
