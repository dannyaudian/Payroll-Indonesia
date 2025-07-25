import json
import os
from typing import List, Optional

import frappe
from payroll_indonesia.setup.gl_account_mapper import assign_gl_accounts_to_salary_components
from payroll_indonesia.setup.settings_migration import setup_default_settings

def get_parent_account(possible_names: List[str], company_abbr: str) -> Optional[str]:
    """
    Find a suitable parent account by trying different possible names.
    
    Args:
        possible_names: List of possible parent account names to try
        company_abbr: Company abbreviation
        
    Returns:
        Full account name with company abbreviation if found, None otherwise
    """
    for name in possible_names:
        parent_account = f"{name} - {company_abbr}"
        if frappe.db.exists("Account", parent_account):
            return parent_account
    return None


def create_default_accounts(company_name: str, company_abbr: str) -> None:
    """
    Create default GL accounts for payroll processing for the specified company.
    
    Args:
        company_name: Name of the company
        company_abbr: Abbreviation of the company
    """
    # Load GL accounts from JSON file
    json_file_path = frappe.get_app_path("payroll_indonesia", "setup", "default_gl_accounts.json")
    
    if not os.path.exists(json_file_path):
        frappe.log_error(f"File not found: {json_file_path}", "Payroll Indonesia Setup")
        return
    
    with open(json_file_path, "r") as f:
        gl_accounts = json.load(f)
    
    # Parent account fallback options for different categories
    parent_account_options = {
        "expense": ["Direct Expenses", "Pengeluaran Langsung", "Expenses", "Biaya"],
        "liability": ["Payables", "Utang Usaha", "Current Liabilities", "Kewajiban Lancar"],
        "tax": ["Duties and Taxes", "Utang Pajak"]
    }
    
    for account in gl_accounts:
        account_name = account.get("account_name")
        root_type = account.get("root_type")
        account_type = account.get("account_type")
        is_group = account.get("is_group", 0)
        category = account.get("category")
        
        # Account name with company abbreviation
        account_name_with_abbr = f"{account_name} - {company_abbr}"
        
        # Skip if account already exists
        if frappe.db.exists("Account", account_name_with_abbr):
            continue
        
        # Find parent account
        parent_account = None
        
        # Special handling for PPh 21 Payable - it should go under Duties and Taxes
        if account_name == "PPh 21 Payable":
            parent_account = get_parent_account(parent_account_options["tax"], company_abbr)
        elif root_type == "Expense":
            # For expense accounts
            expense_parents = frappe.get_all(
                "Account",
                filters={
                    "company": company_name,
                    "root_type": "Expense",
                    "is_group": 1,
                    "account_type": "Expense Account"
                },
                fields=["name"]
            )
            
            if expense_parents:
                parent_account = expense_parents[0].name
            else:
                # Fall back to predefined parent account names
                parent_account = get_parent_account(parent_account_options["expense"], company_abbr)
        elif root_type == "Liability" and account_type == "Payable":
            # For liability accounts (except PPh 21)
            liability_parents = frappe.get_all(
                "Account",
                filters={
                    "company": company_name,
                    "root_type": "Liability",
                    "is_group": 1,
                    "account_type": "Payable"
                },
                fields=["name"]
            )
            
            if liability_parents:
                parent_account = liability_parents[0].name
            else:
                # Fall back to predefined parent account names
                parent_account = get_parent_account(parent_account_options["liability"], company_abbr)
        
        # If no parent account found, skip this account
        if not parent_account:
            frappe.log_error(
                f"Cannot create account {account_name_with_abbr}: No suitable parent account found",
                "Payroll Indonesia Setup"
            )
            continue
        
        # Create account
        try:
            new_account = frappe.get_doc({
                "doctype": "Account",
                "account_name": account_name,
                "parent_account": parent_account,
                "company": company_name,
                "root_type": root_type,
                "account_type": account_type,
                "is_group": is_group,
                "report_type": "Balance Sheet" if root_type == "Liability" else "Profit and Loss"
            })
            
            new_account.insert(ignore_permissions=True)
            frappe.db.commit()
            frappe.msgprint(f"Created account: {account_name_with_abbr}")
        
        except Exception as e:
            frappe.log_error(
                f"Error creating account {account_name_with_abbr}: {str(e)}",
                "Payroll Indonesia Setup"
            )


def after_sync() -> None:
    """
    Setup function that runs after app sync.
    Creates default GL accounts for all companies and maps them to salary components.
    Also migrates Payroll Indonesia Settings tables from default JSON if not present.
    """
    try:
        # Get all companies
        companies = frappe.get_all("Company", fields=["name", "abbr"])
        
        # Create default accounts for each company
        for company in companies:
            create_default_accounts(company.name, company.abbr)
            
            # Map GL accounts to salary components
            try:
                assign_gl_accounts_to_salary_components(company.name, company.abbr)
                frappe.logger().info(f"Mapped salary components to GL accounts for company: {company.name}")
            except Exception as e:
                frappe.log_error(
                    f"Error mapping salary components to GL accounts for company {company.name}: {str(e)}",
                    "Payroll Indonesia Setup"
                )
        
        # Migrate Payroll Indonesia Settings tables if needed
        try:
            setup_default_settings()
            frappe.logger().info("Payroll Indonesia Settings tables migrated (PTKP/TER/Brackets)")
        except Exception as e:
            frappe.log_error(
                f"Error in Payroll Indonesia Settings migration: {str(e)}",
                "Payroll Indonesia Setup"
            )

        frappe.msgprint("Payroll Indonesia: Default GL accounts setup, mapping, and settings migration completed")
    
    except Exception as e:
        frappe.log_error(
            f"Error in Payroll Indonesia setup: {str(e)}",
            "Payroll Indonesia Setup"
        )