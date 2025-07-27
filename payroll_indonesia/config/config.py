import frappe
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

def get_ter_code(tax_status: str) -> str | None:
    """
    Return TER code mapping for the given tax status.
    """
    settings = get_settings()
    for row in settings.get("ter_mapping_table", []):
        if (getattr(row, "tax_status", None) or row.get("tax_status")) == tax_status:
            return getattr(row, "ter_code", None) or row.get("ter_code")
    return None

def get_ter_rate(ter_code: str, monthly_income: float) -> float:
    """
    Return TER rate (%) for a given TER code and monthly income.
    """
    settings = get_settings()
    brackets = [
        row for row in settings.get("ter_bracket_table", [])
        if (getattr(row, "ter_code", None) or row.get("ter_code")) == ter_code
    ]
    for row in brackets:
        min_income = flt(getattr(row, "min_income", None) or row.get("min_income", 0))
        max_income = flt(getattr(row, "max_income", None) or row.get("max_income", 0))
        rate = flt(getattr(row, "rate_percent", None) or row.get("rate_percent", 0))
        if monthly_income >= min_income and (max_income == 0 or monthly_income <= max_income):
            return rate
    return 0.0

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