# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:38:52 by dannyaudian

"""
Controller for Payroll Entry customization for Indonesian payroll.
"""

from typing import Any, Dict, List, Optional

import frappe
from frappe import _
from frappe.utils import getdate, flt
from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry

import payroll_indonesia.payroll_indonesia.validations as validations
import payroll_indonesia.override.payroll_entry_functions as pe_functions
from payroll_indonesia.config.config import get_live_config
from payroll_indonesia.frappe_helpers import logger


class CustomPayrollEntry(PayrollEntry):
    """
    Extends standard PayrollEntry with Indonesia-specific functionality.
    All complex tax and BPJS logic is delegated to specialized modules.
    """

    def validate(self) -> None:
        """
        Validate Payroll Entry with Indonesian-specific requirements.
        """
        try:
            # Call parent validation first
            super().validate()

            # Validate December logic
            self._validate_december_logic()
            
            # Validate TER method logic
            self._validate_ter_method_logic()

            # Validate employees if applicable
            self._validate_employees()

            # Validate configuration settings
            self._validate_config()

            logger.info(f"Validated Payroll Entry {self.name}")
        except Exception as e:
            logger.exception(f"Error validating Payroll Entry {self.name}: {e}")
            frappe.throw(_("Error validating Payroll Entry: {0}").format(str(e)))

    def _validate_december_logic(self) -> None:
        """
        Log December override mode status without any date validation.

        This method simply checks if the December override flag is enabled
        and logs the status without validating dates or month periods.
        """
        # Check if December override is enabled
        is_december = self.get("is_december_override", 0)

        if is_december:
            # Log that December mode is active without any date validation
            logger.info(
                f"Payroll Entry {self.name} is using December override mode for annual tax calculation"
            )

            # Add a message for the user for clarity
            frappe.msgprint(
                _(
                    "December override mode is active: Annual tax calculation and correction "
                    "will be applied to all salary slips generated from this Payroll Entry."
                ),
                indicator="blue",
                alert=True
            )
        else:
            # Optionally log that regular mode is being used
            logger.debug(f"Payroll Entry {self.name} using regular monthly tax calculation")
    
    def _validate_ter_method_logic(self) -> None:
        """
        Log TER method status.
        
        This method checks if the TER method flag is enabled and logs the status.
        """
        # Check if TER method is enabled
        use_ter = self.get("use_ter_method", 0)
        
        if use_ter:
            # Log that TER method is active
            logger.info(
                f"Payroll Entry {self.name} is using TER method for tax calculation"
            )
            
            # Add a message for the user for clarity
            frappe.msgprint(
                _(
                    "TER method is active: Tax will be calculated using TER rates "
                    "for all eligible employees in this Payroll Entry."
                ),
                indicator="blue",
                alert=True
            )
        else:
            # Optionally log that standard progressive method is being used
            logger.debug(f"Payroll Entry {self.name} using standard progressive tax calculation")
            
    def _validate_employees(self) -> None:
        """
        Validate employee data required for Indonesian payroll.
        """
        # Only proceed if employees are already populated
        if not hasattr(self, "employees") or not self.employees:
            return

        # Get employee IDs
        employee_ids = [e.employee for e in self.employees if e.employee]

        if employee_ids:
            # Validate employee fields
            for emp_id in employee_ids:
                try:
                    validations.validate_employee_fields(emp_id)
                except AttributeError:
                    # Handle missing validation function gracefully
                    logger.warning(
                        f"validate_employee_fields not found in validations module. "
                        f"Skipping validation for {emp_id}"
                    )
                except Exception as e:
                    logger.error(f"Error validating employee {emp_id}: {str(e)}")
                    raise

    def _validate_config(self) -> None:
        """
        Validate configuration settings.
        """
        cfg = get_live_config()

        # Check tax configuration if applicable
        tax_config = cfg.get("tax", {})
        if not tax_config:
            frappe.msgprint(
                _("Tax configuration not found. Using system defaults."), indicator="yellow"
            )

        # Check BPJS configuration if applicable
        bpjs_config = cfg.get("bpjs", {})
        if not bpjs_config:
            frappe.msgprint(
                _("BPJS configuration not found. Using system defaults."), indicator="yellow"
            )

    def on_submit(self) -> None:
        """
        Process Payroll Entry on submission.
        Delegates to payroll_entry_functions.post_submit().
        """
        try:
            # Create salary slips if needed
            if not self._has_salary_slips():
                self.create_salary_slips()
            else:
                # Update existing slips with flags if needed
                self._update_existing_slips_flags()

            # Submit salary slips using dedicated function
            result = pe_functions.post_submit(self)

            # Log result
            if result.get("status") == "success":
                logger.info(
                    f"Successfully processed Payroll Entry {self.name}: {result.get('message')}"
                )
            else:
                logger.warning(
                    f"Partially processed Payroll Entry {self.name}: {result.get('message')}"
                )

                # Show message to user
                frappe.msgprint(
                    result.get("message", _("Some issues occurred during processing")),
                    indicator="yellow" if result.get("status") == "partial" else "red",
                )
        except Exception as e:
            logger.exception(f"Error submitting Payroll Entry {self.name}: {e}")
            frappe.throw(_("Error submitting Payroll Entry: {0}").format(str(e)))

    def _has_salary_slips(self) -> bool:
        """
        Check if salary slips have already been created for this Payroll Entry.

        Returns:
            bool: True if salary slips exist
        """
        return bool(
            frappe.db.exists(
                "Salary Slip", {"payroll_entry": self.name, "docstatus": ["in", [0, 1]]}
            )
        )
        
    def _update_existing_slips_flags(self) -> None:
        """
        Update existing salary slips with the current flags.
        
        Only updates slips where the flags haven't been manually set, to avoid
        overriding user preferences. This ensures that all slips attached to
        this Payroll Entry have consistent flags.
        """
        try:
            # Get all draft salary slips for this payroll entry
            slips = frappe.get_all(
                "Salary Slip",
                filters={
                    "payroll_entry": self.name,
                    "docstatus": 0,  # Only update draft slips
                },
                fields=["name", "is_december_override", "use_ter_method"]
            )
            
            if not slips:
                return
                
            # Count of slips updated
            updated_count = 0
            
            for slip in slips:
                fields_to_update = {}
                
                # Check December override flag
                if hasattr(self, "is_december_override") and self.is_december_override:
                    if not slip.get("is_december_override"):
                        fields_to_update["is_december_override"] = 1
                
                # Check TER method flag
                if hasattr(self, "use_ter_method") and self.use_ter_method:
                    if not slip.get("use_ter_method"):
                        fields_to_update["use_ter_method"] = 1
                
                # Update if we have fields to change
                if fields_to_update:
                    frappe.db.set_value(
                        "Salary Slip",
                        slip.name,
                        fields_to_update,
                        update_modified=False
                    )
                    updated_count += 1
                
            if updated_count > 0:
                logger.info(f"Updated flags on {updated_count} existing salary slips")
                
        except Exception as e:
            logger.warning(f"Error updating existing slips' flags: {str(e)}")

    def make_payment_entry(self) -> Dict[str, Any]:
        """
        Create payment entry for salary payments.
        Includes employer contributions.

        Returns:
            Dict[str, Any]: Payment entry data
        """
        payment_entry = super().make_payment_entry()

        # Calculate employer contributions
        employer_contributions = pe_functions.calculate_employer_contributions(self)

        # Add employer contribution information if available
        if employer_contributions and payment_entry:
            # Convert to dict if not already
            if not isinstance(payment_entry, dict):
                payment_entry = payment_entry.as_dict()

            # Add employer contribution info
            payment_entry["employer_contributions"] = employer_contributions

            # Add to title/remarks
            payment_entry["user_remark"] = (
                f"{payment_entry.get('user_remark', '')} "
                f"(Including employer contributions: "
                f"{employer_contributions.get('total', 0)})"
            )

        return payment_entry

    def create_salary_slips(self) -> List[str]:
        """
        Override the standard create_salary_slips method to propagate
        flags to Salary Slips.
        
        Returns:
            List[str]: List of created Salary Slip names
        """
        # Before calling parent implementation, store flags we need to apply
        apply_december = hasattr(self, "is_december_override") and self.is_december_override
        apply_ter = hasattr(self, "use_ter_method") and self.use_ter_method
        
        if apply_december or apply_ter:
            flag_info = []
            if apply_december:
                flag_info.append("December override")
            if apply_ter:
                flag_info.append("TER method")
            
            logger.info(f"Will apply flags to new salary slips from {self.name}: {', '.join(flag_info)}")
        
        # Get the result from the parent implementation
        salary_slips = super().create_salary_slips()
        
        # Propagate flags to all created salary slips
        if salary_slips and (apply_december or apply_ter):
            logger.info(f"Propagating flags to {len(salary_slips)} salary slips")
            
            # Update all created salary slips with flags
            for slip_name in salary_slips:
                try:
                    # Build a dict of fields to update
                    fields_to_update = {}
                    
                    # Check December override
                    if apply_december:
                        existing_override = frappe.db.get_value("Salary Slip", slip_name, "is_december_override")
                        if not existing_override:
                            fields_to_update["is_december_override"] = 1
                    
                    # Check TER method
                    if apply_ter:
                        existing_ter = frappe.db.get_value("Salary Slip", slip_name, "use_ter_method")
                        if not existing_ter:
                            fields_to_update["use_ter_method"] = 1
                    
                    # Update fields if needed
                    if fields_to_update:
                        frappe.db.set_value(
                            "Salary Slip", 
                            slip_name, 
                            fields_to_update, 
                            update_modified=False
                        )
                        logger.debug(f"Set flags for slip {slip_name}: {fields_to_update}")
                        
                except Exception as e:
                    logger.error(f"Failed to set flags for {slip_name}: {str(e)}")
        
        return salary_slips

    def get_sal_slip_list(self, ss_status: int = 0, as_dict: bool = False) -> List[Any]:
        """
        Override the standard get_sal_slip_list method to ensure 
        proper filtering and flags are maintained.
        
        This method is called by various Payroll Entry methods 
        when processing salary slips.
        
        Args:
            ss_status: Filter by docstatus (0=Draft, 1=Submitted, 2=Cancelled)
            as_dict: Return as dictionary instead of list of names
            
        Returns:
            List of salary slip documents or names
        """
        # Get the original list from parent method
        sal_slips = super().get_sal_slip_list(ss_status, as_dict)
        
        # Only update flags if we're getting draft slips and have slips to update
        if ss_status == 0 and sal_slips:
            # Check if we need to apply any flags
            apply_december = hasattr(self, "is_december_override") and self.is_december_override
            apply_ter = hasattr(self, "use_ter_method") and self.use_ter_method
            
            if apply_december or apply_ter:
                try:
                    # Get the list of slip names
                    slip_names = [slip.name for slip in sal_slips] if as_dict else sal_slips
                    
                    # Update slips in batch for efficiency
                    for slip_name in slip_names:
                        fields_to_update = {}
                        
                        # Check December override
                        if apply_december:
                            existing_override = frappe.db.get_value("Salary Slip", slip_name, "is_december_override")
                            if not existing_override:
                                fields_to_update["is_december_override"] = 1
                        
                        # Check TER method
                        if apply_ter:
                            existing_ter = frappe.db.get_value("Salary Slip", slip_name, "use_ter_method")
                            if not existing_ter:
                                fields_to_update["use_ter_method"] = 1
                        
                        # Update fields if needed
                        if fields_to_update:
                            frappe.db.set_value(
                                "Salary Slip", 
                                slip_name, 
                                fields_to_update, 
                                update_modified=False
                            )
                    
                    logger.debug(f"Checked flags for {len(slip_names)} salary slips")
                    
                except Exception as e:
                    logger.warning(f"Error checking flags in get_sal_slip_list: {str(e)}")
        
        return sal_slips

    def create_salary_slips_from_timesheets(self) -> None:
        """
        Create salary slips for employees with timesheets.
        Delegates to payroll_entry_functions.make_slips_from_timesheets().
        """
        if not getattr(self, "salary_slip_based_on_timesheet", 0):
            frappe.msgprint(_("This payroll is not based on timesheets"))
            return

        created_slips = pe_functions.make_slips_from_timesheets(self)
        
        # If no slips were created, show message and return
        if not created_slips:
            frappe.msgprint(
                _(
                    "No salary slips created from timesheets. "
                    "Check if timesheets exist for this period."
                )
            )
            return
            
        # Check if we need to apply any flags
        apply_december = hasattr(self, "is_december_override") and self.is_december_override
        apply_ter = hasattr(self, "use_ter_method") and self.use_ter_method
        
        # Propagate flags to timesheet-based salary slips
        if apply_december or apply_ter:
            flag_info = []
            if apply_december:
                flag_info.append("December override")
            if apply_ter:
                flag_info.append("TER method")
                
            logger.info(f"Propagating flags to {len(created_slips)} timesheet-based salary slips: {', '.join(flag_info)}")
            
            for slip in created_slips:
                try:
                    # Get the slip name from the result
                    slip_name = slip if isinstance(slip, str) else getattr(slip, "name", None)
                    if slip_name:
                        # Build a dict of fields to update
                        fields_to_update = {}
                        
                        # Check December override
                        if apply_december:
                            existing_override = frappe.db.get_value("Salary Slip", slip_name, "is_december_override")
                            if not existing_override:
                                fields_to_update["is_december_override"] = 1
                        
                        # Check TER method
                        if apply_ter:
                            existing_ter = frappe.db.get_value("Salary Slip", slip_name, "use_ter_method")
                            if not existing_ter:
                                fields_to_update["use_ter_method"] = 1
                        
                        # Update fields if needed
                        if fields_to_update:
                            frappe.db.set_value(
                                "Salary Slip", 
                                slip_name, 
                                fields_to_update, 
                                update_modified=False
                            )
                            logger.debug(f"Set flags for timesheet slip {slip_name}: {fields_to_update}")
                except Exception as e:
                    logger.error(f"Failed to set flags for timesheet slip: {str(e)}")

        frappe.msgprint(
            _("Created {0} salary slips from timesheets").format(len(created_slips))
        )

    def fill_employee_details(self) -> None:
        """
        Populate employee details with validation.
        """
        # Call parent implementation
        super().fill_employee_details()

        # Additional validation for Indonesian payroll
        self._validate_employees()