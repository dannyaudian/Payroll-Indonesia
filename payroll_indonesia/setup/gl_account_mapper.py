import json
import os
from typing import Dict

import frappe


def load_json(filename: str) -> Dict[str, str]:
    """
    Load a JSON file from the app's setup directory.
    
    Args:
        filename: Name of the JSON file to load
        
    Returns:
        Dictionary from the JSON file or empty dict if file not found
    """
    file_path = frappe.get_app_path("payroll_indonesia", "setup", filename)
    
    if not os.path.exists(file_path):
        frappe.logger().warning(f"File not found: {file_path}")
        return {}
    
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception as e:
        frappe.logger().warning(f"Error loading {filename}: {str(e)}")
        return {}


def assign_gl_accounts_to_salary_components(company: str, company_abbr: str) -> None:
    """
    Assign GL accounts to salary components based on mapping defined in gl_account_mapping.json
    using the Salary Component Account child table.
    
    Args:
        company: Name of the company
        company_abbr: Company abbreviation used in account names
    """
    # Load mapping from JSON file
    mapping = load_json("gl_account_mapping.json")
    if not mapping:
        frappe.logger().warning("GL account mapping not found or empty. Skipping assignment.")
        return
    
    frappe.logger().info(f"Processing GL account mapping for company: {company}")
    
    # Process each mapping entry
    for component_name, account_name in mapping.items():
        # Build full account name with company abbreviation
        full_acc = f"{account_name} - {company_abbr}"
        
        # Check if account exists
        if not frappe.db.exists("Account", full_acc):
            frappe.logger().warning(f"Account {full_acc} not found for company {company}. Skipping.")
            continue
        
        # Find salary components to update
        salary_components = frappe.get_all(
            "Salary Component",
            filters={"salary_component": component_name},
            pluck="name"
        )
        
        if not salary_components:
            frappe.logger().info(f"No salary component found with name '{component_name}'. Skipping.")
            continue
        
        # Update each salary component
        for sc_name in salary_components:
            sc_doc = frappe.get_doc("Salary Component", sc_name)
            
            # Check if mapping for this company already exists
            existing_mapping = None
            for acc in sc_doc.get("accounts", []):
                if acc.company == company:
                    existing_mapping = acc
                    break
            
            if existing_mapping:
                # Update if account is different
                if existing_mapping.account != full_acc:
                    frappe.logger().info(
                        f"Updating account for '{component_name}' in company '{company}' "
                        f"from '{existing_mapping.account}' to '{full_acc}'"
                    )
                    existing_mapping.account = full_acc
                    sc_doc.save()
                else:
                    frappe.logger().info(
                        f"Salary component '{component_name}' already mapped to '{full_acc}' "
                        f"for company '{company}'. Skipping."
                    )
            else:
                # Create new mapping
                try:
                    sc_doc.append("accounts", {
                        "company": company,
                        "account": full_acc,
                    })
                    sc_doc.save()
                    frappe.logger().info(
                        f"Mapped salary component '{component_name}' to GL account '{full_acc}' "
                        f"for company '{company}'"
                    )
                except Exception as e:
                    frappe.logger().warning(
                        f"Error mapping '{component_name}' to '{full_acc}' for company '{company}': {str(e)}"
                    )


def create_default_mapping_for_component(component_name: str) -> None:
    """
    Create default account mapping (without company) for a salary component.
    
    Args:
        component_name: Name of the salary component
    """
    mapping = load_json("gl_account_mapping.json")
    if not mapping or component_name not in mapping:
        return
    
    account_name = mapping[component_name]
    sc_doc = frappe.get_doc("Salary Component", {"salary_component": component_name})
    
    # Check if default mapping already exists
    has_default = False
    for acc in sc_doc.get("accounts", []):
        if not acc.company:
            has_default = True
            break
    
    if not has_default:
        sc_doc.append("accounts", {
            "company": "",
            "account": account_name,
            "default_account": 1
        })
        sc_doc.save()
        frappe.logger().info(f"Created default mapping for '{component_name}' to '{account_name}'")


@frappe.whitelist()
def assign_gl_accounts_to_salary_components_all() -> None:
    """
    Assign GL accounts to salary components for all companies.
    This function can be called from the command line.
    """
    companies = frappe.get_all("Company", fields=["name", "abbr"])
    mapping = load_json("gl_account_mapping.json")
    
    # First create default mappings for all components
    for component_name in mapping:
        try:
            if frappe.db.exists("Salary Component", {"salary_component": component_name}):
                create_default_mapping_for_component(component_name)
        except Exception as e:
            frappe.logger().warning(f"Error creating default mapping for {component_name}: {str(e)}")
    
    # Then create company-specific mappings
    for company in companies:
        try:
            assign_gl_accounts_to_salary_components(company.name, company.abbr)
            frappe.db.commit()
            frappe.logger().info(f"Completed GL account mapping for company: {company.name}")
        except Exception as e:
            frappe.logger().warning(f"Error processing company {company.name}: {str(e)}")
            frappe.db.rollback()
    
    frappe.logger().info("Completed GL account mapping for all companies")
