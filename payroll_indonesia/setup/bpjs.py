# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
BPJS setup utilities for Payroll Indonesia.
Provides functions to set up BPJS account mappings.
"""

import frappe
from frappe.utils import cint
from payroll_indonesia.frappe_helpers import logger

def ensure_bpjs_account_mappings(doc=None, method=None, transaction_open=False) -> bool:
    """
    Ensure each company has a BPJS Account Mapping.
    
    This can be called:
    - As a hook from Company DocType
    - Directly from other setup functions
    - Via command line
    
    Args:
        doc: Optional Company document (when called from hooks)
        method: Unused hook parameter
        transaction_open: Whether a DB transaction is already open
        
    Returns:
        bool: True if any mappings were created, False otherwise
    """
    try:
        from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import (
            create_default_mapping,
        )

        company_name = getattr(doc, "name", None) if doc else None
        
        if company_name:
            # Called from Company hook, only process this company
            companies = [company_name]
        else:
            # Process all companies
            companies = frappe.get_all("Company", pluck="name")
        
        if not companies:
            logger.warning("No companies found for BPJS account mapping")
            return False
            
        created = False
        for company in companies:
            logger.debug(f"Checking BPJS account mapping for company: {company}")
            
            if not frappe.db.exists("BPJS Account Mapping", {"company": company}):
                try:
                    create_default_mapping(company)
                    logger.info(f"Created BPJS account mapping for company: {company}")
                    created = True
                except Exception as e:
                    logger.error(f"Failed to create BPJS account mapping for {company}: {e}")
            else:
                logger.debug(f"BPJS account mapping already exists for company: {company}")

        if created:
            logger.info(f"Created BPJS account mappings for {len(companies)} companies")
        else:
            logger.info("No new BPJS account mappings needed")
            
        return created
        
    except Exception as e:
        logger.error(f"Error ensuring BPJS Account Mappings: {str(e)}")
        return False


def verify_bpjs_accounts(company=None) -> dict:
    """
    Verify that all required BPJS accounts exist for the given company.
    
    Args:
        company: Company name to verify accounts for (optional, all companies if None)
        
    Returns:
        dict: Results of verification with missing accounts
    """
    try:
        from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import (
            get_mapping_for_company
        )
        
        results = {}
        
        # Get companies to check
        if company:
            companies = [company]
        else:
            companies = frappe.get_all("Company", pluck="name")
            
        for company_name in companies:
            # Check BPJS mapping existence
            mapping_exists = frappe.db.exists("BPJS Account Mapping", {"company": company_name})
            
            # Get mapping details if it exists
            if mapping_exists:
                mapping = get_mapping_for_company(company_name)
                
                # Check required accounts
                missing_accounts = []
                
                account_fields = [
                    "kesehatan_account", 
                    "kesehatan_expense_account",
                    "jht_account", 
                    "jht_expense_account",
                    "jp_account", 
                    "jp_expense_account",
                    "jkk_account", 
                    "jkk_expense_account",
                    "jkm_account", 
                    "jkm_expense_account"
                ]
                
                for field in account_fields:
                    account = mapping.get(field)
                    if not account or not frappe.db.exists("Account", account):
                        missing_accounts.append(field)
                
                results[company_name] = {
                    "mapping_exists": True,
                    "complete": len(missing_accounts) == 0,
                    "missing_accounts": missing_accounts
                }
            else:
                results[company_name] = {
                    "mapping_exists": False,
                    "complete": False,
                    "missing_accounts": ["No BPJS account mapping found"]
                }
                
        return results
    except Exception as e:
        logger.error(f"Error verifying BPJS accounts: {str(e)}")
        return {"error": str(e)}


def setup_bpjs_mapping_cli():
    """
    Command-line interface for setting up BPJS account mappings.
    Can be run with: bench --site <site> execute payroll_indonesia.setup.bpjs.setup_bpjs_mapping_cli
    """
    try:
        print("Setting up BPJS account mappings for all companies...")
        
        result = ensure_bpjs_account_mappings()
        
        if result:
            print("BPJS account mappings created successfully")
        else:
            print("No new BPJS account mappings needed")
            
        # Verify the mappings
        verification = verify_bpjs_accounts()
        
        print("\nVerification Results:")
        for company, status in verification.items():
            print(f"\nCompany: {company}")
            print(f"  Mapping exists: {status['mapping_exists']}")
            print(f"  Complete: {status['complete']}")
            
            if not status['complete']:
                print(f"  Missing accounts: {', '.join(status['missing_accounts'])}")
                
    except Exception as e:
        print(f"Error setting up BPJS account mappings: {e}")