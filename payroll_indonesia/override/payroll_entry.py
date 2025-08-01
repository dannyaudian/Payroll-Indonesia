try:
    from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry
except Exception:
    PayrollEntry = object  # fallback for tests/static analysis

import frappe
import traceback
from typing import Callable, Dict, List, Any, Optional
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

    def get_salary_slips(self) -> List[str]:
        """
        Return list of Salary Slip names linked to this Payroll Entry.
        Only includes draft (docstatus=0) and submitted (docstatus=1) salary slips, 
        excluding cancelled ones (docstatus=2).
        """
        return frappe.get_all(
            "Salary Slip", 
            filters={
                "payroll_entry": self.name,
                "docstatus": ["<", 2]  # Only draft (0) and submitted (1) slips
            }, 
            pluck="name"
        )

    def _create_salary_slips_indonesia(self) -> List[str]:
        """
        Generate salary slips with PPh21 TER (monthly) logic.
        Always return a list (empty if no slip).
        """
        super().create_salary_slips()
        
        def calculate_ter_tax(slip_obj: Any) -> None:
            """Calculate regular monthly TER tax for the slip."""
            slip_obj.calculate_income_tax()
        
        return self._process_salary_slips(calculate_ter_tax)

    def _create_salary_slips_indonesia_december(self) -> List[str]:
        """
        Generate salary slips with PPh21 Desember (annual progressive) logic.
        Always return a list (empty if no slip).
        """
        super().create_salary_slips()
        
        def calculate_december_tax(slip_obj: Any) -> None:
            """Calculate December (annual progressive) tax for the slip."""
            # Ensure December tax type is set before validation or calculation
            setattr(slip_obj, "tax_type", "DECEMBER")
            
            # Calculate December (annual progressive) tax
            slip_obj.calculate_income_tax_december()
            
            # Persist tax-related fields so subsequent operations use the new values
            for field in ("tax", "tax_type", "pph21_info"):
                try:
                    slip_obj.db_set(field, getattr(slip_obj, field))
                except Exception as field_error:
                    error_trace = traceback.format_exc()
                    frappe.log_error(
                        message=f"Failed to set field {field} on Salary Slip '{slip_obj.name}': {str(field_error)}\n{error_trace}",
                        title="Payroll Indonesia December Field Update Error"
                    )
                    # Best effort: attribute might not be saved yet
                    setattr(slip_obj, field, getattr(slip_obj, field))
        
        return self._process_salary_slips(calculate_december_tax)

    def _process_salary_slips(self, tax_calculator: Callable[[Any], None]) -> List[str]:
        """
        Process salary slips with the provided tax calculation function.
        
        Args:
            tax_calculator: Callback function that calculates tax for a salary slip
                           Takes a salary slip object as parameter
        
        Returns:
            List of successfully processed salary slip names
        """
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
                # Apply the provided tax calculation function
                tax_calculator(slip_obj)
                
                # Save the slip to persist changes
                slip_obj.save(ignore_permissions=True)
                processed_slips.append(name)
            except Exception as e:
                error_trace = traceback.format_exc()
                tax_mode = "December" if getattr(slip_obj, "tax_type", "") == "DECEMBER" else "TER"
                frappe.log_error(
                    message=f"Failed to process {tax_mode} Salary Slip '{name}': {str(e)}\n{error_trace}",
                    title=f"Payroll Indonesia {tax_mode} Processing Error"
                )
                frappe.logger().error(
                    f"Payroll Entry: Error processing {tax_mode} Salary Slip '{name}': {str(e)}"
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