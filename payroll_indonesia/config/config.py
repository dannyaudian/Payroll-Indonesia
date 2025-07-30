import frappe
from frappe import ValidationError
from frappe.utils import flt

SETTINGS_DOCTYPE = "Payroll Indonesia Settings"
SETTINGS_NAME = "Payroll Indonesia Settings"

def get_settings():
    """
    Return cached Payroll Indonesia Settings document.
    """
    try:
        return frappe.get_cached_doc(SETTINGS_DOCTYPE, SETTINGS_NAME)
    except Exception:
        class DummySettings(dict):
            def get(self, key, default=None):
                return default
        return DummySettings()

def get_value(fieldname: str, default=None):
    """
    Helper to fetch a field value from Payroll Indonesia Settings.
    """
    return get_settings().get(fieldname, default)

def get_bpjs_rate(fieldname: str) -> float:
    """
    Return BPJS rate (%) for the given fieldname.
    """
    return flt(get_value(fieldname))

def get_bpjs_cap(fieldname: str) -> float:
    """
    Return BPJS cap amount for the given fieldname.
    """
    return flt(get_value(fieldname))

def get_ptkp_amount_from_tax_status(tax_status: str) -> float:
    """
    Return PTKP amount for the given tax_status from PTKP Table.
    """
    if not tax_status:
        raise ValidationError("PTKP amount lookup: tax_status is empty.")
    if not frappe.db.exists("PTKP Table", {"tax_status": tax_status}):
        raise ValidationError(f"PTKP Table: tax_status '{tax_status}' not found.")
    row = frappe.get_value(
        "PTKP Table",
        {"tax_status": tax_status},
        ["ptkp_amount"],
        as_dict=True,
    )
    if row and row.get("ptkp_amount") is not None:
        return flt(row["ptkp_amount"])
    frappe.logger().warning(
        f"PTKP Table: No ptkp_amount found for tax_status '{tax_status}'."
    )
    return 0.0

def get_ptkp_amount(employee_doc) -> float:
    """
    Return PTKP amount for employee_doc using field tax_status.
    """
    tax_status = getattr(employee_doc, "tax_status", None) or employee_doc.get("tax_status") if isinstance(employee_doc, dict) else None
    return get_ptkp_amount_from_tax_status(tax_status)

def get_ter_code(employee_doc) -> str | None:
    """
    Get TER code for employee from TER Mapping Table based on tax_status.
    Returns None if not found.
    """
    tax_status = getattr(employee_doc, "tax_status", None) or employee_doc.get("tax_status") if isinstance(employee_doc, dict) else None
    if not tax_status:
        frappe.logger().warning("TER code lookup: Employee tax_status is empty.")
        return None
    # Check if mapping exists
    if not frappe.db.exists("TER Mapping Table", {"tax_status": tax_status}):
        frappe.logger().warning(f"TER Mapping Table: tax_status '{tax_status}' not found.")
        return None
    row = frappe.get_value(
        "TER Mapping Table",
        {"tax_status": tax_status},
        ["ter_code"],
        as_dict=True,
    )
    if row and "ter_code" in row:
        return row["ter_code"]
    frappe.logger().warning(f"TER Mapping Table: No ter_code found for tax_status '{tax_status}'.")
    return None

def get_ter_rate(ter_code: str, monthly_income: float) -> float:
    """
    Get TER rate from TER Bracket Table for given ter_code and monthly_income.
    Returns rate_percent (float), 0.0 if not found.
    """
    if not ter_code:
        frappe.logger().warning("TER rate lookup: ter_code is empty.")
        return 0.0
    brackets = frappe.get_all(
        "TER Bracket Table",
        filters={"ter_code": ter_code},
        fields=["min_income", "max_income", "rate_percent"],
        order_by="min_income asc",
    )
    if not brackets:
        raise ValidationError(
            f"TER Bracket Table: No brackets found for ter_code '{ter_code}'."
        )
    for row in brackets:
        min_income = flt(row.get("min_income") or 0)
        max_income = flt(row.get("max_income") or 0)
        rate = flt(row.get("rate_percent") or 0)
        # If max_income == 0, treat as infinity
        if monthly_income >= min_income and (max_income == 0 or monthly_income <= max_income):
            return rate
    raise ValidationError(
        f"TER Bracket Table: No bracket match for ter_code '{ter_code}' and monthly_income {monthly_income}."
    )

def is_auto_queue_salary_slip() -> bool:
    """
    Return True if salary slip should be processed via background job (auto_queue_salary_slip checked).
    """
    return bool(int(get_value("auto_queue_salary_slip", 0)))

def is_salary_slip_use_component_cache() -> bool:
    """
    Return True if salary slip should use component cache (salary_slip_use_component_cache checked).
    """
    return bool(int(get_value("salary_slip_use_component_cache", 0)))

# -- Existing BPJS/utility functions remain unchanged above --