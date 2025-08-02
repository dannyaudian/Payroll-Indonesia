try:
    from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry
except ImportError:
    # Fail hard if HRMS is missing - this is critical
    import frappe
    frappe.throw(
        "Required module 'hrms.payroll.doctype.payroll_entry.payroll_entry' is missing. "
        "Please make sure HRMS app is installed.",
        title="Missing Dependency"
    )

import frappe
import traceback
from typing import Callable, Dict, List, Any, Optional, Tuple
from payroll_indonesia.override.salary_slip import CustomSalarySlip
from payroll_indonesia.config import get_value

# Setup global logger for consistent logging.
# This logs to logs/payroll_indonesia.log via the site's configured loggers.
logger = frappe.logger("payroll_indonesia")

class CustomPayrollEntry(PayrollEntry):
    """
    Custom Payroll Entry for Payroll Indonesia.
    Override salary slip creation to use CustomSalarySlip with PPh21 TER/Desember logic.
    """

    def validate(self):
        super().validate()
        # Payroll Indonesia custom validation
        if getattr(self, "run_payroll_indonesia", False):
            logger.info("Payroll Entry: Run Payroll Indonesia is checked.")
            if hasattr(self, "pph21_method") and not self.pph21_method:
                self.pph21_method = get_value("pph21_method", "TER")
        if getattr(self, "run_payroll_indonesia_december", False):
            logger.info("Payroll Entry: Run Payroll Indonesia DECEMBER mode is checked.")
            # Add December-specific validation if needed
            
            # Verify CustomSalarySlip has the required December calculation method
            if not hasattr(CustomSalarySlip, "calculate_income_tax_december"):
                frappe.throw(
                    "Required method 'calculate_income_tax_december' is missing in CustomSalarySlip. "
                    "Please update the CustomSalarySlip class implementation.",
                    title="Missing Method"
                )

    def create_salary_slips(self):
        """
        Override: generate salary slips with Indonesian tax logic.
        """
        try:
            # Clean up any existing salary slips before creating new ones
            # This prevents duplicate salary slip errors when retrying after cancel
            self.delete_salary_slips(force_cleanup=True)
            
            if getattr(self, "run_payroll_indonesia_december", False):
                logger.info(
                    "Payroll Entry: Running Salary Slip generation for Payroll Indonesia DECEMBER (final year) mode."
                )
                return self._create_salary_slips_indonesia_december()
            elif getattr(self, "run_payroll_indonesia", False):
                logger.info(
                    "Payroll Entry: Running Salary Slip generation for Payroll Indonesia normal mode."
                )
                return self._create_salary_slips_indonesia()
            else:
                result = super().create_salary_slips()
                return result if result is not None else []
        except Exception as e:
            error_trace = traceback.format_exc()
            frappe.log_error(
                message=f"Failed to create salary slips for {self.name}: {str(e)}\n{error_trace}",
                title="Payroll Indonesia Salary Slip Creation Error"
            )
            return []
            
    def _create_base_slips(self) -> List[str]:
        """
        Helper to create base salary slips using the parent class.
        This centralizes the base slip creation to avoid code duplication.
        
        Returns:
            List of salary slip names created by the parent class
        """
        try:
            logger.debug(f"Starting base salary slip creation for {self.name}")
            
            # Call super to create base slips
            super().create_salary_slips()
            
            # Get and return slips created by super method
            actual_slips = self.get_salary_slips()
            logger.debug(f"Created {len(actual_slips)} base salary slips")
            return actual_slips
        except Exception as e:
            error_trace = traceback.format_exc()
            frappe.log_error(
                message=f"Failed to create base salary slips for {self.name}: {str(e)}\n{error_trace}",
                title="Payroll Indonesia Base Slip Creation Error"
            )
            return []

    def get_salary_slips(self) -> List[str]:
        """Return list of Salary Slip names linked to this Payroll Entry."""
        try:
            return frappe.get_all(
                "Salary Slip",
                filters={"payroll_entry": self.name},
                pluck="name"
            )
        except Exception as e:
            logger.error(f"Error retrieving salary slips for {self.name}: {str(e)}")
            return []

    def _create_salary_slips_indonesia(self) -> List[str]:
        """
        Generate salary slips with PPh21 TER (monthly) logic.
        Always return a list (empty if no slip).
        """
        try:
            # Create base slips using the parent class
            actual_slips = self._create_base_slips()
            
            if not actual_slips:
                logger.warning(f"No base salary slips created for {self.name}")
                return []
            
            def calculate_ter_tax(slip_obj: Any) -> None:
                """Calculate regular monthly TER tax for the slip."""
                slip_obj.calculate_income_tax()
            
            return self._process_salary_slips(calculate_ter_tax)
        except Exception as e:
            error_trace = traceback.format_exc()
            frappe.log_error(
                message=f"Failed to create Indonesian salary slips for {self.name}: {str(e)}\n{error_trace}",
                title="Payroll Indonesia TER Creation Error"
            )
            return []

    def _create_salary_slips_indonesia_december(self) -> List[str]:
        """
        Generate salary slips with PPh21 Desember (annual progressive) logic.
        Always return a list (empty if no slip).
        """
        try:
            # Create base slips using the parent class
            actual_slips = self._create_base_slips()
            
            if not actual_slips:
                logger.warning(f"No base salary slips created for December mode {self.name}")
                return []
            
            # Get Salary Slip doctype metadata once
            salary_slip_meta = frappe.get_meta("Salary Slip")
            
            def calculate_december_tax(slip_obj: Any) -> None:
                """Calculate December (annual progressive) tax for the slip."""
                # Ensure December tax type is set before validation or calculation
                setattr(slip_obj, "tax_type", "DECEMBER")
                
                # Calculate December (annual progressive) tax
                slip_obj.calculate_income_tax_december()
                
                # Persist tax-related fields so subsequent operations use the new values
                for field in ("tax", "tax_type", "pph21_info"):
                    try:
                        # Check if the field exists in the doctype before setting
                        if salary_slip_meta.has_field(field):
                            slip_obj.db_set(field, getattr(slip_obj, field))
                    except Exception as field_error:
                        # Best effort: attribute might not be saved yet
                        setattr(slip_obj, field, getattr(slip_obj, field))
            
            return self._process_salary_slips(calculate_december_tax)
        except Exception as e:
            error_trace = traceback.format_exc()
            frappe.log_error(
                message=f"Failed to create Indonesian December salary slips for {self.name}: {str(e)}\n{error_trace}",
                title="Payroll Indonesia December Creation Error"
            )
            return []

    def _process_salary_slips(self, tax_calculator: Callable[[Any], None]) -> List[str]:
        """
        Process salary slips with the provided tax calculation function.
        
        Args:
            tax_calculator: Callback function that calculates tax for a salary slip
                           Takes a salary slip object as parameter
        
        Returns:
            List of successfully processed salary slip names
        """
        # Get slips linked to this payroll entry
        slips = self.get_salary_slips() or []
        if not slips:
            logger.warning(f"No salary slips found for payroll entry {self.name}")
            return []
            
        logger.info(f"Processing {len(slips)} salary slips for payroll entry {self.name}")
        processed_slips: List[str] = []
        invalid_slips = []
        
        # Check if salary_slips child table exists before processing
        has_child_table = hasattr(self, "salary_slips")
        if has_child_table:
            # Build a map of salary slip references in the child table
            child_slip_map = {}
            for i, row in enumerate(self.salary_slips):
                slip_name = getattr(row, "salary_slip", None)
                if slip_name:
                    child_slip_map[slip_name] = i
        
        # Get Salary Slip doctype metadata once for field checks
        salary_slip_meta = frappe.get_meta("Salary Slip")
        
        # List of fields that are considered "light" (don't require full save)
        light_fields = {"tax", "tax_type", "pph21_info"}
        
        for name in slips:
            # First check if the slip exists to avoid unnecessary exceptions
            if not frappe.db.exists("Salary Slip", name):
                logger.warning(f"Salary Slip '{name}' not found in database. Skipping.")
                invalid_slips.append(name)
                continue
                
            try:
                slip_obj = frappe.get_doc("Salary Slip", name)
                
                # Store original values of light fields to check if they changed
                original_values = {}
                for field in light_fields:
                    if salary_slip_meta.has_field(field):
                        original_values[field] = getattr(slip_obj, field, None)
            except Exception as e:
                logger.warning(f"Error fetching Salary Slip '{name}': {str(e)}. Skipping.")
                invalid_slips.append(name)
                continue

            try:
                # Apply the provided tax calculation function
                tax_calculator(slip_obj)
                
                # Check if only light fields were modified
                only_light_fields_changed = True
                changed_fields = []
                
                # Check if light fields changed
                for field in light_fields:
                    if salary_slip_meta.has_field(field):
                        new_value = getattr(slip_obj, field, None)
                        if field in original_values and original_values[field] != new_value:
                            changed_fields.append(field)
                
                # Check if earnings or deductions tables were modified
                # This is more accurate than just checking for attribute existence
                earnings_modified = False
                deductions_modified = False
                
                # Check if earnings were modified (if the table exists)
                if hasattr(slip_obj, "earnings") and getattr(slip_obj, "earnings", None):
                    for row in slip_obj.earnings:
                        if row.modified or row.get("__islocal"):
                            earnings_modified = True
                            break
                
                # Check if deductions were modified (if the table exists)
                if hasattr(slip_obj, "deductions") and getattr(slip_obj, "deductions", None):
                    for row in slip_obj.deductions:
                        if row.modified or row.get("__islocal"):
                            deductions_modified = True
                            break
                
                # If no light fields changed OR earnings/deductions were modified, need full save
                if not changed_fields or earnings_modified or deductions_modified:
                    only_light_fields_changed = False
                
                # If only light fields changed, use db_set for each field
                if only_light_fields_changed:
                    for field in changed_fields:
                        slip_obj.db_set(field, getattr(slip_obj, field), update_modified=False)
                    logger.debug(f"Updated light fields for slip {name}: {', '.join(changed_fields)}")
                else:
                    # Full save needed
                    slip_obj.save(ignore_permissions=True)
                    logger.debug(f"Performed full save for slip {name}")
                
                # Submit the salary slip if auto_submit is enabled and slip is not already submitted
                if hasattr(self, "auto_submit_salary_slips") and self.auto_submit_salary_slips and slip_obj.docstatus == 0:
                    slip_obj.submit()
                    logger.info(f"Submitted salary slip: {name}")
                
                processed_slips.append(name)
                logger.info(f"Successfully processed slip: {name}")
            except Exception as e:
                error_trace = traceback.format_exc()
                tax_mode = "December" if getattr(slip_obj, "tax_type", "") == "DECEMBER" else "TER"
                frappe.log_error(
                    message=f"Failed to process {tax_mode} Salary Slip '{name}': {str(e)}\n{error_trace}",
                    title=f"Payroll Indonesia {tax_mode} Processing Error"
                )
                logger.error(f"Error processing {tax_mode} Salary Slip '{name}': {str(e)}")
                invalid_slips.append(name)
        
        # Remove invalid slips from the salary_slips child table
        child_table_modified = False
        if invalid_slips and has_child_table:
            # Process in reverse order to avoid index shifting problems
            invalid_indices = [child_slip_map[name] for name in invalid_slips 
                              if name in child_slip_map]
            invalid_indices.sort(reverse=True)
            for i in invalid_indices:
                self.salary_slips.pop(i)
                child_table_modified = True
            
            logger.info(f"Removed {len(invalid_indices)} invalid slips from child table")
            
            # Save the document after modifying the child table
            if child_table_modified:
                self.save(ignore_permissions=True)
        
        # Update the salary_slips_created field based on actual successful slips
        if hasattr(self, "salary_slips_created"):
            self.salary_slips_created = len(processed_slips)
            self.db_set("salary_slips_created", self.salary_slips_created, update_modified=False)
            logger.info(f"Updated salary_slips_created to {len(processed_slips)}")
        
        if processed_slips:
            logger.info(f"Successfully processed {len(processed_slips)} salary slips")
        else:
            logger.warning("No salary slips were successfully processed")
            
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
        
    def on_cancel(self):
        """
        Handle cancellation of Payroll Entry with proper salary slip cleanup.
        Overrides the base PayrollEntry.on_cancel method to ensure robust error handling.
        """
        try:
            # Set ignore_links flag to skip document link validation
            self.flags.ignore_links = True
            
            # Call delete_salary_slips helper to handle cleanup
            self.delete_salary_slips()
            
            # Cancel linked journal entries
            self.cancel_linked_journal_entries()
            
            # Reset flags & update status
            self.db_set("salary_slips_created", 0)
            self.db_set("salary_slips_submitted", 0)
            self.set_status(update=True, status="Cancelled")
            self.db_set("error_message", "")
            
            logger.info(f"Successfully canceled Payroll Entry {self.name}")
        except Exception as e:
            error_trace = traceback.format_exc()
            frappe.log_error(
                message=f"Error canceling Payroll Entry {self.name}: {str(e)}\n{error_trace}",
                title="Payroll Indonesia Cancel Error"
            )
            # Re-raise the exception to notify the user
            raise
    
    def delete_salary_slips(self, force_cleanup=False):
        """
        Delete all salary slips linked to this Payroll Entry.
        This implementation ensures that all salary slips are completely removed,
        allowing the user to create a new Payroll Entry for the same period without conflicts.
        
        Args:
            force_cleanup: If True, performs cleanup of salary slips even if not canceling
                          Used when creating new salary slips to prevent duplicates
        """
        try:
            # Acquire a lock to prevent race conditions when multiple processes
            # might be trying to delete/clean up salary slips
            lock_key = f"delete_salary_slips_{self.name}"
            if not frappe.cache().exists(lock_key):
                frappe.cache().set(lock_key, True, expires_in_sec=300)  # 5 minute lock
            else:
                logger.warning(f"Another process is already deleting salary slips for {self.name}. Waiting...")
                # Wait for lock to clear (max 30 seconds)
                for _ in range(30):
                    import time
                    time.sleep(1)
                    if not frappe.cache().exists(lock_key):
                        break
                else:
                    # Lock didn't clear in time
                    raise Exception(f"Timeout waiting for salary slip deletion lock to clear for {self.name}")
                
                # Re-acquire the lock
                frappe.cache().set(lock_key, True, expires_in_sec=300)
            
            try:
                # Get all salary slips linked to this Payroll Entry
                salary_slips = self.get_linked_salary_slips()
                
                if not salary_slips:
                    logger.info(f"No salary slips found to delete for Payroll Entry {self.name}")
                    return
                    
                action = "Cleaning up" if force_cleanup else "Deleting"
                logger.info(f"{action} {len(salary_slips)} salary slips for Payroll Entry {self.name}")
                
                # Process each salary slip: cancel if submitted, then delete
                for slip in salary_slips:
                    try:
                        slip_name = slip.name
                        
                        # Skip if slip doesn't exist (already deleted)
                        if not frappe.db.exists("Salary Slip", slip_name):
                            continue
                            
                        # Cancel if submitted (docstatus == 1)
                        if slip.docstatus == 1:
                            logger.info(f"Canceling Salary Slip {slip_name}")
                            frappe.get_doc("Salary Slip", slip_name).cancel()
                        
                        # Delete with force=True and ignore_permissions=True to bypass restrictions
                        logger.info(f"Deleting Salary Slip {slip_name}")
                        frappe.delete_doc("Salary Slip", slip_name, force=True, ignore_permissions=True)
                        
                    except Exception as slip_error:
                        # Log error but continue with other slips
                        error_trace = traceback.format_exc()
                        frappe.log_error(
                            message=f"Error deleting Salary Slip {slip.name}: {str(slip_error)}\n{error_trace}",
                            title="Payroll Indonesia Salary Slip Deletion Error"
                        )
                        logger.warning(f"Error deleting Salary Slip {slip.name}: {str(slip_error)}")
                
                logger.info(f"Successfully {action.lower()} all salary slips for Payroll Entry {self.name}")
                
            finally:
                # Always release the lock when done
                frappe.cache().delete(lock_key)
                
        except Exception as e:
            error_trace = traceback.format_exc()
            frappe.log_error(
                message=f"Failed to delete salary slips for Payroll Entry {self.name}: {str(e)}\n{error_trace}",
                title="Payroll Indonesia Salary Slip Deletion Error"
            )
            logger.error(f"Error in delete_salary_slips: {str(e)}")
            
    def get_linked_salary_slips(self):
        """
        Get all Salary Slips linked to this Payroll Entry.
        Returns a list of salary slip documents.
        """
        try:
            return frappe.get_all(
                "Salary Slip",
                filters={"payroll_entry": self.name},
                fields=["name", "docstatus"],
                as_list=0
            )
        except Exception as e:
            logger.error(f"Error retrieving linked salary slips for {self.name}: {str(e)}")
            return []
            
    def cancel_linked_journal_entries(self):
        """
        Cancel all Journal Entries linked to this Payroll Entry.
        """
        try:
            journal_entries = frappe.get_all(
                "Journal Entry Account",
                {"reference_type": self.doctype, "reference_name": self.name, "docstatus": 1},
                pluck="parent",
                distinct=True,
            )
            
            if not journal_entries:
                logger.info(f"No journal entries found to cancel for Payroll Entry {self.name}")
                return
                
            logger.info(f"Canceling {len(journal_entries)} journal entries for Payroll Entry {self.name}")
            
            # Cancel each journal entry
            for je in journal_entries:
                try:
                    frappe.get_doc("Journal Entry", je).cancel()
                    logger.info(f"Canceled Journal Entry {je}")
                except Exception as je_error:
                    # Log error but continue with other journal entries
                    error_trace = traceback.format_exc()
                    frappe.log_error(
                        message=f"Error canceling Journal Entry {je}: {str(je_error)}\n{error_trace}",
                        title="Payroll Indonesia Journal Entry Cancellation Error"
                    )
                    logger.warning(f"Error canceling Journal Entry {je}: {str(je_error)}")
            
            logger.info(f"Successfully canceled all journal entries for Payroll Entry {self.name}")
            
        except Exception as e:
            error_trace = traceback.format_exc()
            frappe.log_error(
                message=f"Failed to cancel journal entries for Payroll Entry {self.name}: {str(e)}\n{error_trace}",
                title="Payroll Indonesia Journal Entry Cancellation Error"
            )
            logger.error(f"Error in cancel_linked_journal_entries: {str(e)}")