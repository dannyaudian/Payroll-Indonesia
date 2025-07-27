import frappe
from frappe.utils import flt

SETTINGS_DOCTYPE = "Payroll Indonesia Settings"
SETTINGS_NAME = "Payroll Indonesia Settings"


def get_settings():
    """Return cached Payroll Indonesia Settings document."""
    return frappe.get_cached_doc(SETTINGS_DOCTYPE, SETTINGS_NAME)


def get_value(fieldname: str, default=None):
    """Helper to fetch a field value from Payroll Indonesia Settings."""
    return get_settings().get(fieldname, default)


def get_bpjs_rate(fieldname: str) -> float:
    """Return BPJS rate (%) for the given fieldname."""
    return flt(get_value(fieldname))


def get_bpjs_cap(fieldname: str) -> float:
    """Return BPJS cap amount for the given fieldname."""
    return flt(get_value(fieldname))


def get_ptkp_amount(tax_status: str) -> float:
    """Return PTKP amount for the given tax status."""
    settings = get_settings()
    for row in settings.get("ptkp_table", []):
        if row.tax_status == tax_status:
            return flt(row.ptkp_amount)
    return 0.0


def get_ter_code(tax_status: str) -> str | None:
    """Return TER code mapping for the given tax status."""
    settings = get_settings()
    for row in settings.get("ter_mapping_table", []):
        if row.tax_status == tax_status:
            return row.ter_code
    return None


def get_ter_rate(ter_code: str, monthly_income: float) -> float:
    """Return TER rate (%) for a given TER code and monthly income."""
    settings = get_settings()
    brackets = [b for b in settings.get("ter_bracket_table", []) if b.ter_code == ter_code]
    for row in brackets:
        if monthly_income >= row.min_income and (
            row.max_income == 0 or monthly_income <= row.max_income
        ):
            return flt(row.rate_percent)
    return 0.0
