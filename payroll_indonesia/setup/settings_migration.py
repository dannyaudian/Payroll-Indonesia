import json
import os
from typing import Any, Optional

import frappe
from frappe.model.document import Document


def load_json(filename: str) -> Any:
    """
    Load a JSON file from the setup directory.

    Args:
        filename: Name of the JSON file to load

    Returns:
        Parsed JSON content
    """
    file_path = frappe.get_app_path("payroll_indonesia", "setup", filename)

    if not os.path.exists(file_path):
        frappe.logger().warning(f"File not found: {file_path}")
        return None

    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception as e:
        frappe.logger().warning(f"Error loading {filename}: {str(e)}")
        return None


def import_ptkp_table() -> None:
    """Import default PTKP values into Payroll Indonesia Settings"""
    ptkp_data = load_json("default_ptkp_table.json")
    if not ptkp_data or not ptkp_data[0].get("ptkp_table"):
        frappe.logger().warning("PTKP data not found or invalid format")
        return

    settings = get_or_create_settings()
    if not settings:
        return

    settings.ptkp_table = []

    for entry in ptkp_data[0]["ptkp_table"]:
        settings.append(
            "ptkp_table", {"tax_status": entry["tax_status"], "ptkp_amount": entry["ptkp_amount"]}
        )

    settings.save()
    frappe.logger().info("Imported default PTKP table")


def import_ter_mapping() -> None:
    """Import default TER mapping into Payroll Indonesia Settings"""
    ter_mapping_data = load_json("default_ter_mapping.json")
    if not ter_mapping_data:
        frappe.logger().warning("TER mapping data not found or invalid format")
        return

    settings = get_or_create_settings()
    if not settings:
        return

    settings.ter_mapping_table = []

    for entry in ter_mapping_data:
        settings.append(
            "ter_mapping_table", {"tax_status": entry["tax_status"], "ter_code": entry["ter_code"]}
        )

    settings.save()
    frappe.logger().info("Imported default TER mapping")


def import_ter_brackets() -> None:
    """Import default TER brackets into Payroll Indonesia Settings"""
    ter_rate_data = load_json("default_ter_rate.json")
    if not ter_rate_data:
        frappe.logger().warning("TER rate data not found or invalid format")
        return

    settings = get_or_create_settings()
    if not settings:
        return

    settings.ter_bracket_table = []

    for ter_code_data in ter_rate_data:
        ter_code = ter_code_data["ter_code"]
        for bracket in ter_code_data["brackets"]:
            settings.append(
                "ter_bracket_table",
                {
                    "ter_code": ter_code,
                    "min_income": bracket["min_income"],
                    "max_income": bracket["max_income"] if bracket["max_income"] is not None else 0,
                    "rate_percent": bracket["rate_percent"],
                },
            )

    settings.save()
    frappe.logger().info("Imported default TER brackets")


def get_or_create_settings() -> Optional[Document]:
    """Get or create Payroll Indonesia Settings document"""
    if not frappe.db.exists("Payroll Indonesia Settings", "Payroll Indonesia Settings"):
        settings = frappe.new_doc("Payroll Indonesia Settings")
        settings.name = "Payroll Indonesia Settings"

        settings.pph21_method = "TER"
        settings.validate_tax_status_strict = 1
        settings.salary_slip_use_component_cache = 1
        settings.auto_queue_salary_slip = 0

        settings.bpjs_health_employer_rate = 4.0
        settings.bpjs_health_employer_cap = 12000000
        settings.bpjs_health_employee_rate = 1.0
        settings.bpjs_health_employee_cap = 12000000

        settings.bpjs_jht_employer_rate = 3.7
        settings.bpjs_jht_employer_cap = 9077600
        settings.bpjs_jht_employee_rate = 2.0
        settings.bpjs_jht_employee_cap = 9077600

        settings.bpjs_jkk_rate = 0.24
        settings.bpjs_jkk_cap = 9077600
        settings.bpjs_jkm_rate = 0.3
        settings.bpjs_jkm_cap = 9077600

        settings.bpjs_pension_employer_rate = 2.0
        settings.bpjs_pension_employer_cap = 9077600
        settings.bpjs_pension_employee_rate = 1.0
        settings.bpjs_pension_employee_cap = 9077600

        settings.biaya_jabatan_rate = 5.0
        settings.biaya_jabatan_cap = 6000000

        settings.fallback_income_tax_slab = None

        settings.insert()
        frappe.logger().info("Created new Payroll Indonesia Settings")
        return settings
    else:
        return frappe.get_doc("Payroll Indonesia Settings", "Payroll Indonesia Settings")


def setup_default_settings() -> None:
    """
    Setup default Payroll Indonesia settings
    This function is called from setup_module.py after_sync
    """
    try:
        import_ptkp_table()
        import_ter_mapping()
        import_ter_brackets()

        frappe.db.commit()
        frappe.logger().info("Completed Payroll Indonesia settings migration")
    except Exception as e:
        frappe.db.rollback()
        frappe.logger().error(f"Error in Payroll Indonesia settings migration: {str(e)}")


@frappe.whitelist()
def run_settings_migration() -> str:
    """
    Run settings migration manually
    Can be called from client side
    """
    try:
        setup_default_settings()
        return "Payroll Indonesia settings migration completed successfully"
    except Exception as e:
        return f"Error in Payroll Indonesia settings migration: {str(e)}"
