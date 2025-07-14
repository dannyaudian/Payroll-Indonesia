# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, flt
from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.utilities.tax_slab import get_default_tax_slab

__all__ = ["ensure_default_salary_structure", "create_default_salary_structure"]

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
    """Find a component name by keywords in the configuration."""
    for comp in config or []:
        name = comp.get("name", "").lower()
        if all(k.lower() in name for k in keywords):
            return comp.get("name")
    return default

def _get_component_tax_effects(component_name: str) -> Tuple[str, str]:
    """Get the tax effect configuration for a component when used as earning and deduction.
    
    Args:
        component_name: The name of the salary component
        
    Returns:
        Tuple containing tax effect as earning and as deduction
    """
    try:
        component = frappe.get_doc("Salary Component", component_name)
        
        # Default tax effects
        tax_effect_earning = "Penambah Bruto/Objek Pajak"
        tax_effect_deduction = "Pengurang Netto/Tax Deduction"
        
        # Check if the component has tax effect mappings
        if hasattr(component, "tax_effect_by_type") and component.tax_effect_by_type:
            for mapping in component.tax_effect_by_type:
                if mapping.component_type == "Earning":
                    tax_effect_earning = mapping.tax_effect_type
                elif mapping.component_type == "Deduction":
                    tax_effect_deduction = mapping.tax_effect_type
        
        # Fallback based on is_tax_applicable flag
        elif hasattr(component, "is_tax_applicable"):
            if not component.is_tax_applicable:
                tax_effect_earning = "Tidak Berpengaruh ke Pajak"
                tax_effect_deduction = "Tidak Berpengaruh ke Pajak"
        
        return tax_effect_earning, tax_effect_deduction
        
    except Exception as e:
        logger.warning(f"Error getting tax effects for {component_name}: {str(e)}")
        return "Penambah Bruto/Objek Pajak", "Pengurang Netto/Tax Deduction"

def ensure_default_salary_structure() -> bool:
    """Ensure a default salary structure exists, creating one if it doesn't."""
    structure_name = "Default Salary Structure"
    try:
        for name in ["Default Salary Structure", "Default Structure", "Indonesia Standard Structure"]:
            if frappe.db.exists("Salary Structure", {"name": name, "docstatus": ["<", 2]}):
                logger.info(f"Salary Structure '{name}' already exists, skipping creation")
                return False
        logger.info("No default salary structure found - creating new one")

        components_count = frappe.db.count("Salary Component")
        if components_count == 0:
            logger.error("No salary components found - cannot create salary structure")
            return False

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

        basic_percent = config.get("basic_salary_percent", 100)
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

        # Get tax effect types for each component
        tax_effects = {}
        for key, component_name in component_names.items():
            tax_effects[key] = _get_component_tax_effects(component_name)

        earnings = [
            {
                "salary_component": component_names["basic"],
                "abbr": "GP",
                "amount_based_on_formula": 1,
                "formula": "base",
                "condition": "",
                "depends_on_payment_days": 1,
                "tax_effect_type": tax_effects["basic"][0],  # As earning
            },
            {
                "salary_component": component_names["meal"],
                "abbr": "TM",
                "amount": meal_allowance,
                "condition": "",
                "depends_on_payment_days": 1,
                "tax_effect_type": tax_effects["meal"][0],  # As earning
            },
            {
                "salary_component": component_names["transport"],
                "abbr": "TT",
                "amount": transport_allowance,
                "condition": "",
                "depends_on_payment_days": 1,
                "tax_effect_type": tax_effects["transport"][0],  # As earning
            },
        ]

        deductions = [
            {
                "salary_component": component_names["bpjs_kesehatan"],
                "abbr": "BPJSKES",
                "amount": 0,
                "condition": "ikut_bpjs_kesehatan",
                "depends_on_payment_days": 1,
                "tax_effect_type": tax_effects["bpjs_kesehatan"][1],  # As deduction
            },
            {
                "salary_component": component_names["bpjs_jht"],
                "abbr": "BPJSJHT",
                "amount": 0,
                "condition": "ikut_bpjs_ketenagakerjaan",
                "depends_on_payment_days": 1,
                "tax_effect_type": tax_effects["bpjs_jht"][1],  # As deduction
            },
            {
                "salary_component": component_names["bpjs_jp"],
                "abbr": "BPJSJP",
                "amount": 0,
                "condition": "ikut_bpjs_ketenagakerjaan",
                "depends_on_payment_days": 1,
                "tax_effect_type": tax_effects["bpjs_jp"][1],  # As deduction
            },
            {
                "salary_component": component_names["pph21"],
                "abbr": "PPH21",
                "amount": 0,
                "condition": "",
                "depends_on_payment_days": 1,
                "tax_effect_type": "Tidak Berpengaruh ke Pajak",  # PPh 21 doesn't affect its own calculation
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
            # Clean up the dict to remove extra fields if not supported
            if not frappe.get_meta("Salary Detail").has_field("tax_effect_type"):
                earning.pop("tax_effect_type", None)
            ss.append("earnings", earning)
            
        for deduction in deductions:
            # Clean up the dict to remove extra fields if not supported
            if not frappe.get_meta("Salary Detail").has_field("tax_effect_type"):
                deduction.pop("tax_effect_type", None)
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
    """Create a salary structure assignment for testing."""
    try:
        assignment = frappe.new_doc("Salary Structure Assignment")
        assignment.salary_structure = structure_name
        assignment.company = company
        assignment.from_date = getdate()
        assignment.base = flt(4000000)  # Set a reasonable base salary
        
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
    """Set up default salary structure during app installation."""
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

def create_default_salary_structure() -> bool:
    """Create a default salary structure using Payroll Indonesia components and tax configuration."""
    structure_name = "Payroll Indonesia Default"

    try:
        if frappe.db.exists("Salary Structure", structure_name):
            logger.info(f"Salary Structure '{structure_name}' already exists, skipping creation")
            return True

        logger.info(f"Creating default salary structure: {structure_name}")

        defaults = _load_defaults()
        config = defaults.get("struktur_gaji", {})

        default_company = frappe.defaults.get_global_default("company")
        if not default_company:
            companies = frappe.get_all("Company", limit=1)
            if companies:
                default_company = companies[0].name
            else:
                logger.error("No company found to associate with salary structure")
                return False

        default_tax_slab = get_default_tax_slab()

        salary_components = defaults.get("salary_components", {})
        earnings_conf = salary_components.get("earnings", [])
        deductions_conf = salary_components.get("deductions", [])

        basic_percent = config.get("basic_salary_percent", 100)
        meal_allowance = config.get("meal_allowance", 750000)
        transport_allowance = config.get("transport_allowance", 900000)
        frequency = defaults.get("defaults", {}).get("payroll_frequency", "Monthly")

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

        # Get tax effect types for each component
        tax_effects = {}
        for key, component_name in component_names.items():
            tax_effects[key] = _get_component_tax_effects(component_name)

        ss = frappe.new_doc("Salary Structure")
        ss.name = structure_name
        ss.salary_structure_name = structure_name
        ss.is_active = "Yes"
        ss.payroll_frequency = frequency
        ss.company = default_company
        ss.currency = "IDR"
        ss.note = "Default salary structure created automatically by Payroll Indonesia"

        # Define all components with their tax effects
        earnings_data = [
            {
                "salary_component": component_names["basic"],
                "abbr": "GP",
                "amount_based_on_formula": 1,
                "formula": "base",
                "condition": "",
                "depends_on_payment_days": 1,
                "tax_effect_type": tax_effects["basic"][0],  # As earning
            },
            {
                "salary_component": component_names["meal"],
                "abbr": "TM",
                "amount": meal_allowance,
                "condition": "",
                "depends_on_payment_days": 1,
                "tax_effect_type": tax_effects["meal"][0],  # As earning
            },
            {
                "salary_component": component_names["transport"],
                "abbr": "TT",
                "amount": transport_allowance,
                "condition": "",
                "depends_on_payment_days": 1,
                "tax_effect_type": tax_effects["transport"][0],  # As earning
            }
        ]
        
        deductions_data = [
            {
                "salary_component": component_names["bpjs_kesehatan"],
                "abbr": "BPJSKES",
                "amount": 0,
                "condition": "ikut_bpjs_kesehatan",
                "depends_on_payment_days": 1,
                "tax_effect_type": tax_effects["bpjs_kesehatan"][1],  # As deduction
            },
            {
                "salary_component": component_names["bpjs_jht"],
                "abbr": "BPJSJHT",
                "amount": 0,
                "condition": "ikut_bpjs_ketenagakerjaan",
                "depends_on_payment_days": 1,
                "tax_effect_type": tax_effects["bpjs_jht"][1],  # As deduction
            },
            {
                "salary_component": component_names["bpjs_jp"],
                "abbr": "BPJSJP",
                "amount": 0,
                "condition": "ikut_bpjs_ketenagakerjaan",
                "depends_on_payment_days": 1,
                "tax_effect_type": tax_effects["bpjs_jp"][1],  # As deduction
            },
            {
                "salary_component": component_names["pph21"],
                "abbr": "PPH21",
                "amount": 0,
                "condition": "",
                "depends_on_payment_days": 1,
                "tax_effect_type": "Tidak Berpengaruh ke Pajak",  # PPh 21 doesn't affect its own calculation
            }
        ]
        
        # Check if Salary Detail has tax_effect_type field before adding
        has_tax_effect_field = frappe.get_meta("Salary Detail").has_field("tax_effect_type")
        
        for earning in earnings_data:
            if not has_tax_effect_field:
                earning.pop("tax_effect_type", None)
            ss.append("earnings", earning)

        for deduction in deductions_data:
            if not has_tax_effect_field:
                deduction.pop("tax_effect_type", None)
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

        create_assignment = config.get("create_default_assignment", False)
        if create_assignment:
            try:
                _create_structure_assignment(ss.name, default_company, default_tax_slab)
                logger.info(f"Created default assignment for Salary Structure: {structure_name}")
            except Exception as e:
                logger.warning(f"Could not create structure assignment: {str(e)}")

        return True

    except Exception as e:
        logger.error(f"Error creating default Salary Structure: {str(e)}", exc_info=True)
        return False