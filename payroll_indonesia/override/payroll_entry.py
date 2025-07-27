from erpnext.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry
import frappe
from payroll_indonesia.config import config
from payroll_indonesia.config import pph21_ter
from payroll_indonesia.config import pph21_ter_december

class CustomPayrollEntry(PayrollEntry):
    def validate(self):
        super().validate()
        # Custom validation for Payroll Indonesia
        if getattr(self, "run_payroll_indonesia", False):
            frappe.logger().info("Payroll Entry: Run Payroll Indonesia is checked.")
            settings = config.get_settings()
            if hasattr(self, "pph21_method") and not self.pph21_method:
                self.pph21_method = settings.get("pph21_method", "TER")
        if getattr(self, "run_payroll_indonesia_december", False):
            frappe.logger().info("Payroll Entry: Run Payroll Indonesia DECEMBER mode is checked.")
            # Tambahkan validasi/logic khusus Desember jika ada

    def create_salary_slips(self):
        """
        Override: generate salary slips dengan perhitungan PPh 21 Indonesia (TER/Desember)
        """
        if getattr(self, "run_payroll_indonesia_december", False):
            frappe.logger().info("Payroll Entry: Running Salary Slip generation for Payroll Indonesia DECEMBER (final year) mode.")
            return self._create_salary_slips_indonesia_december()
        elif getattr(self, "run_payroll_indonesia", False):
            frappe.logger().info("Payroll Entry: Running Salary Slip generation for Payroll Indonesia normal mode.")
            return self._create_salary_slips_indonesia()
        else:
            return super().create_salary_slips()

    def _create_salary_slips_indonesia(self):
        """
        Generate salary slips dengan logika PPh21 TER (bulanan).
        """
        slips = super().create_salary_slips()
        for slip in slips:
            emp = self._get_employee_doc(slip)
            # Hitung PPh 21 TER
            pph21_result = pph21_ter.calculate_pph21_TER(emp, slip)
            slip["pph21_info"] = pph21_result
            slip["tax"] = pph21_result.get("pph21", 0)
            slip["tax_type"] = "TER"
        return slips

    def _create_salary_slips_indonesia_december(self):
        """
        Generate salary slips dengan logika PPh21 Desember (annual progressive/final).
        """
        slips = super().create_salary_slips()
        for slip in slips:
            emp = self._get_employee_doc(slip)
            # Hitung PPh 21 progressive annual (Desember)
            pph21_result = pph21_ter_december.calculate_pph21_TER_december(emp, slip)
            slip["pph21_info"] = pph21_result
            slip["tax"] = pph21_result.get("pph21_month", 0)
            slip["tax_type"] = "DECEMBER"
        return slips

    def _get_employee_doc(self, slip):
        """
        Helper untuk mengambil data employee (dict), bisa dari slip atau fetch dari DB.
        """
        if "employee" in slip:
            if isinstance(slip["employee"], dict):
                return slip["employee"]
            else:
                # Fetch doc dari DB jika hanya string id
                return frappe.get_doc("Employee", slip["employee"])
        return {}
