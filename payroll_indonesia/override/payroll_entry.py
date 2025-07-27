from erpnext.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry
import frappe

class CustomPayrollEntry(PayrollEntry):
    def validate(self):
        super().validate()
        # Custom validation for Payroll Indonesia
        if getattr(self, "run_payroll_indonesia", False):
            frappe.logger().info("Payroll Entry: Run Payroll Indonesia is checked.")
            # Auto set pph21_method from settings if not set
            settings = frappe.get_single("Payroll Indonesia Settings") if frappe.db.exists("DocType", "Payroll Indonesia Settings") else None
            if hasattr(self, "pph21_method") and not self.pph21_method and settings:
                self.pph21_method = settings.get("pph21_method", "TER")
        if getattr(self, "run_payroll_indonesia_december", False):
            frappe.logger().info("Payroll Entry: Run Payroll Indonesia DECEMBER mode is checked.")
            # Add any December-specific validation here if needed

    def create_salary_slips(self):
        """
        Override: generate salary slips dengan perhitungan PPh 21 Indonesia (TER/Desember) via CustomSalarySlip logic
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
        Generate salary slips dengan logika PPh21 TER (bulanan) sesuai CustomSalarySlip.
        """
        slips = super().create_salary_slips()
        for slip in slips:
            slip_obj = self._get_salary_slip_obj(slip)
            # calculate_income_tax will handle the Indonesian logic
            slip_obj.calculate_income_tax()
            # Sync calculated fields back if slip is dict (for batch context)
            if isinstance(slip, dict):
                slip["pph21_info"] = getattr(slip_obj, "pph21_info", {})
                slip["tax"] = getattr(slip_obj, "tax", 0)
                slip["tax_type"] = getattr(slip_obj, "tax_type", "TER")
        return slips

    def _create_salary_slips_indonesia_december(self):
        """
        Generate salary slips dengan logika PPh21 Desember (annual progressive/final) sesuai CustomSalarySlip.
        """
        slips = super().create_salary_slips()
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
        Helper: construct or fetch a SalarySlip (or CustomSalarySlip) object for calculation.
        If slip is an object, use directly.
        If dict, fetch doc from DB or construct object.
        """
        if hasattr(slip, "calculate_income_tax"):
            return slip  # already a slip object
        elif isinstance(slip, dict):
            # Try fetch from DB if possible, else construct dummy object
            if "name" in slip:
                try:
                    slip_obj = frappe.get_doc("Salary Slip", slip["name"])
                except Exception:
                    from payroll_indonesia.override.salary_slip import CustomSalarySlip
                    slip_obj = CustomSalarySlip(**slip)
            else:
                from payroll_indonesia.override.salary_slip import CustomSalarySlip
                slip_obj = CustomSalarySlip(**slip)
            return slip_obj
        else:
            return slip  # fallback

    def _get_employee_doc(self, slip):
        """
        Helper untuk mengambil data employee (dict), bisa dari slip atau fetch dari DB.
        """
        if hasattr(slip, "employee"):
            if isinstance(slip.employee, dict):
                return slip.employee
            else:
                return frappe.get_doc("Employee", slip.employee)
        if isinstance(slip, dict) and "employee" in slip:
            if isinstance(slip["employee"], dict):
                return slip["employee"]
            else:
                return frappe.get_doc("Employee", slip["employee"])
        return {}
