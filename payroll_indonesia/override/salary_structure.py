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
    for comp in config or []:
        name = comp.get("name", "").lower()
        if all(k.lower() in name for k in keywords):
            return comp.get("name")
    return default

def ensure_default_salary_structure() -> bool:
    """Create a default salary structure if it doesn't already exist."""
    structure_name = "Default Salary Structure"
    try:
        # Check if structure already exists with more detailed logging
        for name in ["Default Salary Structure", "Default Structure", "Indonesia Standard Structure"]:
            if frappe.db.exists("Salary Structure", {"name": name, "docstatus": ["<", 2]}):
                logger.info(f"Salary Structure '{name}' already exists, skipping creation")
                return False
        logger.info("No default salary structure found - creating new one")

        # Cek prasyarat
        components_count = frappe.db.count("Salary Component")
        if components_count == 0:
            logger.error("No salary components found - cannot create salary structure")
            return False

        # Log components yang akan digunakan
        defaults = _load_defaults()
        config = defaults.get("struktur_gaji", {})
        logger.info(f"Using config: {config}")

        default_company = frappe.defaults.get_global_default("company")

        if not default_company:
            companies = frappe.get_all("Company", limit=1)
            if companies:
                default_company = companies[0].name
            else:
                logger.error("No company found to associate with salary structure")
                return False

        default_tax_slab = get_default_tax_slab()

        basic_percent = config.get("basic_salary_percent", 75)
        meal_allowance = config.get("meal_allowance", 750000)
        transport_allowance = config.get("transport_allowance", 900000)
        frequency = defaults.get("defaults", {}).get("payroll_frequency", "Monthly")

        salary_components = defaults.get("salary_components", {})
        earnings_conf = salary_components.get("earnings", [])
        deductions_conf = salary_components.get("deductions", [])

        component_names = {
            "basic": _find_component_name(earnings_conf, ["gaji", "pokok"], "Gaji Pokok"),
            "meal": _find_component_name(earnings_conf, ["makan"], "Tunjangan Makan"),
            "transport": _find_component_name(earnings_conf, ["transport"], "Tunjangan Transport"),
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

        earnings = [
            {
                "salary_component": component_names["basic"],
                "abbr": "GP",
                "amount_based_on_formula": 1,
                "formula": "base",
                "condition": "",
                "depends_on_payment_days": 1,
            },
            {
                "salary_component": component_names["meal"],
                "abbr": "TM",
                "amount": meal_allowance,
                "condition": "",
                "depends_on_payment_days": 1,
            },
            {
                "salary_component": component_names["transport"],
                "abbr": "TT",
                "amount": transport_allowance,
                "condition": "",
                "depends_on_payment_days": 1,
            },
        ]

        deductions = [
            {
                "salary_component": component_names["bpjs_kesehatan"],
                "abbr": "BPJSKES",
                "amount": 0,
                "condition": "ikut_bpjs_kesehatan",
                "depends_on_payment_days": 1,
            },
            {
                "salary_component": component_names["bpjs_jht"],
                "abbr": "BPJSJHT",
                "amount": 0,
                "condition": "ikut_bpjs_ketenagakerjaan",
                "depends_on_payment_days": 1,
            },
            {
                "salary_component": component_names["bpjs_jp"],
                "abbr": "BPJSJP",
                "amount": 0,
                "condition": "ikut_bpjs_ketenagakerjaan",
                "depends_on_payment_days": 1,
            },
            {
                "salary_component": component_names["pph21"],
                "abbr": "PPH21",
                "amount": 0,
                "condition": "",
                "depends_on_payment_days": 1,
            },
        ]

        ss = frappe.new_doc("Salary Structure")
        ss.name = structure_name
        ss.salary_structure_name = structure_name
        ss.is_active = "Yes"
        ss.payroll_frequency = frequency
        ss.company = default_company
        ss.currency = "IDR"
        ss.note = "Default salary structure created automatically by Payroll Indonesia"

        for earning in earnings:
            ss.append("earnings", earning)
        for deduction in deductions:
            ss.append("deductions", deduction)

        if hasattr(ss, "tax_calculation_method"):
            ss.tax_calculation_method = "Manual"

        if hasattr(ss, "income_tax_slab") and default_tax_slab:
            ss.income_tax_slab = default_tax_slab

        ss.flags.ignore_permissions = True
        ss.flags.ignore_mandatory = True
        ss.insert()

        ss.submit()

        logger.info(f"Successfully created and submitted Salary Structure: {structure_name}")
        try:
            create_assignment = config.get("create_default_assignment", False)

            if create_assignment:
                _create_structure_assignment(ss.name, default_company, default_tax_slab)
                logger.info(f"Created default assignment for Salary Structure: {structure_name}")
        except Exception as e:
            logger.warning(f"Could not create structure assignment: {str(e)}")

        components = frappe.db.get_all("Salary Component", fields=["name", "salary_component", "type"])
        if components:
            logger.info(f"Found {len(components)} salary components")
            for comp in components:
                logger.info(f"Component: {comp.name}, Type: {comp.type}")
        else:
            logger.warning("No salary components found!")

        return True
    except Exception as e:
        logger.error(f"Error creating default Salary Structure: {str(e)}", exc_info=True)
        return False

def _create_structure_assignment(
    structure_name: str, company: str, tax_slab: Optional[str] = None
) -> bool:
    try:
        assignment = frappe.new_doc("Salary Structure Assignment")
        assignment.salary_structure = structure_name
        assignment.company = company
        assignment.from_date = getdate()
        assignment.base = 0
        if tax_slab and hasattr(assignment, "income_tax_slab"):
            assignment.income_tax_slab = tax_slab

        assignment.flags.ignore_permissions = True
        assignment.flags.ignore_mandatory = True
        assignment.insert()

        return True

    except Exception as e:
        logger.error(f"Error creating structure assignment: {str(e)}")
        return False

def setup_default_salary_structure():
    try:
        result = ensure_default_salary_structure()
        if not result:
            logger.warning("Could not create default salary structure - checking reason")
            existing = frappe.db.get_all("Salary Structure",
                filters={"name": ["in", ["Default Salary Structure", "Default Structure", "Indonesia Standard Structure"]]})
            if existing:
                logger.info(f"Found existing structure: {existing[0].name}")
            else:
                logger.warning("No existing structure found - might be an error in creation")
    except Exception as e:
        logger.error(f"Error creating salary structure: {str(e)}", exc_info=True)