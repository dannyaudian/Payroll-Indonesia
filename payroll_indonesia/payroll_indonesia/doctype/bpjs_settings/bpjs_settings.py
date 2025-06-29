# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 03:44:29 by dannyaudian

"""
BPJS Settings DocType controller.

Handles validation and setup of BPJS (social security) settings
using configuration from defaults.json.
"""

from typing import Dict, Any, List, Optional, Union, Tuple

from frappe import _
import frappe
from frappe.model.document import Document

from payroll_indonesia.config.config import get_config as get_default_config
from payroll_indonesia.payroll_indonesia.utils import (
    get_or_create_account, debug_log
)


class BPJSSettings(Document):
    """
    Controller for BPJS Settings DocType.
    
    Manages Indonesian social security contribution settings, account configuration,
    and synchronization with central configuration.
    
    Attributes:
        kesehatan_employee_percent (float): Health insurance employee contribution rate
        kesehatan_employer_percent (float): Health insurance employer contribution rate 
        kesehatan_max_salary (float): Maximum salary for health insurance calculation
        jht_employee_percent (float): Old age employee contribution rate
        jht_employer_percent (float): Old age employer contribution rate
        jp_employee_percent (float): Pension plan employee contribution rate
        jp_employer_percent (float): Pension plan employer contribution rate
        jp_max_salary (float): Maximum salary for pension calculation
        jkk_percent (float): Work accident insurance employer contribution rate
        jkm_percent (float): Death insurance employer contribution rate
    """
    
    def onload(self) -> None:
        """Load additional data when document is loaded."""
        self._sync_from_defaults()
    
    def validate(self) -> None:
        """
        Validate BPJS settings using rules from defaults.json.
        
        Raises:
            frappe.ValidationError: If any percentage or salary threshold is invalid
        """
        try:
            self._validate_percentages()
            self._validate_salary_thresholds()
            debug_log("BPJS Settings validated successfully", "BPJS Settings")
        except Exception as e:
            debug_log(f"Error validating BPJS Settings: {str(e)}", "BPJS Settings", trace=True)
            frappe.log_error(f"Error validating BPJS Settings: {str(e)}")
            raise
    
    def on_update(self) -> None:
        """
        Set up accounts and update related settings after saving.
        
        Creates/updates BPJS accounts for all companies based on defaults.json.
        """
        try:
            # Ensure accounts are created for all companies
            self._setup_accounts_for_all_companies()
            
            # Update dependent documents
            self._update_salary_components()
            
            debug_log("BPJS Settings updated successfully", "BPJS Settings")
        except Exception as e:
            debug_log(f"Error in BPJS Settings on_update: {str(e)}", "BPJS Settings", trace=True)
            frappe.log_error(f"Error in BPJS Settings on_update: {str(e)}")
    
    def _validate_percentages(self) -> None:
        """
        Validate all percentage fields against configuration rules.
        
        Raises:
            frappe.ValidationError: If any percentage is outside allowed range
        """
        # Get validation rules from config
        config = get_default_config()
        percentage_ranges = config.get("bpjs_settings", {}).get(
            "validation_rules", {}).get("percentage_ranges", [])
        
        if not percentage_ranges:
            debug_log("No percentage validation rules found in config", "BPJS Settings")
            return
        
        # Check each rule
        for rule in percentage_ranges:
            field = rule.get("field")
            min_val = rule.get("min", 0)
            max_val = rule.get("max", 100)
            error_msg = rule.get("error_msg", f"{field} must be between {min_val} and {max_val}%")
            
            if hasattr(self, field):
                value = float(self.get(field) or 0)
                if value < min_val or value > max_val:
                    frappe.throw(_(error_msg))
    
    def _validate_salary_thresholds(self) -> None:
        """
        Validate salary threshold fields against configuration rules.
        
        Raises:
            frappe.ValidationError: If any threshold is below minimum
        """
        # Get validation rules from config
        config = get_default_config()
        salary_thresholds = config.get("bpjs_settings", {}).get(
            "validation_rules", {}).get("salary_thresholds", [])
        
        if not salary_thresholds:
            debug_log("No salary threshold validation rules found in config", "BPJS Settings")
            return
        
        # Check each rule
        for rule in salary_thresholds:
            field = rule.get("field")
            min_val = rule.get("min", 0)
            error_msg = rule.get("error_msg", f"{field} must be greater than {min_val}")
            
            if hasattr(self, field):
                value = float(self.get(field) or 0)
                if value < min_val:
                    frappe.throw(_(error_msg))
    
    def _sync_from_defaults(self) -> None:
        """Load default values from defaults.json if document is new."""
        if not self.is_new():
            return
            
        config = get_default_config()
        bpjs_config = config.get("bpjs", {})
        
        if not bpjs_config:
            debug_log("No BPJS configuration found in defaults.json", "BPJS Settings")
            return
        
        # Set default values from config
        for field in [
            "kesehatan_employee_percent",
            "kesehatan_employer_percent",
            "kesehatan_max_salary",
            "jht_employee_percent", 
            "jht_employer_percent",
            "jp_employee_percent",
            "jp_employer_percent",
            "jp_max_salary",
            "jkk_percent",
            "jkm_percent"
        ]:
            if field in bpjs_config and hasattr(self, field):
                self.set(field, bpjs_config.get(field))
        
        debug_log("Default BPJS values loaded from configuration", "BPJS Settings")
    
    def _setup_accounts_for_all_companies(self) -> None:
        """Set up BPJS accounts for all active companies."""
        # Get all active companies
        companies = frappe.get_all("Company", pluck="name")
        
        if not companies:
            debug_log("No companies found for BPJS account setup", "BPJS Settings")
            return
        
        debug_log(f"Setting up BPJS accounts for {len(companies)} companies", "BPJS Settings")
        
        # Track results
        results = {"success": [], "failed": []}
        
        # Set up accounts for each company
        for company in companies:
            try:
                liability_parent, expense_parent = self._ensure_parent_accounts(company)
                
                if liability_parent and expense_parent:
                    # Create payable accounts
                    self._create_bpjs_payable_accounts(company, liability_parent)
                    
                    # Create expense accounts
                    self._create_bpjs_expense_accounts(company, expense_parent)
                    
                    results["success"].append(company)
                else:
                    results["failed"].append(company)
            except Exception as e:
                debug_log(
                    f"Error setting up BPJS accounts for {company}: {str(e)}",
                    "BPJS Settings",
                    trace=True
                )
                results["failed"].append(company)
        
        # Log summary
        if results["success"]:
            debug_log(
                f"Successfully set up BPJS accounts for: {', '.join(results['success'])}",
                "BPJS Settings"
            )
        
        if results["failed"]:
            debug_log(
                f"Failed to set up BPJS accounts for: {', '.join(results['failed'])}",
                "BPJS Settings"
            )
    
    def _ensure_parent_accounts(self, company: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Create or get parent accounts for BPJS.
        
        Args:
            company: Company name
            
        Returns:
            tuple: (liability_parent_account, expense_parent_account)
        """
        # Create liability parent
        liability_parent = get_or_create_account(
            company=company,
            account_name="BPJS Liabilities",
            account_type="Tax",
            is_group=1,
            root_type="Liability"
        )
        
        if not liability_parent:
            debug_log(f"Failed to create BPJS liability parent for {company}", "BPJS Settings")
        
        # Create expense parent
        expense_parent = get_or_create_account(
            company=company,
            account_name="BPJS Expenses",
            account_type="Expense Account",
            is_group=1,
            root_type="Expense"
        )
        
        if not expense_parent:
            debug_log(f"Failed to create BPJS expense parent for {company}", "BPJS Settings")
        
        return liability_parent, expense_parent
    
    def _create_bpjs_payable_accounts(self, company: str, parent: str) -> List[str]:
        """
        Create BPJS payable accounts from configuration.
        
        Args:
            company: Company name
            parent: Parent account name
            
        Returns:
            list: Created account names
        """
        config = get_default_config()
        payable_accounts = config.get("gl_accounts", {}).get("bpjs_payable_accounts", {})
        
        if not payable_accounts:
            debug_log("No BPJS payable accounts defined in configuration", "BPJS Settings")
            return []
        
        created_accounts = []
        
        for key, account_data in payable_accounts.items():
            try:
                account_name = account_data.get("account_name")
                account_type = account_data.get("account_type", "Payable")
                root_type = account_data.get("root_type", "Liability")
                
                if not account_name:
                    continue
                
                account = get_or_create_account(
                    company=company,
                    account_name=account_name,
                    account_type=account_type,
                    is_group=0,
                    root_type=root_type
                )
                
                if account:
                    created_accounts.append(account)
                    debug_log(f"Created BPJS payable account: {account}", "BPJS Settings")
            except Exception as e:
                debug_log(
                    f"Error creating BPJS payable account {account_data.get('account_name')}: {str(e)}",
                    "BPJS Settings",
                    trace=True
                )
        
        return created_accounts
    
    def _create_bpjs_expense_accounts(self, company: str, parent: str) -> List[str]:
        """
        Create BPJS expense accounts from configuration.
        
        Args:
            company: Company name
            parent: Parent account name
            
        Returns:
            list: Created account names
        """
        config = get_default_config()
        expense_accounts = config.get("gl_accounts", {}).get("bpjs_expense_accounts", {})
        
        if not expense_accounts:
            debug_log("No BPJS expense accounts defined in configuration", "BPJS Settings")
            return []
        
        created_accounts = []
        
        for key, account_data in expense_accounts.items():
            try:
                account_name = account_data.get("account_name")
                account_type = account_data.get("account_type", "Expense Account")
                root_type = account_data.get("root_type", "Expense")
                
                if not account_name:
                    continue
                
                account = get_or_create_account(
                    company=company,
                    account_name=account_name,
                    account_type=account_type,
                    is_group=0,
                    root_type=root_type
                )
                
                if account:
                    created_accounts.append(account)
                    debug_log(f"Created BPJS expense account: {account}", "BPJS Settings")
            except Exception as e:
                debug_log(
                    f"Error creating BPJS expense account {account_data.get('account_name')}: {str(e)}",
                    "BPJS Settings",
                    trace=True
                )
        
        return created_accounts
    
    def _update_salary_components(self) -> None:
        """Update BPJS components in active salary structures."""
        # Get component map from configuration
        config = get_default_config()
        component_map = config.get("bpjs_settings", {}).get("bpjs_components", {})
        
        if not component_map:
            debug_log("No BPJS component mapping found in configuration", "BPJS Settings")
            return
        
        # Get active salary structures
        salary_structures = frappe.get_all(
            "Salary Structure",
            filters={"is_active": "Yes", "docstatus": 1},
            fields=["name"]
        )
        
        if not salary_structures:
            debug_log("No active salary structures found", "BPJS Settings")
            return
        
        updated_count = 0
        
        # For each structure, find and update BPJS components
        for structure in salary_structures:
            try:
                ss = frappe.get_doc("Salary Structure", structure.name)
                
                # Check earnings and deductions for BPJS components
                for component_list in ["earnings", "deductions"]:
                    if not hasattr(ss, component_list):
                        continue
                    
                    for component in getattr(ss, component_list):
                        if component.salary_component in component_map:
                            # Get corresponding field from component map
                            field_name = component_map[component.salary_component]
                            
                            # Update formula or amount if component found
                            if hasattr(self, field_name):
                                # Only update if not using formula
                                if not component.amount_based_on_formula:
                                    component.amount = self.get(field_name)
                                    updated_count += 1
                
                # Save if changes were made
                if updated_count > 0:
                    ss.flags.ignore_validate = True
                    ss.save(ignore_permissions=True)
            except Exception as e:
                debug_log(
                    f"Error updating salary structure {structure.name}: {str(e)}",
                    "BPJS Settings",
                    trace=True
                )
        
        if updated_count > 0:
            debug_log(
                f"Updated {updated_count} BPJS components in salary structures",
                "BPJS Settings"
            )


def setup_bpjs_settings() -> bool:
    """
    Create default BPJS Settings if they don't exist.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if frappe.db.exists("BPJS Settings", "BPJS Settings"):
            debug_log("BPJS Settings already exist", "BPJS Settings")
            return True
        
        # Get default values from config
        config = get_default_config()
        bpjs_config = config.get("bpjs", {})
        
        if not bpjs_config:
            debug_log("No BPJS configuration found in defaults.json", "BPJS Settings")
            return False
        
        # Create new settings
        bpjs_settings = frappe.new_doc("BPJS Settings")
        
        # Set basic fields
        for field in [
            "kesehatan_employee_percent",
            "kesehatan_employer_percent",
            "kesehatan_max_salary",
            "jht_employee_percent", 
            "jht_employer_percent",
            "jp_employee_percent",
            "jp_employer_percent",
            "jp_max_salary",
            "jkk_percent",
            "jkm_percent"
        ]:
            if field in bpjs_config:
                bpjs_settings.set(field, bpjs_config.get(field))
        
        # Save settings
        bpjs_settings.flags.ignore_validate = True
        bpjs_settings.insert(ignore_permissions=True)
        
        # Create accounts for all companies
        bpjs_settings._setup_accounts_for_all_companies()
        
        debug_log("BPJS Settings created successfully", "BPJS Settings")
        return True
    except Exception as e:
        debug_log(f"Error setting up BPJS Settings: {str(e)}", "BPJS Settings", trace=True)
        frappe.log_error(f"Error setting up BPJS Settings: {str(e)}")
        return False


def update_bpjs_settings() -> bool:
    """
    Update BPJS Settings from defaults.json.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not frappe.db.exists("BPJS Settings", "BPJS Settings"):
            return setup_bpjs_settings()
        
        # Get BPJS Settings
        bpjs_settings = frappe.get_doc("BPJS Settings", "BPJS Settings")
        
        # Get default values from config
        config = get_default_config()
        bpjs_config = config.get("bpjs", {})
        
        if not bpjs_config:
            debug_log("No BPJS configuration found in defaults.json", "BPJS Settings")
            return False
        
        # Track if any changes were made
        changes_made = False
        
        # Update fields
        for field in [
            "kesehatan_employee_percent",
            "kesehatan_employer_percent",
            "kesehatan_max_salary",
            "jht_employee_percent", 
            "jht_employer_percent",
            "jp_employee_percent",
            "jp_employer_percent",
            "jp_max_salary",
            "jkk_percent",
            "jkm_percent"
        ]:
            if field in bpjs_config and hasattr(bpjs_settings, field):
                current_value = float(bpjs_settings.get(field) or 0)
                new_value = float(bpjs_config.get(field) or 0)
                
                # Only update if values differ
                if abs(current_value - new_value) > 0.001:  # Compare with small epsilon
                    bpjs_settings.set(field, new_value)
                    changes_made = True
        
        # Save if changes were made
        if changes_made:
            bpjs_settings.flags.ignore_validate = True
            bpjs_settings.save(ignore_permissions=True)
            debug_log("BPJS Settings updated from defaults.json", "BPJS Settings")
        else:
            debug_log("BPJS Settings already match defaults.json", "BPJS Settings")
        
        return True
    except Exception as e:
        debug_log(f"Error updating BPJS Settings: {str(e)}", "BPJS Settings", trace=True)
        frappe.log_error(f"Error updating BPJS Settings: {str(e)}")
        return False
