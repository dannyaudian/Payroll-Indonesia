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
        # Payroll Indonesia custom validation
        if getattr(self, "run_payroll_indonesia", False):
            frappe.logger().info("Payroll Entry: Run Payroll Indonesia is checked.")
            if hasattr(self, "pph21_method") and not self.pph21_method:
                self.pph21_method = get_value("pph21_method", "TER")
        if getattr(self, "run_payroll_indonesia_december", False):
            frappe.logger().info("Payroll Entry: Run Payroll Indonesia DECEMBER mode is checked.")
            # Add December-specific validation if needed

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

    def get_salary_slips(self):
        """Return list of Salary Slip names linked to this Payroll Entry."""
        return frappe.get_all(
            "Salary Slip", filters={"payroll_entry": self.name}, pluck="name"
        )

    def _create_salary_slips_indonesia(self):
        """
        Generate salary slips with PPh21 TER (monthly) logic.
        Always return a list (empty if no slip).
        """
        super().create_salary_slips()
        slips = self.get_salary_slips() or []
        processed_slips = []
        for name in slips:
            exists = True
            try:
                exists = frappe.db.exists("Salary Slip", name)
            except Exception:
                # Fallback if frappe.db is not available (e.g. tests)
                exists = True
            if not exists:
                frappe.logger().warning(
                    f"Payroll Entry: Salary Slip '{name}' not found. Removing from child table."
                )
                try:
                    if hasattr(self, "salary_slips"):
                        self.salary_slips = [
                            row
                            for row in self.salary_slips
                            if getattr(row, "salary_slip", "") != name
                        ]
                except Exception:
                    pass
                continue

            try:
                slip_obj = frappe.get_doc("Salary Slip", name)
            except frappe.DoesNotExistError:
                frappe.logger().warning(
                    f"Payroll Entry: Salary Slip '{name}' not found. Skipping."
                )
                continue
            except Exception:
                frappe.logger().warning(
                    f"Payroll Entry: Error fetching Salary Slip '{name}'. Skipping."
                )
                continue

            slip_obj.calculate_income_tax()
            try:
                slip_obj.save(ignore_permissions=True)
            except Exception:
                frappe.logger().warning(
                    f"Payroll Entry: Failed saving Salary Slip '{name}'."
                )
                continue
            processed_slips.append(name)

        count = len(processed_slips)
        try:
            self.db_set("salary_slips_created", count)
        except Exception:
            setattr(self, "salary_slips_created", count)
        return processed_slips

    def _create_salary_slips_indonesia_december(self):
        """
        Generate salary slips with PPh21 Desember (annual progressive) logic.
        Always return a list (empty if no slip).
        """
        super().create_salary_slips()
        slips = self.get_salary_slips() or []
        processed_slips = []
        for name in slips:
            exists = True
            try:
                exists = frappe.db.exists("Salary Slip", name)
            except Exception:
                exists = True
            if not exists:
                frappe.logger().warning(
                    f"Payroll Entry: Salary Slip '{name}' not found. Removing from child table."
                )
                try:
                    if hasattr(self, "salary_slips"):
                        self.salary_slips = [
                            row
                            for row in self.salary_slips
                            if getattr(row, "salary_slip", "") != name
                        ]
                except Exception:
                    pass
                continue

            try:
                slip_obj = frappe.get_doc("Salary Slip", name)
            except frappe.DoesNotExistError:
                frappe.logger().warning(
                    f"Payroll Entry: Salary Slip '{name}' not found. Skipping."
                )
                continue
            except Exception:
                frappe.logger().warning(
                    f"Payroll Entry: Error fetching Salary Slip '{name}'. Skipping."
                )
                continue

            # Ensure December tax type is set before validation or calculation
            setattr(slip_obj, "tax_type", "DECEMBER")

            # Calculate December (annual progressive) tax on first pass
            slip_obj.calculate_income_tax_december()

            # Persist tax-related fields (tax, tax_type, pph21_info) so
            # subsequent operations use the new values
            for field in ("tax", "tax_type", "pph21_info"):
                try:
                    slip_obj.db_set(field, getattr(slip_obj, field))
                except Exception:
                    # Best effort: attribute might not be saved yet
                    setattr(slip_obj, field, getattr(slip_obj, field))

            # Always save the slip to persist deduction rows (e.g. PPh 21)
            try:
                slip_obj.save(ignore_permissions=True)
            except Exception:
                frappe.logger().warning(
                    f"Payroll Entry: Failed saving Salary Slip '{name}'."
                )
                continue
            processed_slips.append(name)

        count = len(processed_slips)
        try:
            self.db_set("salary_slips_created", count)
        except Exception:
            setattr(self, "salary_slips_created", count)
        return processed_slips

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
