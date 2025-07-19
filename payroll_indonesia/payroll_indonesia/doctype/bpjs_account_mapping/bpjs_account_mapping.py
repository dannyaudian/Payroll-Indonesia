# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from payroll_indonesia.frappe_helpers import logger

__all__ = [
    "BPJSAccountMapping",
    "get_mapping_for_company",
    "create_default_mapping",
    "get_bpjs_accounts",
    "sync_to_settings",
]

# Account field names as defined in bpjs_account_mapping.json
ACCOUNT_FIELDS = [
    "kesehatan_employee_account",
    "jht_employee_account",
    "jp_employee_account",
    "kesehatan_employer_debit_account",
    "kesehatan_employer_credit_account",
    "jht_employer_debit_account",
    "jht_employer_credit_account",
    "jp_employer_debit_account",
    "jp_employer_credit_account",
    "jkk_employer_debit_account",
    "jkk_employer_credit_account",
    "jkm_employer_debit_account",
    "jkm_employer_credit_account",
]

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def sync_to_settings(doc, method=None):
    """
    Sync BPJS Account Mapping to Payroll Indonesia Settings.

    Args:
        doc: The BPJS Account Mapping document
        method: The method that triggered this hook (optional)
    """
    try:
        # This is a placeholder for sync_to_settings functionality
        # Actual implementation would synchronize BPJS mapping data to settings
        logger.debug(f"BPJS Account Mapping {doc.name} updated - settings sync placeholder")
        pass
    except Exception as e:
        logger.error(f"Error syncing BPJS mapping to settings: {str(e)}")


@frappe.whitelist()
def get_mapping_for_company(company=None):
    """
    Get BPJS Account mapping for specified company

    Args:
        company (str, optional): Company name to get mapping for, uses default if not specified

    Returns:
        dict: Dictionary containing account mapping details

    Raises:
        frappe.DoesNotExistError: When no mapping exists for the company
    """
    if not company:
        company = frappe.defaults.get_user_default("Company")
        if not company:
            # Try to get first company
            companies = frappe.get_all("Company")
            if companies:
                company = companies[0].name

    if not company:
        frappe.throw(
            _("No company specified and no default company found"), frappe.DoesNotExistError
        )

    # Try to get from cache first
    cache_key = f"bpjs_mapping_{company}"
    mapping_dict = frappe.cache().get_value(cache_key)

    if mapping_dict:
        return mapping_dict

    try:
        # Find mapping for this company
        mapping_name = frappe.db.get_value("BPJS Account Mapping", {"company": company}, "name")

        # Raise exception if no mapping exists
        if not mapping_name:
            frappe.throw(
                _("No BPJS Account Mapping found for company {0}").format(company),
                frappe.DoesNotExistError,
            )

        # Get complete document data
        mapping = frappe.get_cached_doc("BPJS Account Mapping", mapping_name)

        # Convert to dictionary for Jinja template use
        mapping_dict = {
            "name": mapping.name,
            "company": mapping.company,
        }
        for field in ACCOUNT_FIELDS:
            mapping_dict[field] = mapping.get(field)

        # Cache the result with appropriate TTL
        frappe.cache().set_value(cache_key, mapping_dict, expires_in_sec=3600)

        return mapping_dict
    except frappe.DoesNotExistError:
        # Re-raise DoesNotExistError
        raise
    except Exception as e:
        frappe.log_error(
            f"Error getting BPJS account mapping for company {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Mapping Error",
        )
        frappe.throw(_("Error retrieving BPJS Account Mapping"), frappe.DoesNotExistError)


@frappe.whitelist()
def create_default_mapping(company):
    """
    Create a default BPJS Account Mapping with blank accounts

    Args:
        company (str): Company name

    Returns:
        str: Name of created mapping or None if failed
    """
    try:
        # Verify company is valid
        if not frappe.db.exists("Company", company):
            frappe.throw(_("Company {0} does not exist").format(company))

        # Check if mapping already exists
        existing_mapping = frappe.db.exists("BPJS Account Mapping", {"company": company})
        if existing_mapping:
            return existing_mapping

        # Create new mapping
        mapping = frappe.new_doc("BPJS Account Mapping")
        mapping.company = company
        mapping.mapping_name = f"BPJS Mapping - {company}"

        # Set blank accounts for all fields
        for field in ACCOUNT_FIELDS:
            setattr(mapping, field, "")

        # Insert with ignore_permissions
        mapping.insert(ignore_permissions=True)
        frappe.db.commit()

        # Clear cache for the company
        frappe.cache().delete_value(f"bpjs_mapping_{company}")

        return mapping.name

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            f"Error creating default BPJS account mapping for {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Mapping Error",
        )
        # Re-raise with a clear message
        frappe.throw(
            _("Could not create BPJS Account Mapping for {0}: {1}").format(company, str(e)[:100])
        )
        return None


@frappe.whitelist()
def get_bpjs_accounts(company):
    """
    Returns dict of BPJS account field names mapped to account values.

    Args:
        company (str): Company to get BPJS accounts for

    Returns:
        dict: Dictionary with BPJS accounts

    Raises:
        frappe.ValidationError: If mapping not found or incomplete
    """
    if not company:
        frappe.throw(_("Company is required to get BPJS accounts"), frappe.ValidationError)

    # Find mapping for this company
    mapping_name = frappe.db.get_value("BPJS Account Mapping", {"company": company}, "name")

    if not mapping_name:
        frappe.throw(
            _("No BPJS Account Mapping found for company {0}").format(company),
            frappe.ValidationError,
        )

    # Get mapping document
    mapping = frappe.get_doc("BPJS Account Mapping", mapping_name)

    # Check if all required accounts are set
    for field in ACCOUNT_FIELDS:
        if not mapping.get(field):
            frappe.throw(
                _("{0} not set in BPJS Account Mapping").format(frappe.unscrub(field)),
                frappe.ValidationError,
            )

    # Return accounts
    return {field: mapping.get(field) for field in ACCOUNT_FIELDS}


# ---------------------------------------------------------------------------
# Document class
# ---------------------------------------------------------------------------


class BPJSAccountMapping(Document):
    def validate(self):
        """Validate required fields and account types"""
        self.validate_duplicate_mapping()
        self.validate_accounts_belong_to_company()
        self.validate_amount_fields()

    def validate_duplicate_mapping(self):
        """Ensure no duplicate mapping exists for the same company"""
        if not self.is_new():
            # Skip validation when updating the same document
            return

        existing = frappe.db.get_value(
            "BPJS Account Mapping",
            {"company": self.company, "name": ["!=", self.name]},
            "name",
        )

        if existing:
            frappe.throw(
                _("BPJS Account Mapping '{0}' already exists for company {1}").format(
                    existing, self.company
                )
            )

    def validate_accounts_belong_to_company(self):
        """Validate that all accounts belong to the specified company"""
        account_fields = ACCOUNT_FIELDS

        for field in account_fields:
            account = self.get(field)
            if account:
                company = frappe.db.get_value("Account", account, "company")
                if company != self.company:
                    frappe.throw(
                        _("Account {0} does not belong to company {1}").format(
                            account, self.company
                        )
                    )

    def validate_amount_fields(self):
        """Validate that all amount fields are positive"""
        amount_fields = [
            "bpjs_kesehatan_employee_rate",
            "bpjs_kesehatan_employer_rate",
            "bpjs_jht_employee_rate",
            "bpjs_jht_employer_rate",
            "bpjs_jp_employee_rate",
            "bpjs_jp_employer_rate",
            "bpjs_jkk_rate",
            "bpjs_jkm_rate",
        ]

        for field in amount_fields:
            if hasattr(self, field) and self.get(field) is not None:
                if self.get(field) < 0:
                    frappe.throw(_("{0} must be a positive value").format(frappe.unscrub(field)))

    def on_update(self):
        """Clear cache after update"""
        original_creation = frappe.db.get_value(self.doctype, self.name, "creation")
        frappe.cache().delete_value(f"bpjs_mapping_{self.company}")
        if original_creation and self.creation != original_creation:
            logger.warning(
                f"Creation timestamp mismatch for {self.name}. Resetting to original value"
            )
            self.creation = original_creation
        # keep settings in sync after update
        sync_to_settings(self)
