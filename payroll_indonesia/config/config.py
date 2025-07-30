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

def get_ptkp_amount(tax_status: str) -> float:
    """
    Return PTKP amount for the given tax status.
    """
    settings = get_settings()
    for row in settings.get("ptkp_table", []):
        if (getattr(row, "tax_status", None) or row.get("tax_status")) == tax_status:
            return flt(getattr(row, "ptkp_amount", None) or row.get("ptkp_amount"))
    return 0.0

def get_ter_code(employee) -> str:
    """Return TER code based on employee tax status."""
    tax_status = None
    if hasattr(employee, "tax_status"):
        tax_status = getattr(employee, "tax_status")
    elif isinstance(employee, dict):
        tax_status = employee.get("tax_status")
    if not tax_status:
        tax_status = "TK/0"
    return tax_status

def get_ter_rate(ter_code: str, monthly_income: float) -> float:
    """Return TER rate from ``PPh 21 TER Table``."""
    brackets = frappe.get_all(
        "PPh 21 TER Table",
        filters={"ter_code": ter_code},
        fields=["min_income", "max_income", "rate_percent"],
        order_by="min_income asc",
    )
    for row in brackets:
        min_income = flt(row.get("min_income") or 0)
        max_income = flt(row.get("max_income") or 0)
        rate = flt(row.get("rate_percent") or 0)
        if monthly_income >= min_income and (max_income == 0 or monthly_income <= max_income):
            return rate
    frappe.throw(
        f"No TER bracket found for code {ter_code} and income {monthly_income}",
        exc=ValidationError,
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
