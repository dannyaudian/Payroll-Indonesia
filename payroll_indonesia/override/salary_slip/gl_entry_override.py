# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-16 09:42:07 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt
import logging

# Configure logger for BPJS
logger = logging.getLogger("bpjs")


#
# Salary Slip GL Entry Override
#
def override_salary_slip_gl_entries(doc, method=None):
    """
    Override GL entries for BPJS components and PPh 21 December correction in Salary Slip

    This function modifies GL entries for:
    1. BPJS employer and employee components to use correct accounts
    2. PPh 21 December correction entries (koreksi_pph21)
    3. TER adjustment amounts if present

    Args:
        doc (obj): Salary Slip document
        method (str, optional): Method that called this function
    """
    try:
        doc_name = getattr(doc, "name", "Unknown")
        logger.info(f"on_submit_salary_slip hook triggered for {doc_name}")

        # Skip if no earnings/deductions
        if (
            not hasattr(doc, "earnings")
            or not hasattr(doc, "deductions")
            or (not doc.earnings and not doc.deductions)
        ):
            logger.info(
                f"Skipping GL entry override for {doc_name}: No earnings or deductions found"
            )
            return

        # Get company with fallback
        company = getattr(doc, "company", None)
        if not company:
            frappe.log_error(
                f"Cannot override GL entries for Salary Slip {doc_name}: Missing company",
                "GL Entry Error",
            )
            return

        # Get BPJS account mapping for this company
        bpjs_mapping = get_bpjs_account_mapping(company)
        if not bpjs_mapping:
            # Not a critical error - we'll use default accounts
            logger.info(
                f"BPJS Account Mapping not found for company {company}. Using default accounts."
            )

        # Get existing GL entries that will be created
        try:
            gl_entries = get_existing_gl_entries(doc)
            if not gl_entries:
                logger.info(f"No GL entries found for Salary Slip {doc_name}")
                return
        except Exception as e:
            # Non-critical error - log and continue with standard GL entries
            logger.error(f"Error getting GL entries for Salary Slip {doc_name}: {str(e)}")
            return

        # Store company abbreviation for consistent use
        company_abbr = frappe.get_cached_value("Company", company, "abbr")

        # Modify GL entries for BPJS components
        modified_entries = []

        for entry in gl_entries:
            # Check if this is a BPJS component
            component = entry.get("against", "")
            is_bpjs_component = "BPJS" in component

            if not is_bpjs_component:
                modified_entries.append(entry)
                continue

            # Process the component based on standardized naming conventions
            try:
                modified_entry = process_bpjs_component_entry(
                    entry, component, bpjs_mapping, company_abbr
                )

                # Add BPJS component type as a custom field
                if "Kesehatan" in component:
                    modified_entry["bpjs_component_type"] = "Kesehatan"
                elif "JHT" in component:
                    modified_entry["bpjs_component_type"] = "JHT"
                elif "JP" in component:
                    modified_entry["bpjs_component_type"] = "JP"
                elif "JKK" in component:
                    modified_entry["bpjs_component_type"] = "JKK"
                elif "JKM" in component:
                    modified_entry["bpjs_component_type"] = "JKM"
                else:
                    modified_entry["bpjs_component_type"] = "BPJS"

                modified_entries.append(modified_entry)
            except Exception as e:
                # Non-critical error - log and keep original entry
                logger.error(f"Error processing BPJS component {component} in {doc_name}: {str(e)}")
                # Keep original entry if processing fails
                modified_entries.append(entry)

        # Check for December PPh 21 correction (koreksi_pph21)
        # If present, add GL entry from Payroll Payable to Tax Payable
        koreksi_pph21 = flt(getattr(doc, "koreksi_pph21", 0))
        if koreksi_pph21 != 0:
            # Get accounts for December correction
            payroll_payable_account = get_default_payable_account(doc)
            tax_payable_account = get_tax_payable_account(doc, company_abbr)
            default_cost_center = get_default_cost_center(doc, company)

            if payroll_payable_account and tax_payable_account:
                logger.info(f"Creating GL entry for PPh 21 December correction: {koreksi_pph21}")

                # For positive correction (additional tax), debit payroll payable and credit tax payable
                # For negative correction (tax refund), debit tax payable and credit payroll payable
                if koreksi_pph21 > 0:
                    # Additional tax to be paid
                    modified_entries.append(
                        {
                            "account": payroll_payable_account,
                            "against": tax_payable_account,
                            "debit": koreksi_pph21,
                            "credit": 0,
                            "cost_center": default_cost_center,
                            "against_voucher_type": "Salary Slip",
                            "against_voucher": doc.name,
                            "remarks": f"PPh 21 December Correction - {doc.employee_name}",
                        }
                    )

                    modified_entries.append(
                        {
                            "account": tax_payable_account,
                            "against": payroll_payable_account,
                            "debit": 0,
                            "credit": koreksi_pph21,
                            "cost_center": default_cost_center,
                            "against_voucher_type": "Salary Slip",
                            "against_voucher": doc.name,
                            "remarks": f"PPh 21 December Correction - {doc.employee_name}",
                        }
                    )
                else:
                    # Tax refund
                    modified_entries.append(
                        {
                            "account": tax_payable_account,
                            "against": payroll_payable_account,
                            "debit": abs(koreksi_pph21),
                            "credit": 0,
                            "cost_center": default_cost_center,
                            "against_voucher_type": "Salary Slip",
                            "against_voucher": doc.name,
                            "remarks": f"PPh 21 December Correction (Refund) - {doc.employee_name}",
                        }
                    )

                    modified_entries.append(
                        {
                            "account": payroll_payable_account,
                            "against": tax_payable_account,
                            "debit": 0,
                            "credit": abs(koreksi_pph21),
                            "cost_center": default_cost_center,
                            "against_voucher_type": "Salary Slip",
                            "against_voucher": doc.name,
                            "remarks": f"PPh 21 December Correction (Refund) - {doc.employee_name}",
                        }
                    )

        # Check for TER adjustment amount if present
        ter_adjustment_amount = flt(getattr(doc, "ter_adjustment_amount", 0))
        if ter_adjustment_amount != 0:
            # Get accounts for TER adjustment
            payroll_payable_account = get_default_payable_account(doc)
            tax_payable_account = get_tax_payable_account(doc, company_abbr)
            default_cost_center = get_default_cost_center(doc, company)

            if payroll_payable_account and tax_payable_account:
                logger.info(f"Creating GL entry for TER adjustment: {ter_adjustment_amount}")

                # For positive adjustment (additional tax), debit payroll payable and credit tax payable
                # For negative adjustment (tax reduction), debit tax payable and credit payroll payable
                if ter_adjustment_amount > 0:
                    # Additional tax
                    modified_entries.append(
                        {
                            "account": payroll_payable_account,
                            "against": tax_payable_account,
                            "debit": ter_adjustment_amount,
                            "credit": 0,
                            "cost_center": default_cost_center,
                            "against_voucher_type": "Salary Slip",
                            "against_voucher": doc.name,
                            "remarks": f"TER Adjustment - {doc.employee_name}",
                        }
                    )

                    modified_entries.append(
                        {
                            "account": tax_payable_account,
                            "against": payroll_payable_account,
                            "debit": 0,
                            "credit": ter_adjustment_amount,
                            "cost_center": default_cost_center,
                            "against_voucher_type": "Salary Slip",
                            "against_voucher": doc.name,
                            "remarks": f"TER Adjustment - {doc.employee_name}",
                        }
                    )
                else:
                    # Tax reduction
                    modified_entries.append(
                        {
                            "account": tax_payable_account,
                            "against": payroll_payable_account,
                            "debit": abs(ter_adjustment_amount),
                            "credit": 0,
                            "cost_center": default_cost_center,
                            "against_voucher_type": "Salary Slip",
                            "against_voucher": doc.name,
                            "remarks": f"TER Adjustment (Reduction) - {doc.employee_name}",
                        }
                    )

                    modified_entries.append(
                        {
                            "account": payroll_payable_account,
                            "against": tax_payable_account,
                            "debit": 0,
                            "credit": abs(ter_adjustment_amount),
                            "cost_center": default_cost_center,
                            "against_voucher_type": "Salary Slip",
                            "against_voucher": doc.name,
                            "remarks": f"TER Adjustment (Reduction) - {doc.employee_name}",
                        }
                    )

        # Add Employer BPJS GL entries if total_bpjs_employer exists
        employer_bpjs_amount = flt(getattr(doc, "total_bpjs_employer", 0))
        if employer_bpjs_amount > 0:
            # Get accounts for employer BPJS
            expense_account = get_bpjs_employer_expense_account(doc, company_abbr)
            bpjs_payable_account = get_bpjs_payable_account(doc, company_abbr)
            default_cost_center = get_default_cost_center(doc, company)

            if expense_account and bpjs_payable_account:
                logger.info(f"Creating GL entry for Employer BPJS: {employer_bpjs_amount}")

                # Add GL entries for employer BPJS contributions
                modified_entries.append(
                    {
                        "account": expense_account,
                        "against": bpjs_payable_account,
                        "debit": employer_bpjs_amount,
                        "credit": 0,
                        "cost_center": default_cost_center,
                        "against_voucher_type": "Salary Slip",
                        "against_voucher": doc.name,
                        "remarks": f"Employer BPJS - {doc.employee_name}",
                        "bpjs_component_type": "Employer",
                    }
                )

                modified_entries.append(
                    {
                        "account": bpjs_payable_account,
                        "against": expense_account,
                        "debit": 0,
                        "credit": employer_bpjs_amount,
                        "cost_center": default_cost_center,
                        "against_voucher_type": "Salary Slip",
                        "against_voucher": doc.name,
                        "remarks": f"Employer BPJS - {doc.employee_name}",
                        "bpjs_component_type": "Employer",
                    }
                )

        # Replace GL entries with our modified entries
        doc.gl_entries = modified_entries

    except Exception as e:
        # Non-critical error - log and continue with default GL entries
        logger.error(
            f"Error in override_salary_slip_gl_entries for {getattr(doc, 'name', 'Unknown')}: {str(e)}"
        )
        frappe.log_error(
            f"Error in override_salary_slip_gl_entries: {str(e)}\n{frappe.get_traceback()}",
            "GL Entry Override Error",
        )


#
# Payment Entry GL Entry Override
#
def override_payment_entry_gl_entries(doc, method=None):
    """
    Override GL entries for BPJS Payment Entry

    This function modifies GL entries for Payment Entries that reference BPJS Payment Summary
    to use correct accounts from defaults.json configuration with standardized naming.

    Args:
        doc (obj): Payment Entry document
        method (str, optional): Method that called this function
    """
    try:
        # Check if this is a BPJS payment
        is_bpjs_payment = False

        # Check references for BPJS Payment Summary
        if hasattr(doc, "references") and doc.references:
            for ref in doc.references:
                if getattr(ref, "reference_doctype", "") == "BPJS Payment Summary":
                    is_bpjs_payment = True
                    break

        # Check party name for BPJS
        if not is_bpjs_payment and hasattr(doc, "party") and "BPJS" in doc.party:
            is_bpjs_payment = True

        # Check for BPJS in remarks
        if (
            not is_bpjs_payment
            and hasattr(doc, "remarks")
            and doc.remarks
            and "BPJS" in doc.remarks
        ):
            is_bpjs_payment = True

        if not is_bpjs_payment:
            return

        company = getattr(doc, "company", None)
        if not company:
            return

        # Get gl_entries that would be created
        if not hasattr(doc, "gl_entries") or not doc.gl_entries:
            return

        try:
            # Load BPJS account config from defaults.json
            mapping_config = frappe.get_file_json(
                frappe.get_app_path("payroll_indonesia", "config", "defaults.json")
            )
            bpjs_accounts = mapping_config.get("gl_accounts", {}).get("bpjs_payable_accounts", {})
        except Exception as e:
            # Non-critical error - log and continue with original entries
            logger.error(f"Error loading BPJS account config: {str(e)}")
            frappe.log_error(
                f"Error loading BPJS account config: {str(e)}\n{frappe.get_traceback()}",
                "BPJS Config Error",
            )
            return

        # Get company abbreviation
        company_abbr = frappe.get_cached_value("Company", company, "abbr")

        # Check if we need to modify each account
        for entry in doc.gl_entries:
            # Use the bpjs_component_type field if available
            bpjs_type = getattr(entry, "bpjs_component_type", None)

            # If no component type field, determine from account name
            if not bpjs_type and "BPJS" in entry.account:
                if "Kesehatan" in entry.account:
                    bpjs_type = "kesehatan"
                elif "JHT" in entry.account:
                    bpjs_type = "jht"
                elif "JP" in entry.account:
                    bpjs_type = "jp"
                elif "JKK" in entry.account:
                    bpjs_type = "jkk"
                elif "JKM" in entry.account:
                    bpjs_type = "jkm"

            if bpjs_type and bpjs_accounts.get(f"{bpjs_type}_payable"):
                # Get account name from defaults.json
                account_name = bpjs_accounts[f"{bpjs_type}_payable"]["account_name"]
                standardized_account = f"{account_name} - {company_abbr}"

                # If account exists, update the entry
                if frappe.db.exists("Account", standardized_account):
                    entry.account = standardized_account

                    # Set or update the component type field
                    entry.bpjs_component_type = bpjs_type

        logger.info(f"Modified GL entries for BPJS Payment Entry {doc.name}")

    except Exception as e:
        # Non-critical error - log and continue with original entries
        logger.error(
            f"Error in override_payment_entry_gl_entries for {getattr(doc, 'name', 'Unknown')}: {str(e)}"
        )
        frappe.log_error(
            f"Error in override_payment_entry_gl_entries: {str(e)}\n{frappe.get_traceback()}",
            "Payment Entry Override Error",
        )


#
# Journal Entry GL Entry Override
#
def override_journal_entry_gl_entries(doc, method=None):
    """
    Override GL entries for Journal Entry linked to BPJS Payment Summary

    This function modifies GL entries for Journal Entries that reference BPJS Payment Summary
    to use correct accounts from defaults.json configuration with standardized naming.

    Args:
        doc (obj): Journal Entry document
        method (str, optional): Method that called this function
    """
    try:
        # Check if this is a BPJS journal entry
        is_bpjs_journal = False

        # Check references in accounts for BPJS Payment Summary
        if hasattr(doc, "accounts") and doc.accounts:
            for acc in doc.accounts:
                if getattr(acc, "reference_type", "") == "BPJS Payment Summary":
                    is_bpjs_journal = True
                    break

        # Check for BPJS in user_remark
        if (
            not is_bpjs_journal
            and hasattr(doc, "user_remark")
            and doc.user_remark
            and "BPJS" in doc.user_remark
        ):
            is_bpjs_journal = True

        if not is_bpjs_journal:
            return

        company = getattr(doc, "company", None)
        if not company:
            return

        # Get accounts that would be used
        if not hasattr(doc, "accounts") or not doc.accounts:
            return

        try:
            # Load BPJS account config from defaults.json
            mapping_config = frappe.get_file_json(
                frappe.get_app_path("payroll_indonesia", "config", "defaults.json")
            )
            bpjs_expense_accounts = mapping_config.get("gl_accounts", {}).get(
                "bpjs_expense_accounts", {}
            )
            bpjs_payable_accounts = mapping_config.get("gl_accounts", {}).get(
                "bpjs_payable_accounts", {}
            )
        except Exception as e:
            # Non-critical error - log and continue with original entries
            logger.error(f"Error loading BPJS account config: {str(e)}")
            frappe.log_error(
                f"Error loading BPJS account config: {str(e)}\n{frappe.get_traceback()}",
                "BPJS Config Error",
            )
            return

        # Get company abbreviation
        company_abbr = frappe.get_cached_value("Company", company, "abbr")

        # Check if we need to modify each account
        for acc in doc.accounts:
            # Use the bpjs_component_type field if available
            bpjs_type = getattr(acc, "bpjs_component_type", None)

            # If no component type field, determine from account name
            if not bpjs_type and "BPJS" in acc.account:
                # Check if this is expense or payable
                is_expense = "Expense" in acc.account

                if "Kesehatan" in acc.account:
                    bpjs_type = "kesehatan"
                elif "JHT" in acc.account:
                    bpjs_type = "jht"
                elif "JP" in acc.account:
                    bpjs_type = "jp"
                elif "JKK" in acc.account:
                    bpjs_type = "jkk"
                elif "JKM" in acc.account:
                    bpjs_type = "jkm"

            if bpjs_type:
                is_expense = "Expense" in acc.account
                account_config = None

                if is_expense and bpjs_expense_accounts.get(f"bpjs_{bpjs_type}_employer_expense"):
                    # Get account name from defaults.json for expense
                    account_config = bpjs_expense_accounts[f"bpjs_{bpjs_type}_employer_expense"]
                elif not is_expense and bpjs_payable_accounts.get(f"{bpjs_type}_payable"):
                    # Get account name from defaults.json for payable
                    account_config = bpjs_payable_accounts[f"{bpjs_type}_payable"]

                if account_config:
                    account_name = account_config["account_name"]
                    standardized_account = f"{account_name} - {company_abbr}"

                    # If account exists, update the entry
                    if frappe.db.exists("Account", standardized_account):
                        acc.account = standardized_account

                        # Set or update the component type field
                        acc.bpjs_component_type = bpjs_type

        logger.info(f"Modified accounts for BPJS Journal Entry {doc.name}")

    except Exception as e:
        # Non-critical error - log and continue with original entries
        logger.error(
            f"Error in override_journal_entry_gl_entries for {getattr(doc, 'name', 'Unknown')}: {str(e)}"
        )
        frappe.log_error(
            f"Error in override_journal_entry_gl_entries: {str(e)}\n{frappe.get_traceback()}",
            "Journal Entry Override Error",
        )


#
# Helper Functions
#
def process_bpjs_component_entry(entry, component, bpjs_mapping, company_abbr=None):
    """
    Process a GL entry for a BPJS component to use correct accounts

    Args:
        entry (dict): Original GL entry
        component (str): BPJS component name
        bpjs_mapping (obj): BPJS Account Mapping document
        company_abbr (str, optional): Company abbreviation for fallback

    Returns:
        dict: Modified GL entry with updated account
    """
    try:
        # Make a copy to avoid modifying the original
        entry = dict(entry)

        # Handle different BPJS component types
        if "Employer" in component:
            # This is an employer contribution
            if "Kesehatan" in component:
                if entry.get("debit") and bpjs_mapping.kesehatan_employer_debit_account:
                    entry["account"] = bpjs_mapping.kesehatan_employer_debit_account
                elif entry.get("credit") and bpjs_mapping.kesehatan_employer_credit_account:
                    entry["account"] = bpjs_mapping.kesehatan_employer_credit_account
            elif "JHT" in component:
                if entry.get("debit") and bpjs_mapping.jht_employer_debit_account:
                    entry["account"] = bpjs_mapping.jht_employer_debit_account
                elif entry.get("credit") and bpjs_mapping.jht_employer_credit_account:
                    entry["account"] = bpjs_mapping.jht_employer_credit_account
            elif "JP" in component:
                if entry.get("debit") and bpjs_mapping.jp_employer_debit_account:
                    entry["account"] = bpjs_mapping.jp_employer_debit_account
                elif entry.get("credit") and bpjs_mapping.jp_employer_credit_account:
                    entry["account"] = bpjs_mapping.jp_employer_credit_account
            elif "JKK" in component:
                if entry.get("debit") and bpjs_mapping.jkk_employer_debit_account:
                    entry["account"] = bpjs_mapping.jkk_employer_debit_account
                elif entry.get("credit") and bpjs_mapping.jkk_employer_credit_account:
                    entry["account"] = bpjs_mapping.jkk_employer_credit_account
            elif "JKM" in component:
                if entry.get("debit") and bpjs_mapping.jkm_employer_debit_account:
                    entry["account"] = bpjs_mapping.jkm_employer_debit_account
                elif entry.get("credit") and bpjs_mapping.jkm_employer_credit_account:
                    entry["account"] = bpjs_mapping.jkm_employer_credit_account
        else:
            # This is an employee contribution (deduction)
            if "Kesehatan" in component and bpjs_mapping.kesehatan_employee_account:
                if entry.get("credit"):
                    entry["account"] = bpjs_mapping.kesehatan_employee_account
            elif "JHT" in component and bpjs_mapping.jht_employee_account:
                if entry.get("credit"):
                    entry["account"] = bpjs_mapping.jht_employee_account
            elif "JP" in component and bpjs_mapping.jp_employee_account:
                if entry.get("credit"):
                    entry["account"] = bpjs_mapping.jp_employee_account

        # If not found in mapping but component is BPJS, use standardized account name as fallback
        if (
            company_abbr
            and ("BPJS" in component)
            and (not entry.get("account") or entry.get("account") == "")
        ):
            fallback_account = get_fallback_bpjs_account(
                component, company_abbr, entry.get("debit", 0) > 0
            )
            if fallback_account:
                entry["account"] = fallback_account

        return entry
    except Exception as e:
        # Non-critical error - log and return original entry
        logger.error(f"Error processing BPJS component entry for {component}: {str(e)}")
        # Keep original entry
        return entry


def get_bpjs_account_mapping(company):
    """
    Get BPJS Account Mapping for this company

    Args:
        company (str): Company name

    Returns:
        obj: BPJS Account Mapping document or None if not found
    """
    try:
        # First try to use the cached mapping
        cache_key = f"bpjs_mapping_{company}"
        mapping_dict = frappe.cache().get_value(cache_key)

        if mapping_dict and isinstance(mapping_dict, dict) and mapping_dict.get("name"):
            # Convert back to document
            try:
                mapping = frappe.get_doc("BPJS Account Mapping", mapping_dict.get("name"))
                if mapping:
                    return mapping
            except Exception as e:
                # Cache might be invalid, clear it
                frappe.cache().delete_value(cache_key)
                logger.error(f"Invalid cache for BPJS mapping: {str(e)}")

        # If no cache or document not found, query directly
        mapping = frappe.get_all("BPJS Account Mapping", filters={"company": company}, limit=1)

        if mapping:
            return frappe.get_doc("BPJS Account Mapping", mapping[0].name)

        # Try to create mapping if it doesn't exist
        try:
            from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import (
                create_default_mapping,
            )

            mapping_name = create_default_mapping(company)
            if mapping_name:
                return frappe.get_doc("BPJS Account Mapping", mapping_name)
        except ImportError:
            # Non-critical error - log and continue without mapping
            logger.error(f"Could not import create_default_mapping for {company}")

    except Exception as e:
        # Non-critical error - log and continue without mapping
        logger.error(f"Error getting BPJS Account Mapping for {company}: {str(e)}")
        frappe.log_error(
            f"Error getting BPJS Account Mapping for {company}: {str(e)}\n{frappe.get_traceback()}",
            "BPJS Mapping Error",
        )

    return None


def get_existing_gl_entries(doc):
    """
    Get existing GL entries for this Salary Slip to avoid duplicates

    Args:
        doc: Salary Slip document or document name

    Returns:
        list: List of GL entries
    """
    try:
        slip_name = doc.name if hasattr(doc, "name") else doc

        gl_entries = frappe.db.get_all(
            "GL Entry",
            filters={"voucher_type": "Salary Slip", "voucher_no": slip_name, "is_cancelled": 0},
            fields=["name", "account", "against", "credit", "debit", "cost_center"],
        )

        # If no existing entries, return empty list
        if not gl_entries:
            return []

        # Process department to get cost center
        department = frappe.db.get_value("Salary Slip", slip_name, "department")

        # Add cost center if not already in GL entries
        if department:
            try:
                # First check if cost_center column exists in Department table
                if frappe.db.has_column("Department", "cost_center"):
                    cost_center = frappe.db.get_value("Department", department, "cost_center")
                    if cost_center:
                        for entry in gl_entries:
                            if not entry.get("cost_center"):
                                entry["cost_center"] = cost_center
                else:
                    logger.info("Department table does not have cost_center column")

                    # Try to get cost center from Company
                    company = frappe.db.get_value("Salary Slip", slip_name, "company")
                    if company:
                        cost_center = frappe.db.get_value("Company", company, "cost_center")
                        if cost_center:
                            for entry in gl_entries:
                                if not entry.get("cost_center"):
                                    entry["cost_center"] = cost_center
            except Exception as e:
                # Non-critical error - log and continue without cost center
                logger.error(
                    f"Error getting cost center for {slip_name}, department {department}: {str(e)}"
                )
                # Continue processing without cost center

        return gl_entries

    except Exception as e:
        # Potentially critical error - throw since we need GL entries
        logger.error(f"Error retrieving GL entries for {getattr(doc, 'name', 'Unknown')}: {str(e)}")
        frappe.log_error(
            f"Error retrieving GL entries: {str(e)}\n{frappe.get_traceback()}",
            "GL Entry Retrieval Error",
        )
        frappe.throw(_("Could not retrieve GL entries for salary slip: {0}").format(str(e)))


def get_fallback_bpjs_account(component_name, company_abbr, is_debit):
    """
    Get a fallback BPJS account when mapping doesn't provide one

    Args:
        component_name (str): BPJS component name
        company_abbr (str): Company abbreviation
        is_debit (bool): Whether this is a debit entry (for expense) or credit entry (for liability)

    Returns:
        str: Fallback account name or None
    """
    try:
        if is_debit:
            # For debit entries, use expense accounts
            if "Kesehatan" in component_name:
                return f"BPJS Kesehatan Employer Expense - {company_abbr}"
            elif "JHT" in component_name:
                return f"BPJS JHT Employer Expense - {company_abbr}"
            elif "JP" in component_name:
                return f"BPJS JP Employer Expense - {company_abbr}"
            elif "JKK" in component_name:
                return f"BPJS JKK Employer Expense - {company_abbr}"
            elif "JKM" in component_name:
                return f"BPJS JKM Employer Expense - {company_abbr}"
            else:
                return f"BPJS Expenses - {company_abbr}"
        else:
            # For credit entries, use liability accounts
            if "Kesehatan" in component_name:
                return f"BPJS Kesehatan Payable - {company_abbr}"
            elif "JHT" in component_name:
                return f"BPJS JHT Payable - {company_abbr}"
            elif "JP" in component_name:
                return f"BPJS JP Payable - {company_abbr}"
            elif "JKK" in component_name:
                return f"BPJS JKK Payable - {company_abbr}"
            elif "JKM" in component_name:
                return f"BPJS JKM Payable - {company_abbr}"
            else:
                return f"BPJS Payable - {company_abbr}"
    except Exception as e:
        # Non-critical error - log and return None
        logger.error(f"Error getting fallback BPJS account: {str(e)}")
        return None


def get_default_payable_account(doc):
    """
    Get default payable account for salary slip with multiple fallbacks

    Args:
        doc (obj): Salary Slip document

    Returns:
        str: Default payable account
    """
    try:
        company = getattr(doc, "company", None)
        if not company:
            return None

        # Try direct payroll_payable_account from doc
        payable_account = getattr(doc, "payroll_payable_account", None)

        # Try custom fields
        if not payable_account:
            if hasattr(doc, "custom_payable_account"):
                payable_account = doc.custom_payable_account
            elif hasattr(doc, "payable_account"):
                payable_account = doc.payable_account

        # Try payroll entry payable account
        if not payable_account and hasattr(doc, "payroll_entry") and doc.payroll_entry:
            payable_account = frappe.db.get_value(
                "Payroll Entry", doc.payroll_entry, "payroll_payable_account"
            )

        # Try company default payroll payable account
        if not payable_account:
            payable_account = get_default_account(company, "default_payroll_payable_account")

        # Fallback to default payable account
        if not payable_account:
            payable_account = get_default_account(company, "default_payable_account")

        # Ultimate fallback to standard naming
        if not payable_account:
            abbr = frappe.get_cached_value("Company", company, "abbr")
            payable_account = f"Salary Payable - {abbr}"

        return payable_account
    except Exception as e:
        # Non-critical error - log and return None
        logger.error(f"Error getting default payable account: {str(e)}")
        return None


def get_tax_payable_account(doc, company_abbr):
    """
    Get tax payable account for PPh 21 with multiple fallbacks

    Args:
        doc (obj): Salary Slip document
        company_abbr (str): Company abbreviation

    Returns:
        str: Tax payable account
    """
    try:
        company = getattr(doc, "company", None)
        if not company:
            return None

        # Try from configured account
        tax_payable_account = get_default_account(company, "default_income_tax_payable_account")

        # Try specific PPh 21 account if available
        if not tax_payable_account:
            tax_payable_account = frappe.db.get_value(
                "Account", {"account_name": "PPh 21 Payable", "company": company}, "name"
            )

        # Try general tax payable account
        if not tax_payable_account:
            tax_payable_account = frappe.db.get_value(
                "Account", {"account_name": "Tax Payable", "company": company}, "name"
            )

        # Fallback to standardized naming
        if not tax_payable_account:
            tax_payable_account = f"PPh 21 Payable - {company_abbr}"

            # If doesn't exist, try Tax Payable
            if not frappe.db.exists("Account", tax_payable_account):
                tax_payable_account = f"Tax Payable - {company_abbr}"

        return tax_payable_account
    except Exception as e:
        # Non-critical error - log and return None
        logger.error(f"Error getting tax payable account: {str(e)}")
        return None


def get_bpjs_employer_expense_account(doc, company_abbr):
    """
    Get BPJS employer expense account with multiple fallbacks

    Args:
        doc (obj): Salary Slip document
        company_abbr (str): Company abbreviation

    Returns:
        str: BPJS employer expense account
    """
    try:
        company = getattr(doc, "company", None)
        if not company:
            return None

        # Try configured account
        expense_account = get_default_account(company, "default_bpjs_employer_expense_account")

        # Try from database
        if not expense_account:
            expense_account = frappe.db.get_value(
                "Account", {"account_name": "BPJS Employer Expense", "company": company}, "name"
            )

        # Fallback to standardized naming
        if not expense_account:
            expense_account = f"BPJS Employer Expense - {company_abbr}"

            # If doesn't exist, try general Employee Benefits Expense
            if not frappe.db.exists("Account", expense_account):
                expense_account = f"Employee Benefits Expense - {company_abbr}"

        return expense_account
    except Exception as e:
        # Non-critical error - log and return None
        logger.error(f"Error getting BPJS employer expense account: {str(e)}")
        return None


def get_bpjs_payable_account(doc, company_abbr):
    """
    Get BPJS payable account with multiple fallbacks

    Args:
        doc (obj): Salary Slip document
        company_abbr (str): Company abbreviation

    Returns:
        str: BPJS payable account
    """
    try:
        company = getattr(doc, "company", None)
        if not company:
            return None

        # Try configured account
        payable_account = get_default_account(company, "default_bpjs_payable_account")

        # Try from database
        if not payable_account:
            payable_account = frappe.db.get_value(
                "Account", {"account_name": "BPJS Payable", "company": company}, "name"
            )

        # Fallback to standardized naming
        if not payable_account:
            payable_account = f"BPJS Payable - {company_abbr}"

            # If doesn't exist, try Statutory Payable
            if not frappe.db.exists("Account", payable_account):
                payable_account = f"Statutory Payable - {company_abbr}"

        return payable_account
    except Exception as e:
        # Non-critical error - log and return None
        logger.error(f"Error getting BPJS payable account: {str(e)}")
        return None


def get_default_cost_center(doc, company):
    """
    Get default cost center with multiple fallbacks

    Args:
        doc (obj): Salary Slip document
        company (str): Company name

    Returns:
        str: Default cost center
    """
    try:
        # Try department's cost center
        if hasattr(doc, "department") and doc.department:
            if frappe.db.has_column("Department", "cost_center"):
                cost_center = frappe.db.get_value("Department", doc.department, "cost_center")
                if cost_center:
                    return cost_center

        # Try employee's cost center
        if hasattr(doc, "employee") and doc.employee:
            if frappe.db.has_column("Employee", "cost_center"):
                cost_center = frappe.db.get_value("Employee", doc.employee, "cost_center")
                if cost_center:
                    return cost_center

        # Try payroll entry's cost center
        if hasattr(doc, "payroll_entry") and doc.payroll_entry:
            cost_center = frappe.db.get_value("Payroll Entry", doc.payroll_entry, "cost_center")
            if cost_center:
                return cost_center

        # Try company's cost center
        cost_center = frappe.get_cached_value("Company", company, "cost_center")
        if cost_center:
            return cost_center

        # Ultimate fallback
        company_abbr = frappe.get_cached_value("Company", company, "abbr")
        return f"Main - {company_abbr}"
    except Exception as e:
        # Non-critical error - log and return None
        logger.error(f"Error getting default cost center: {str(e)}")
        return None


def get_default_account(company, account_type=None):
    """
    Get default account for company based on account type

    Args:
        company (str): Company name
        account_type (str, optional): Account type field in Company document

    Returns:
        str: Default account or None
    """
    try:
        if account_type:
            return frappe.get_cached_value("Company", company, account_type)
        return None
    except Exception as e:
        # Non-critical error - log and return None
        logger.error(f"Error getting default account for {company}: {str(e)}")
        return None


@frappe.whitelist()
def diagnose_gl_entries(document_name, document_type="Salary Slip"):
    """
    Diagnostic function to analyze GL entries for a document

    Args:
        document_name (str): Name of the document
        document_type (str): Type of document (Salary Slip, Payment Entry, Journal Entry)

    Returns:
        dict: Diagnostic information about GL entries
    """
    try:
        # Validate input parameters
        if not document_name:
            frappe.throw(_("Document name is required"), title=_("Missing Parameter"))

        if not document_type:
            frappe.throw(_("Document type is required"), title=_("Missing Parameter"))

        # Verify document exists
        if not frappe.db.exists(document_type, document_name):
            frappe.throw(
                _("{0} '{1}' not found").format(document_type, document_name),
                title=_("Document Not Found"),
            )

        # Get the document
        doc = frappe.get_doc(document_type, document_name)

        result = {
            "name": doc.name,
            "doctype": doc.doctype,
            "company": getattr(doc, "company", None),
            "has_gl_entries": False,
            "gl_entries_count": 0,
            "bpjs_entries": [],
            "bpjs_components": [],
            "pph21_entries": [],
            "accounts_used": [],
        }

        # Check if document has GL entries
        if hasattr(doc, "gl_entries") and doc.gl_entries:
            result["has_gl_entries"] = True
            result["gl_entries_count"] = len(doc.gl_entries)

            # Find BPJS and PPh 21 related entries
            for entry in doc.gl_entries:
                account = getattr(entry, "account", "")
                against = getattr(entry, "against", "")
                remarks = getattr(entry, "remarks", "")
                bpjs_component_type = getattr(entry, "bpjs_component_type", None)

                # Track all unique accounts
                if account and account not in result["accounts_used"]:
                    result["accounts_used"].append(account)

                # Check for BPJS entries using component type field or account name
                is_bpjs_entry = (bpjs_component_type is not None) or (
                    "BPJS" in account or "BPJS" in against
                )

                if is_bpjs_entry:
                    result["bpjs_entries"].append(
                        {
                            "account": account,
                            "against": against,
                            "remarks": remarks,
                            "debit": getattr(entry, "debit", 0),
                            "credit": getattr(entry, "credit", 0),
                            "component_type": bpjs_component_type,
                        }
                    )

                    # Add unique components
                    if "BPJS" in against and against not in result["bpjs_components"]:
                        result["bpjs_components"].append(against)

                # Check for PPh 21 entries
                if "PPh 21" in account or "PPh 21" in against or "PPh 21" in remarks:
                    result["pph21_entries"].append(
                        {
                            "account": account,
                            "against": against,
                            "remarks": remarks,
                            "debit": getattr(entry, "debit", 0),
                            "credit": getattr(entry, "credit", 0),
                        }
                    )

        # Check for PPh 21 December correction
        if hasattr(doc, "koreksi_pph21"):
            result["has_pph21_correction"] = True
            result["koreksi_pph21"] = flt(doc.koreksi_pph21)
        else:
            result["has_pph21_correction"] = False

        # Check for TER adjustment
        if hasattr(doc, "ter_adjustment_amount"):
            result["has_ter_adjustment"] = True
            result["ter_adjustment_amount"] = flt(doc.ter_adjustment_amount)
        else:
            result["has_ter_adjustment"] = False

        # Check for employer BPJS
        if hasattr(doc, "total_bpjs_employer"):
            result["has_employer_bpjs"] = True
            result["total_bpjs_employer"] = flt(doc.total_bpjs_employer)
        else:
            result["has_employer_bpjs"] = False

        return result
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise

        # Critical diagnostic error - throw
        logger.error(f"Error diagnosing GL entries for {document_type} {document_name}: {str(e)}")
        frappe.log_error(
            f"Error diagnosing GL entries: {str(e)}\n{frappe.get_traceback()}", "GL Diagnosis Error"
        )
        frappe.throw(_("Error diagnosing GL entries: {0}").format(str(e)))
