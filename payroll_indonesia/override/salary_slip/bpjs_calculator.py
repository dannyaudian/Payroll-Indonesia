# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:29:18 by dannyaudian

"""
BPJS calculator module - satu-satunya kalkulator BPJS.

Provides standardized calculation functions for BPJS deductions in Indonesian payroll.
"""

from typing import Any, Dict, Optional, Union, List

import frappe
from frappe.utils import flt, cint

from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.config.config import get_live_config, get_component_tax_effect
from payroll_indonesia.constants import (
    DEFAULT_UMR,
    BPJS_KESEHATAN_EMPLOYEE_PERCENT,
    BPJS_KESEHATAN_EMPLOYER_PERCENT,
    BPJS_KESEHATAN_MAX_SALARY,
    BPJS_JHT_EMPLOYEE_PERCENT,
    BPJS_JHT_EMPLOYER_PERCENT,
    BPJS_JP_EMPLOYEE_PERCENT,
    BPJS_JP_EMPLOYER_PERCENT,
    BPJS_JP_MAX_SALARY,
    BPJS_JKK_PERCENT,
    BPJS_JKM_PERCENT,
)

# Define public API
__all__ = ["calculate_bpjs", "calculate_components", "validate_bpjs_percentages"]


def is_valid_percent(value: Union[float, int, str]) -> bool:
    """Check if a value is a valid percentage between 0 and 100."""
    try:
        percent = flt(value)
        return 0 <= percent <= 100
    except (ValueError, TypeError):
        return False


def calculate_bpjs(
    base_salary: float,
    rate_percent: float,
    *,
    max_salary: Optional[float] = None,
) -> int:
    """
    Calculate BPJS deduction amount based on salary and rate.

    Args:
        base_salary: The base salary amount for calculation
        rate_percent: The BPJS rate percentage (e.g., 1.0 for 1%)
        max_salary: Optional maximum salary cap for the calculation

    Returns:
        int: The calculated BPJS amount as a rounded integer (IDR has no cents)
    """
    try:
        # Ensure inputs are proper float values
        base_salary = flt(base_salary)
        rate_percent = flt(rate_percent)

        # Validate inputs
        if base_salary < 0:
            logger.warning(f"Negative base salary provided: {base_salary}. Using absolute value.")
            base_salary = abs(base_salary)

        if not is_valid_percent(rate_percent):
            logger.warning(
                f"Invalid BPJS rate percentage: {rate_percent}. "
                f"Should be between 0-100. Using absolute value capped at 100."
            )
            rate_percent = min(abs(rate_percent), 100)

        # Apply maximum salary cap if provided
        if max_salary is not None and max_salary > 0 and base_salary > max_salary:
            base_salary = max_salary

        # Calculate the BPJS amount (rate_percent is a percentage, so divide by 100)
        bpjs_amount = base_salary * (rate_percent / 100.0)

        # Round to nearest whole number (IDR doesn't have cents)
        return round(bpjs_amount)

    except Exception as e:
        logger.exception(f"Error calculating BPJS amount: {str(e)}")
        return 0


def validate_bpjs_percentages(cfg: Dict[str, Any]) -> bool:
    """
    Validate all percentage values in BPJS config.

    Args:
        cfg: Configuration dictionary

    Returns:
        bool: True if all are within 0-100 range, False otherwise
    """
    try:
        bpjs = cfg.get("bpjs", {})
        if not bpjs:
            logger.warning("BPJS configuration not found")
            return False

        percentage_keys = [
            "kesehatan_employee_percent",
            "kesehatan_employer_percent",
            "jht_employee_percent",
            "jht_employer_percent",
            "jp_employee_percent",
            "jp_employer_percent",
            "jkk_percent",
            "jkm_percent",
        ]

        for key in percentage_keys:
            value = bpjs.get(key)
            if value is None:
                logger.warning(f"BPJS config key not found: {key}")
                continue

            try:
                percentage = float(value)
                if not 0 <= percentage <= 100:
                    logger.warning(f"BPJS config {key} out of bounds: {percentage}")
                    return False
            except (ValueError, TypeError):
                logger.warning(f"BPJS config {key} not float: {value}")
                return False

        return True

    except Exception as e:
        logger.exception(f"Error validating BPJS percentages: {str(e)}")
        return False


def _get_base_salary(slip: Any) -> float:
    """
    Extract base salary from salary slip or return default UMR.
    
    Uses tax effect types to identify components that should be included in base salary.

    Args:
        slip: The Salary Slip document

    Returns:
        float: Base salary amount
    """
    try:
        # Try to get from gross_pay attribute (preferred)
        if hasattr(slip, "gross_pay") and slip.gross_pay:
            return float(slip.gross_pay)

        # Try to get from earnings list using tax effect types
        base_salary = 0.0
        if hasattr(slip, "earnings"):
            for earning in getattr(slip, "earnings", []):
                component_name = getattr(earning, "salary_component", "")
                # Get tax effect for this component
                tax_effect = get_component_tax_effect(component_name, "Earning")
                
                # Include components that are part of taxable gross income
                if tax_effect in [
                    "Penambah Bruto/Objek Pajak", 
                    "Natura/Fasilitas (Objek Pajak)"
                ]:
                    base_salary += float(getattr(earning, "amount", 0))
            
            if base_salary > 0:
                return base_salary

        # Use default UMR if no base salary found
        config = get_live_config()
        default_umr = float(config.get("bpjs", {}).get("default_umr", DEFAULT_UMR))
        logger.warning(
            f"No base salary found for slip {getattr(slip, 'name', 'unknown')}. "
            f"Using default UMR: {default_umr}"
        )
        return default_umr

    except Exception as e:
        logger.exception(f"Error getting base salary: {str(e)}")
        # Fall back to default UMR
        return float(DEFAULT_UMR)


def _is_bpjs_kesehatan_component(component_name: str) -> bool:
    """
    Check if a component is related to BPJS Kesehatan based on name or tax effect.
    
    Args:
        component_name: Name of the salary component
        
    Returns:
        bool: True if it's a BPJS Kesehatan component
    """
    kesehatan_keywords = ["kesehatan", "health"]
    return any(keyword in component_name.lower() for keyword in kesehatan_keywords)


def _is_bpjs_jht_component(component_name: str) -> bool:
    """
    Check if a component is related to BPJS JHT based on name or tax effect.
    
    Args:
        component_name: Name of the salary component
        
    Returns:
        bool: True if it's a BPJS JHT component
    """
    jht_keywords = ["jht", "hari tua"]
    return any(keyword in component_name.lower() for keyword in jht_keywords)


def _is_bpjs_jp_component(component_name: str) -> bool:
    """
    Check if a component is related to BPJS JP based on name or tax effect.
    
    Args:
        component_name: Name of the salary component
        
    Returns:
        bool: True if it's a BPJS JP component
    """
    jp_keywords = ["jp", "pensiun"]
    return any(keyword in component_name.lower() for keyword in jp_keywords)


def _is_bpjs_jkk_component(component_name: str) -> bool:
    """
    Check if a component is related to BPJS JKK based on name or tax effect.
    
    Args:
        component_name: Name of the salary component
        
    Returns:
        bool: True if it's a BPJS JKK component
    """
    jkk_keywords = ["jkk", "kecelakaan"]
    return any(keyword in component_name.lower() for keyword in jkk_keywords)


def _is_bpjs_jkm_component(component_name: str) -> bool:
    """
    Check if a component is related to BPJS JKM based on name or tax effect.
    
    Args:
        component_name: Name of the salary component
        
    Returns:
        bool: True if it's a BPJS JKM component
    """
    jkm_keywords = ["jkm", "kematian"]
    return any(keyword in component_name.lower() for keyword in jkm_keywords)


def _find_component_amounts(slip: Any, component_type: str) -> Dict[str, float]:
    """
    Find BPJS component amounts in the salary slip based on tax effect and component names.
    
    Args:
        slip: The Salary Slip document
        component_type: Either 'earnings' or 'deductions'
        
    Returns:
        Dict[str, float]: Dictionary of component names and amounts
    """
    component_amounts = {}
    
    if not hasattr(slip, component_type):
        return component_amounts
        
    components_list = getattr(slip, component_type, [])
    
    for component in components_list:
        component_name = getattr(component, "salary_component", "")
        amount = flt(getattr(component, "amount", 0))
        
        # Store component amount by name
        component_amounts[component_name] = amount
        
    return component_amounts


def calculate_components(slip: Any) -> Dict[str, float]:
    """
    Calculate BPJS (employee & employer) components for salary slip.
    
    This function now uses tax effect types to determine which components are 
    included in the base salary and which are BPJS components.

    Args:
        slip: The Salary Slip document

    Returns:
        Dict[str, float]: Dictionary with all BPJS components and totals
    """
    try:
        # Initialize empty result with zeros for all components
        result = {
            "kesehatan_employee": 0,
            "kesehatan_employer": 0,
            "jht_employee": 0,
            "jht_employer": 0,
            "jp_employee": 0,
            "jp_employer": 0,
            "jkk": 0,
            "jkm": 0,
            "total_employee": 0,
            "total_employer": 0,
        }

        # Get configuration
        cfg = get_live_config()
        if not cfg:
            logger.warning("Failed to get configuration")
            return result

        # Validate percentages
        if not validate_bpjs_percentages(cfg):
            logger.warning("BPJS config percentages invalid. Using default values.")
            # Continue with default values instead of aborting

        bpjs_config = cfg.get("bpjs", {})

        # Check if employee is enrolled in BPJS
        should_calculate = True
        if hasattr(slip, "employee") and slip.employee:
            try:
                # Check if employee is enrolled in BPJS
                employee_doc = frappe.get_doc("Employee", slip.employee)
                ikut_bpjs_kesehatan = cint(getattr(employee_doc, "ikut_bpjs_kesehatan", 1))
                ikut_bpjs_ketenagakerjaan = cint(
                    getattr(employee_doc, "ikut_bpjs_ketenagakerjaan", 1)
                )

                if not (ikut_bpjs_kesehatan or ikut_bpjs_ketenagakerjaan):
                    logger.info(f"Employee {slip.employee} is not enrolled in any BPJS program")
                    return result

            except Exception as e:
                logger.exception(f"Error checking employee BPJS enrollment: {str(e)}")
                # Continue with calculation as default

        # Find existing BPJS components in slip
        deduction_amounts = _find_component_amounts(slip, "deductions")
        
        # Check if BPJS components already exist and have amounts
        kesehatan_employee_comp = next((comp for comp in deduction_amounts if _is_bpjs_kesehatan_component(comp) and "employee" in comp.lower()), None)
        jht_employee_comp = next((comp for comp in deduction_amounts if _is_bpjs_jht_component(comp) and "employee" in comp.lower()), None)
        jp_employee_comp = next((comp for comp in deduction_amounts if _is_bpjs_jp_component(comp) and "employee" in comp.lower()), None)
        
        # If components exist with amounts, use those values
        if kesehatan_employee_comp:
            result["kesehatan_employee"] = deduction_amounts[kesehatan_employee_comp]
        if jht_employee_comp:
            result["jht_employee"] = deduction_amounts[jht_employee_comp]
        if jp_employee_comp:
            result["jp_employee"] = deduction_amounts[jp_employee_comp]
            
        # If all employee components have values, skip calculation
        if result["kesehatan_employee"] > 0 and result["jht_employee"] > 0 and result["jp_employee"] > 0:
            # Just calculate totals
            result["total_employee"] = (
                result["kesehatan_employee"] + result["jht_employee"] + result["jp_employee"]
            )
            return result

        # Get base salary
        base_salary = _get_base_salary(slip)
        if base_salary <= 0:
            logger.warning(f"Base salary is zero or negative: {base_salary}")
            return result

        # Get salary caps from config or defaults with warning if missing
        kesehatan_max = BPJS_KESEHATAN_MAX_SALARY
        if "kesehatan_max_salary" in bpjs_config:
            kesehatan_max = float(bpjs_config["kesehatan_max_salary"])
        else:
            logger.warning(
                f"BPJS Kesehatan max salary not found in config. Using default: {kesehatan_max}"
            )

        jp_max = BPJS_JP_MAX_SALARY
        if "jp_max_salary" in bpjs_config:
            jp_max = float(bpjs_config["jp_max_salary"])
        else:
            logger.warning(f"BPJS JP max salary not found in config. Using default: {jp_max}")

        # Get percentages with warnings if missing
        percentages = {}

        # Kesehatan employee
        if "kesehatan_employee_percent" in bpjs_config:
            percentages["kesehatan_emp"] = float(bpjs_config["kesehatan_employee_percent"])
        else:
            percentages["kesehatan_emp"] = BPJS_KESEHATAN_EMPLOYEE_PERCENT
            logger.warning(
                f"BPJS Kesehatan employee percent not found. Using default: {percentages['kesehatan_emp']}%"
            )

        # Kesehatan employer
        if "kesehatan_employer_percent" in bpjs_config:
            percentages["kesehatan_com"] = float(bpjs_config["kesehatan_employer_percent"])
        else:
            percentages["kesehatan_com"] = BPJS_KESEHATAN_EMPLOYER_PERCENT
            logger.warning(
                f"BPJS Kesehatan employer percent not found. Using default: {percentages['kesehatan_com']}%"
            )

        # JHT employee
        if "jht_employee_percent" in bpjs_config:
            percentages["jht_emp"] = float(bpjs_config["jht_employee_percent"])
        else:
            percentages["jht_emp"] = BPJS_JHT_EMPLOYEE_PERCENT
            logger.warning(
                f"BPJS JHT employee percent not found. Using default: {percentages['jht_emp']}%"
            )

        # JHT employer
        if "jht_employer_percent" in bpjs_config:
            percentages["jht_com"] = float(bpjs_config["jht_employer_percent"])
        else:
            percentages["jht_com"] = BPJS_JHT_EMPLOYER_PERCENT
            logger.warning(
                f"BPJS JHT employer percent not found. Using default: {percentages['jht_com']}%"
            )

        # JP employee
        if "jp_employee_percent" in bpjs_config:
            percentages["jp_emp"] = float(bpjs_config["jp_employee_percent"])
        else:
            percentages["jp_emp"] = BPJS_JP_EMPLOYEE_PERCENT
            logger.warning(
                f"BPJS JP employee percent not found. Using default: {percentages['jp_emp']}%"
            )

        # JP employer
        if "jp_employer_percent" in bpjs_config:
            percentages["jp_com"] = float(bpjs_config["jp_employer_percent"])
        else:
            percentages["jp_com"] = BPJS_JP_EMPLOYER_PERCENT
            logger.warning(
                f"BPJS JP employer percent not found. Using default: {percentages['jp_com']}%"
            )

        # JKK
        if "jkk_percent" in bpjs_config:
            percentages["jkk"] = float(bpjs_config["jkk_percent"])
        else:
            percentages["jkk"] = BPJS_JKK_PERCENT
            logger.warning(f"BPJS JKK percent not found. Using default: {percentages['jkk']}%")

        # JKM
        if "jkm_percent" in bpjs_config:
            percentages["jkm"] = float(bpjs_config["jkm_percent"])
        else:
            percentages["jkm"] = BPJS_JKM_PERCENT
            logger.warning(f"BPJS JKM percent not found. Using default: {percentages['jkm']}%")

        # Calculate each component
        # Use existing value if available, otherwise calculate
        if not kesehatan_employee_comp:
            result["kesehatan_employee"] = calculate_bpjs(
                base_salary, percentages["kesehatan_emp"], max_salary=kesehatan_max
            )

        result["kesehatan_employer"] = calculate_bpjs(
            base_salary, percentages["kesehatan_com"], max_salary=kesehatan_max
        )

        if not jht_employee_comp:
            result["jht_employee"] = calculate_bpjs(base_salary, percentages["jht_emp"])

        result["jht_employer"] = calculate_bpjs(base_salary, percentages["jht_com"])

        if not jp_employee_comp:
            result["jp_employee"] = calculate_bpjs(
                base_salary, percentages["jp_emp"], max_salary=jp_max
            )

        result["jp_employer"] = calculate_bpjs(
            base_salary, percentages["jp_com"], max_salary=jp_max
        )

        result["jkk"] = calculate_bpjs(base_salary, percentages["jkk"])

        result["jkm"] = calculate_bpjs(base_salary, percentages["jkm"])

        # Calculate totals
        result["total_employee"] = (
            result["kesehatan_employee"] + result["jht_employee"] + result["jp_employee"]
        )

        result["total_employer"] = (
            result["kesehatan_employer"]
            + result["jht_employer"]
            + result["jp_employer"]
            + result["jkk"]
            + result["jkm"]
        )

        employee_id = getattr(slip, "employee", "unknown")
        logger.debug(f"BPJS calculation for {employee_id}: {result}")
        return result

    except Exception as e:
        logger.exception(f"Error calculating BPJS components: {str(e)}")
        return {
            "kesehatan_employee": 0,
            "kesehatan_employer": 0,
            "jht_employee": 0,
            "jht_employer": 0,
            "jp_employee": 0,
            "jp_employer": 0,
            "jkk": 0,
            "jkm": 0,
            "total_employee": 0,
            "total_employer": 0,
        }