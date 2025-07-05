# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import json
from pathlib import Path
from typing import Dict, Any, List, Optional

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime
from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.utilities.tax_slab import get_default_tax_slab

__all__ = ["ensure_default_salary_structure"]


def _load_defaults() -> Dict[str, Any]:
    """
    Load configuration defaults from defaults.json.

    Returns:
        Dict[str, Any]: Configuration dictionary
    """
    try:
        app_path = frappe.get_app_path("payroll_indonesia")
        config_path = Path(app_path) / "config" / "defaults.json"

        if not config_path.exists():
            logger.warning(f"defaults.json not found at {config_path}")
            return {}

        with open(config_path, "r") as f:
            defaults = json.load(f)

        logger.debug(f"Loaded defaults.json with {len(defaults)} sections")
        return defaults

    except Exception as e:
        logger.error(f"Error loading defaults.json: {str(e)}")
        return {}


def _find_component_name(config: List[Dict[str, Any]], keywords: List[str], default: str) -> str:
    """Return component name matching all keywords from the config list."""
    for comp in config or []:
        name = comp.get("name", "").lower()
        if all(k.lower() in name for k in keywords):
            return comp.get("name")
    return default


def ensure_default_salary_structure() -> bool:
    """
    Create a default salary structure if it doesn't already exist.

    This function checks if a salary structure named 'Default Salary Structure'
    already exists. If not, it creates one with standard earnings and deductions
    components based on configuration values from defaults.json.

    Returns:
        bool: True if a new structure was created, False if it already exists
    """
    structure_name = "Default Salary Structure"

    try:
        # Check if structure already exists
        if frappe.db.exists("Salary Structure", {"name": structure_name, "docstatus": ["<", 2]}):
            logger.info(f"Salary Structure '{structure_name}' already exists, skipping creation")
            return False

        # Load configuration defaults
        defaults = _load_defaults()
        config = defaults.get("struktur_gaji", {})

        # Get default company
        default_company = frappe.defaults.get_global_default("company")
        if not default_company:
            companies = frappe.get_all("Company", limit=1)
            if companies:
                default_company = companies[0].name
            else:
                logger.error("No company found to associate with salary structure")
                return False

        # Get default tax slab
        default_tax_slab = get_default_tax_slab()

        # Get configuration values with defaults
        basic_percent = config.get("basic_salary_percent", 75)
        meal_allowance = config.get("meal_allowance", 750000)
        transport_allowance = config.get("transport_allowance", 900000)
        frequency = config.get("frequency", "Monthly")

        salary_components = defaults.get("salary_components", {})
        earnings_conf = salary_components.get("earnings", [])
        deductions_conf = salary_components.get("deductions", [])

        component_names = {
            "basic": _find_component_name(earnings_conf, ["gaji", "pokok"], "Basic Salary"),
            "meal": _find_component_name(earnings_conf, ["makan"], "Meal Allowance"),
            "transport": _find_component_name(earnings_conf, ["transport"], "Transport Allowance"),
            "bpjs_kesehatan": _find_component_name(
                deductions_conf, ["kesehatan", "employee"], "BPJS Kesehatan Employee"
            ),
            "bpjs_jht": _find_component_name(
                deductions_conf, ["jht", "employee"], "BPJS JHT Employee"
            ),
            "bpjs_jp": _find_component_name(
                deductions_conf, ["jp", "employee"], "BPJS JP Employee"
            ),
            "pph21": _find_component_name(deductions_conf, ["pph", "21"], "PPh 21"),
        }

        # Define earnings components
        earnings = [
            {
                "salary_component": component_names["basic"],
                "abbr": "BS",
                "amount_based_on_formula": 1,
                "formula": "base",
                "condition": "",
                "depends_on_payment_days": 1,
            },
            {
                "salary_component": component_names["meal"],
                "abbr": "MA",
                "amount": meal_allowance,
                "condition": "",
                "depends_on_payment_days": 1,
            },
            {
                "salary_component": component_names["transport"],
                "abbr": "TA",
                "amount": transport_allowance,
                "condition": "",
                "depends_on_payment_days": 1,
            },
        ]

        # Define deductions components
        deductions = [
            {
                "salary_component": component_names["bpjs_kesehatan"],
                "abbr": "BKE",
                "amount": 0,
                "condition": "ikut_bpjs_kesehatan",
                "depends_on_payment_days": 1,
            },
            {
                "salary_component": component_names["bpjs_jht"],
                "abbr": "BJE",
                "amount": 0,
                "condition": "ikut_bpjs_ketenagakerjaan",
                "depends_on_payment_days": 1,
            },
            {
                "salary_component": component_names["bpjs_jp"],
                "abbr": "BJPE",
                "amount": 0,
                "condition": "ikut_bpjs_ketenagakerjaan",
                "depends_on_payment_days": 1,
            },
            {
                "salary_component": component_names["pph21"],
                "abbr": "PPh",
                "amount": 0,
                "condition": "",
                "depends_on_payment_days": 1,
            },
        ]

        # Create the structure
        ss = frappe.new_doc("Salary Structure")
        ss.name = structure_name
        ss.salary_structure_name = structure_name
        ss.is_active = "Yes"
        ss.payroll_frequency = frequency
        ss.company = default_company
        ss.currency = "IDR"
        ss.note = "Default salary structure created automatically by Payroll Indonesia"

        # Add earnings
        for earning in earnings:
            ss.append("earnings", earning)

        # Add deductions
        for deduction in deductions:
            ss.append("deductions", deduction)

        # Set tax calculation method and tax slab if field exists
        if hasattr(ss, "tax_calculation_method"):
            ss.tax_calculation_method = "Manual"

        if hasattr(ss, "income_tax_slab") and default_tax_slab:
            ss.income_tax_slab = default_tax_slab

        # Save with flags
        ss.flags.ignore_permissions = True
        ss.flags.ignore_mandatory = True
        ss.insert()

        # Submit the structure
        ss.submit()

        logger.info(f"Successfully created and submitted Salary Structure: {structure_name}")

        # Create assignment for all employees if needed
        try:
            # Check if we should create an assignment for all employees
            create_assignment = config.get("create_default_assignment", False)

            if create_assignment:
                _create_structure_assignment(ss.name, default_company, default_tax_slab)
                logger.info(f"Created default assignment for Salary Structure: {structure_name}")
        except Exception as e:
            logger.warning(f"Could not create structure assignment: {str(e)}")

        return True

    except Exception as e:
        logger.error(f"Error creating default Salary Structure: {str(e)}")
        return False


def _create_structure_assignment(
    structure_name: str, company: str, tax_slab: Optional[str] = None
) -> bool:
    """
    Create a salary structure assignment for all employees.

    Args:
        structure_name: Name of the salary structure
        company: Company to assign to
        tax_slab: Income tax slab to use

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        assignment = frappe.new_doc("Salary Structure Assignment")
        assignment.salary_structure = structure_name
        assignment.company = company
        assignment.from_date = getdate()
        assignment.base = 0  # This will be set per employee

        if tax_slab and hasattr(assignment, "income_tax_slab"):
            assignment.income_tax_slab = tax_slab

        assignment.flags.ignore_permissions = True
        assignment.flags.ignore_mandatory = True
        assignment.insert()

        return True

    except Exception as e:
        logger.error(f"Error creating structure assignment: {str(e)}")
        return False
