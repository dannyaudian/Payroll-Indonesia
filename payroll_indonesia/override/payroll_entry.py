try:
    from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry
except Exception:
    PayrollEntry = object  # fallback for tests/static analysis

import frappe
import traceback
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
        invalid_slips = []
        
        for name in slips:
            # First check if the slip exists to avoid unnecessary exceptions
            if not frappe.db.exists("Salary Slip", name):
                frappe.logger().warning(
                    f"Payroll Entry: Salary Slip '{name}' not found. Removing from list."
                )
                invalid_slips.append(name)
                continue
                
            try:
                slip_obj = frappe.get_doc("Salary Slip", name)
            except Exception as e:
                frappe.logger().warning(
                    f"Payroll Entry: Error fetching Salary Slip '{name}': {str(e)}. Skipping."
                )
                invalid_slips.append(name)
                continue

            try:
                slip_obj.calculate_income_tax()
                slip_obj.save(ignore_permissions=True)
                processed_slips.append(name)
            except Exception as e:
                error_trace = traceback.format_exc()
                frappe.log_error(
                    message=f"Failed to process Salary Slip '{name}': {str(e)}\n{error_trace}",
                    title="Payroll Indonesia TER Processing Error"
                )
                frappe.logger().error(
                    f"Payroll Entry: Error processing Salary Slip '{name}': {str(e)}"
                )
                invalid_slips.append(name)
        
        # Remove invalid slips from the salary_slips child table
        if invalid_slips and hasattr(self, "salary_slips"):
            for i, row in reversed(list(enumerate(self.salary_slips))):
                if hasattr(row, "salary_slip") and row.salary_slip in invalid_slips:
                    self.salary_slips.pop(i)
        
        # Update the salary_slips_created field based on actual successful slips
        if hasattr(self, "salary_slips_created"):
            self.salary_slips_created = len(processed_slips)
            self.db_set("salary_slips_created", self.salary_slips_created, update_modified=False)
        
        return processed_slips

    def _create_salary_slips_indonesia_december(self):
        """
        Generate salary slips with PPh21 Desember (annual progressive) logic.
        Always return a list (empty if no slip).
        """
        super().create_salary_slips()
        slips = self.get_salary_slips() or []
        processed_slips = []
        invalid_slips = []
        
        for name in slips:
            # First check if the slip exists to avoid unnecessary exceptions
            if not frappe.db.exists("Salary Slip", name):
                frappe.logger().warning(
                    f"Payroll Entry: Salary Slip '{name}' not found. Removing from list."
                )
                invalid_slips.append(name)
                continue
                
            try:
                slip_obj = frappe.get_doc("Salary Slip", name)
            except Exception as e:
                frappe.logger().warning(
                    f"Payroll Entry: Error fetching Salary Slip '{name}': {str(e)}. Skipping."
                )
                invalid_slips.append(name)
                continue

            try:
                # Ensure December tax type is set before validation or calculation
                setattr(slip_obj, "tax_type", "DECEMBER")

                # Calculate December (annual progressive) tax on first pass
                slip_obj.calculate_income_tax_december()

                # Persist tax-related fields (tax, tax_type, pph21_info) so
                # subsequent operations use the new values
                for field in ("tax", "tax_type", "pph21_info"):
                    try:
                        slip_obj.db_set(field, getattr(slip_obj, field))
                    except Exception as field_error:
                        error_trace = traceback.format_exc()
                        frappe.log_error(
                            message=f"Failed to set field {field} on Salary Slip '{name}': {str(field_error)}\n{error_trace}",
                            title="Payroll Indonesia December Field Update Error"
                        )
                        # Best effort: attribute might not be saved yet
                        setattr(slip_obj, field, getattr(slip_obj, field))

                # Always save the slip to persist deduction rows (e.g. PPh 21)
                slip_obj.save(ignore_permissions=True)
                processed_slips.append(name)
            except Exception as e:
                error_trace = traceback.format_exc()
                frappe.log_error(
                    message=f"Failed to process December Salary Slip '{name}': {str(e)}\n{error_trace}",
                    title="Payroll Indonesia December Processing Error"
                )
                frappe.logger().error(
                    f"Payroll Entry: Error processing December Salary Slip '{name}': {str(e)}"
                )
                invalid_slips.append(name)

        # Remove invalid slips from the salary_slips child table
        if invalid_slips and hasattr(self, "salary_slips"):
            for i, row in reversed(list(enumerate(self.salary_slips))):
                if hasattr(row, "salary_slip") and row.salary_slip in invalid_slips:
                    self.salary_slips.pop(i)
        
        # Update the salary_slips_created field based on actual successful slips
        if hasattr(self, "salary_slips_created"):
            self.salary_slips_created = len(processed_slips)
            self.db_set("salary_slips_created", self.salary_slips_created, update_modified=False)
        
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