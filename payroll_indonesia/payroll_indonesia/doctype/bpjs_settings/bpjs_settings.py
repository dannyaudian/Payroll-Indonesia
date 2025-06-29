# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 00:10:21 by dannyaudian

"""
BPJS Settings DocType controller.

Handles validation and synchronization of BPJS (social security) settings
using centralized validation and configuration management.
"""

import logging
from typing import Dict, Any, Optional

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from payroll_indonesia.config.config import get_live_config
from payroll_indonesia.frappe_helpers import safe_execute
import payroll_indonesia.payroll_indonesia.validations as validations
from payroll_indonesia.payroll_indonesia.utils import (
    create_parent_liability_account,
    create_parent_expense_account,
    retry_bpjs_mapping,
)

# Configure logger
logger = logging.getLogger("payroll_indonesia.bpjs")


class BPJSSettings(Document):
    """
    Controller for BPJS Settings DocType.
    
    Manages Indonesian social security contribution settings, account configuration,
    and synchronization with central configuration.
    """
    
    def validate(self):
        """
        Validate BPJS settings using centralized validation logic.
        
        Delegates to the validation module for all validation rules.
        """
        # Skip validation if explicitly ignored
        if getattr(self, "flags", {}).get("ignore_validate"):
            return
            
        try:
            # Delegate validation to central validation module
            validations.validate_bpjs_settings(self)
            
            # Sync from Payroll Indonesia Settings if needed
            self._sync_from_payroll_settings()
            
            logger.info(f"BPJS Settings validated successfully by {frappe.session.user}")
        except Exception as e:
            logger.error(f"Error validating BPJS Settings: {str(e)}")
            frappe.log_error(f"Error validating BPJS Settings: {str(e)}")
    
    def before_save(self):
        """
        Optionally sync settings to defaults.json before saving.
        
        Only runs if sync_to_defaults is enabled in configuration.
        """
        config = get_live_config()
        sync_to_defaults = config.get("settings", {}).get("sync_to_defaults", False)
        
        if sync_to_defaults:
            try:
                validations.sync_bpjs_to_defaults(self)
                logger.info("BPJS Settings synced to defaults.json")
            except Exception as e:
                logger.warning(f"Could not sync BPJS settings to defaults: {str(e)}")
    
    def on_update(self):
        """
        Update related documents when settings change.
        
        Ensures BPJS mappings exist for all companies and updates salary structures.
        """
        try:
            # Update salary structure assignments if needed
            self._update_salary_structures()

            # Ensure all companies have BPJS mapping
            self._ensure_bpjs_mapping_for_all_companies()

            # Sync changes back to Payroll Indonesia Settings
            self._sync_to_payroll_settings()
            
            logger.info(f"BPJS Settings updated by {frappe.session.user}")
        except Exception as e:
            logger.error(f"Error in BPJS Settings on_update: {str(e)}")
            frappe.log_error(f"Error in BPJS Settings on_update: {str(e)}")
    
    @safe_execute(log_exception=True)
    def setup_accounts(self):
        """
        Setup GL accounts for BPJS components for all companies.
        
        Creates standardized account structure for BPJS payments and expenses.
        """
        # Get companies to process
        default_company = frappe.defaults.get_defaults().get("company")
        if not default_company:
            companies = frappe.get_all("Company", pluck="name")
            if not companies:
                logger.warning("No companies found to setup BPJS accounts")
                return
        else:
            companies = [default_company]
        
        logger.info(f"Setting up BPJS accounts for companies: {', '.join(companies)}")
        
        # Track results for summary
        results = {"success": [], "failed": [], "skipped": []}
        
        # Get configuration
        config = get_live_config()
        
        # Process each company
        for company in companies:
            try:
                # Create parent accounts
                liability_parent = create_parent_liability_account(company)
                if not liability_parent:
                    results["failed"].append(f"{company} (liability parent)")
                    continue
                    
                expense_parent = create_parent_expense_account(company)
                if not expense_parent:
                    results["failed"].append(f"{company} (expense parent)")
                    continue
                
                # Get account information from configuration
                gl_accounts = config.get("gl_accounts", {})
                
                # Create BPJS mapping
                mapping_result = self._create_bpjs_mapping(company)
                if mapping_result:
                    results["success"].append(company)
                else:
                    results["failed"].append(company)
            except Exception as e:
                logger.error(f"Error setting up BPJS accounts for {company}: {str(e)}")
                results["failed"].append(company)
        
        # Log summary
        if results["success"]:
            logger.info(f"BPJS accounts setup completed for: {', '.join(results['success'])}")
        if results["failed"]:
            logger.error(f"BPJS accounts setup failed for: {', '.join(results['failed'])}")
    
    @safe_execute(log_exception=True)
    def _sync_from_payroll_settings(self):
        """Load settings from Payroll Indonesia Settings if they exist."""
        # Get central settings
        config = get_live_config()
        bpjs_config = config.get("bpjs", {})
        
        # Fields to sync from central config
        fields = [
            "kesehatan_employee_percent",
            "kesehatan_employer_percent",
            "kesehatan_max_salary",
            "jht_employee_percent",
            "jht_employer_percent",
            "jp_employee_percent",
            "jp_employer_percent",
            "jp_max_salary",
            "jkk_percent",
            "jkm_percent",
        ]
        
        # Only sync if this is a new document
        if self.is_new():
            for field in fields:
                if hasattr(self, field) and field in bpjs_config:
                    self.set(field, bpjs_config.get(field))
            logger.info("BPJS Settings loaded from central configuration")
    
    @safe_execute(log_exception=True)
    def _sync_to_payroll_settings(self):
        """Sync changes to Payroll Indonesia Settings."""
        if not frappe.db.exists("DocType", "Payroll Indonesia Settings"):
            return
            
        # Get Payroll Indonesia Settings
        pi_settings = frappe.get_doc("Payroll Indonesia Settings", "Payroll Indonesia Settings")
        
        # Fields to sync
        fields = [
            "kesehatan_employee_percent",
            "kesehatan_employer_percent",
            "kesehatan_max_salary",
            "jht_employee_percent",
            "jht_employer_percent",
            "jp_employee_percent",
            "jp_employer_percent",
            "jp_max_salary",
            "jkk_percent",
            "jkm_percent",
        ]
        
        # Check which fields need updating
        needs_update = False
        for field in fields:
            if hasattr(pi_settings, field) and hasattr(self, field):
                if pi_settings.get(field) != self.get(field):
                    pi_settings.set(field, self.get(field))
                    needs_update = True
        
        # Save if changes were made
        if needs_update:
            pi_settings.app_last_updated = now_datetime()
            pi_settings.app_updated_by = frappe.session.user
            pi_settings.flags.ignore_validate = True
            pi_settings.save(ignore_permissions=True)
            logger.info("Payroll Indonesia Settings updated from BPJS Settings")
    
    @safe_execute(log_exception=True)
    def _create_bpjs_mapping(self, company: str) -> Optional[str]:
        """
        Create BPJS mapping for company.
        
        Args:
            company: Company name
            
        Returns:
            str: Mapping name if created, None otherwise
        """
        # Check if mapping already exists
        existing_mapping = frappe.db.exists("BPJS Account Mapping", {"company": company})
        if existing_mapping:
            logger.info(f"BPJS Account Mapping already exists for {company}: {existing_mapping}")
            return existing_mapping
        
        # Import create_default_mapping function
        try:
            module_path = "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping"
            module = frappe.get_module(module_path)
            create_default_mapping = getattr(module, "create_default_mapping", None)
            
            if not create_default_mapping:
                logger.error("create_default_mapping function not found")
                return None
            
            # Get account mapping from configuration
            config = get_live_config()
            account_mapping = config.get("gl_accounts", {}).get("bpjs_account_mapping", {})
            
            # Create mapping
            logger.info(f"Creating new BPJS Account Mapping for {company}")
            mapping_name = create_default_mapping(company, account_mapping)
            
            if mapping_name:
                logger.info(f"Created BPJS mapping: {mapping_name} for {company}")
                return mapping_name
            else:
                logger.warning(f"Failed to create BPJS mapping for {company}")
                return None
        except Exception as e:
            logger.error(f"Error creating BPJS mapping for {company}: {str(e)}")
            return None
    
    @safe_execute(log_exception=True)
    def _update_salary_structures(self):
        """
        Update BPJS components in active salary structures.
        
        Updates salary structures with current BPJS percentages.
        """
        # Find active salary structures
        salary_structures = frappe.get_all(
            "Salary Structure",
            filters={"is_active": "Yes", "docstatus": 0},  # Only draft structures
            fields=["name"],
        )
        
        if not salary_structures:
            logger.info("No active draft salary structures found to update")
            return
        
        # Get component map from configuration
        config = get_live_config()
        component_map = config.get("bpjs_settings", {}).get("bpjs_components", {})
        
        # Fallback to direct mapping if not configured
        if not component_map:
            component_map = {
                "BPJS Kesehatan Employee": "kesehatan_employee_percent",
                "BPJS Kesehatan Employer": "kesehatan_employer_percent",
                "BPJS JHT Employee": "jht_employee_percent",
                "BPJS JHT Employer": "jht_employer_percent",
                "BPJS JP Employee": "jp_employee_percent",
                "BPJS JP Employer": "jp_employer_percent",
                "BPJS JKK": "jkk_percent",
                "BPJS JKM": "jkm_percent",
            }
        
        # Build components to update
        bpjs_components = {}
        for component_name, field_name in component_map.items():
            if hasattr(self, field_name):
                bpjs_components[component_name] = self.get(field_name)
        
        # Track statistics
        updated_count = 0
        
        # Update each salary structure
        for structure in salary_structures:
            try:
                ss = frappe.get_doc("Salary Structure", structure.name)
                changes_made = False
                
                # Update components in both earnings and deductions
                for table_name in ["earnings", "deductions"]:
                    if not hasattr(ss, table_name):
                        continue
                        
                    for detail in getattr(ss, table_name):
                        if detail.salary_component in bpjs_components:
                            # Skip if uses formula
                            if detail.amount_based_on_formula and detail.formula:
                                continue
                                
                            # Update amount if needed
                            new_amount = bpjs_components[detail.salary_component]
                            if flt(detail.amount) != flt(new_amount):
                                detail.amount = new_amount
                                changes_made = True
                
                # Save if changes were made
                if changes_made:
                    ss.flags.ignore_validate = True
                    ss.save(ignore_permissions=True)
                    updated_count += 1
            except Exception as e:
                logger.error(f"Error updating salary structure {structure.name}: {str(e)}")
        
        if updated_count > 0:
            logger.info(f"Updated {updated_count} salary structures with BPJS rates")
    
    @safe_execute(log_exception=True)
    def _ensure_bpjs_mapping_for_all_companies(self):
        """Ensure all companies have BPJS mapping."""
        companies = frappe.get_all("Company", pluck="name")
        failed_companies = []
        
        for company in companies:
            # Check if mapping exists
            if not frappe.db.exists("BPJS Account Mapping", {"company": company}):
                mapping_name = self._create_bpjs_mapping(company)
                if not mapping_name:
                    failed_companies.append(company)
        
        # Schedule retry for failed companies
        if failed_companies:
            logger.info(f"Scheduling retry for BPJS mapping: {', '.join(failed_companies)}")
            frappe.enqueue(
                method="payroll_indonesia.payroll_indonesia.utils.retry_bpjs_mapping",
                companies=failed_companies,
                queue="long",
                timeout=1500,
            )
    
    @frappe.whitelist()
    def export_settings(self) -> Dict[str, Any]:
        """
        Export BPJS settings for import in other instances.
        
        Returns:
            dict: Dictionary of exportable settings
        """
        # Get fields to export from configuration
        config = get_live_config()
        export_fields = config.get("bpjs_settings", {}).get("export_fields", [
            "kesehatan_employee_percent",
            "kesehatan_employer_percent",
            "kesehatan_max_salary",
            "jht_employee_percent",
            "jht_employer_percent",
            "jp_employee_percent",
            "jp_employer_percent",
            "jp_max_salary",
            "jkk_percent",
            "jkm_percent",
        ])
        
        # Build export data
        result = {
            "export_date": now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
            "export_user": frappe.session.user,
            "settings": {},
        }
        
        for field in export_fields:
            if hasattr(self, field):
                result["settings"][field] = flt(self.get(field))
        
        return result
