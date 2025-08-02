import frappe
from frappe import ValidationError
from frappe.utils import flt

# Define all defaults in one place for better maintenance
DEFAULTS = {
    "SETTINGS_DOCTYPE": "Payroll Indonesia Settings",
    "SETTINGS_NAME": "Payroll Indonesia Settings",
    "BIAYA_JABATAN_RATE": 5.0,                # percent
    "BIAYA_JABATAN_CAP_YEARLY": 6_000_000.0,  # rupiah (6 million)
    "BPJS_KES_EMPLOYEE": 1.0,                 # percent
    "BPJS_KES_COMPANY": 4.0,                  # percent
    "BPJS_KES_CAP": 12_000_000.0,             # rupiah (12 million)
    "BPJS_JHT_EMPLOYEE": 2.0,                 # percent
    "BPJS_JHT_COMPANY": 3.7,                  # percent
    "BPJS_JHT_CAP": 9_077_600.0,              # rupiah
    "BPJS_JP_EMPLOYEE": 1.0,                  # percent
    "BPJS_JP_COMPANY": 2.0,                   # percent
    "BPJS_JP_CAP": 9_077_600.0,               # rupiah
    "BPJS_JKK_COMPANY": 0.24,                 # percent (risk level I)
    "BPJS_JKM_COMPANY": 0.3,                  # percent
}

# Logger for consistent logging
logger = frappe.logger("payroll_indonesia.config")

def settings_exist() -> bool:
    """
    Check if Payroll Indonesia Settings exists in the database.
    """
    return frappe.db.exists(DEFAULTS["SETTINGS_DOCTYPE"], DEFAULTS["SETTINGS_NAME"])

def get_settings():
    """
    Return cached Payroll Indonesia Settings document.
    Logs a warning if settings don't exist.
    """
    try:
        if settings_exist():
            return frappe.get_cached_doc(DEFAULTS["SETTINGS_DOCTYPE"], DEFAULTS["SETTINGS_NAME"])
        else:
            logger.warning(
                f"{DEFAULTS['SETTINGS_DOCTYPE']} not found. Using default values."
            )
            class DummySettings(dict):
                def get(self, key, default=None):
                    return default
            return DummySettings()
    except Exception as e:
        logger.warning(
            f"Error loading {DEFAULTS['SETTINGS_DOCTYPE']}: {str(e)}. Using default values."
        )
        class DummySettings(dict):
            def get(self, key, default=None):
                return default
        return DummySettings()

def get_value(fieldname: str, default=None):
    """
    Helper to fetch a field value from Payroll Indonesia Settings.
    """
    return get_settings().get(fieldname, default)

def get_numeric(fieldname: str, default_key: str = None) -> float:
    """
    Helper to fetch a numeric value from settings with proper fallback and logging.
    
    Args:
        fieldname: The field name in Payroll Indonesia Settings
        default_key: The key in DEFAULTS dictionary to use if setting is not found
        
    Returns:
        float: The numeric value from settings or default
    """
    value = get_value(fieldname)
    
    # Get the default value if provided
    default = DEFAULTS.get(default_key) if default_key else None
    
    # If value is None or empty and we have a default, log and return default
    if (value is None or value == "") and default is not None:
        logger.info(
            f"Field '{fieldname}' not found in {DEFAULTS['SETTINGS_DOCTYPE']}. Using default: {default}"
        )
        return float(default)
        
    # Return the found value as float
    return flt(value)

def get_bpjs_rate(fieldname: str) -> float:
    """
    Return BPJS rate (%) for the given fieldname.
    """
    default_key = fieldname.upper() if fieldname.upper() in DEFAULTS else None
    return get_numeric(fieldname, default_key)

def get_bpjs_cap(fieldname: str) -> float:
    """
    Return BPJS cap amount for the given fieldname.
    """
    default_key = fieldname.upper() if fieldname.upper() in DEFAULTS else None
    return get_numeric(fieldname, default_key)

def get_ptkp_amount_from_tax_status(tax_status: str) -> float:
    """
    Return PTKP amount for the given tax_status from PTKP Table.
    Uses field 'ptkp_amount' as per latest migration.
    """
    if not tax_status:
        logger.error("PTKP amount lookup: tax_status is empty.")
        raise ValidationError("PTKP amount lookup: tax_status is empty.")
        
    if not frappe.db.exists("PTKP Table", {"tax_status": tax_status}):
        logger.error(f"PTKP Table: tax_status '{tax_status}' not found.")
        raise ValidationError(f"PTKP Table: tax_status '{tax_status}' not found.")
        
    row = frappe.get_value(
        "PTKP Table",
        {"tax_status": tax_status},
        ["ptkp_amount"],
        as_dict=True,
    )
    
    if row and row.get("ptkp_amount") is not None:
        return flt(row["ptkp_amount"])
        
    logger.warning(f"PTKP Table: No ptkp_amount found for tax_status '{tax_status}'.")
    return 0.0

def get_ptkp_amount(employee_doc) -> float:
    """
    Return PTKP amount for employee_doc using field tax_status.
    """
    if hasattr(employee_doc, "tax_status"):
        tax_status = getattr(employee_doc, "tax_status")
    elif isinstance(employee_doc, dict):
        tax_status = employee_doc.get("tax_status")
    else:
        tax_status = None

    return get_ptkp_amount_from_tax_status(tax_status)

def get_ter_code(employee_doc) -> str | None:
    """
    Get TER code for employee from TER Mapping Table based on tax_status.
    Returns None if not found.
    """
    if hasattr(employee_doc, "tax_status"):
        tax_status = getattr(employee_doc, "tax_status")
    elif isinstance(employee_doc, dict):
        tax_status = employee_doc.get("tax_status")
    else:
        tax_status = None
        
    if not tax_status:
        logger.warning("TER code lookup: Employee tax_status is empty.")
        return None
        
    if not frappe.db.exists("TER Mapping Table", {"tax_status": tax_status}):
        logger.warning(f"TER Mapping Table: tax_status '{tax_status}' not found.")
        return None
        
    row = frappe.get_value(
        "TER Mapping Table",
        {"tax_status": tax_status},
        ["ter_code"],
        as_dict=True,
    )
    
    if row and "ter_code" in row:
        return row["ter_code"]
        
    logger.warning(f"TER Mapping Table: No ter_code found for tax_status '{tax_status}'.")
    return None

def get_ter_rate(ter_code: str, monthly_income: float) -> float:
    """
    Get TER rate from TER Bracket Table for given ter_code and monthly_income.
    Returns rate_percent (float), 0.0 if not found.
    """
    if not ter_code:
        logger.warning("TER rate lookup: ter_code is empty.")
        return 0.0
        
    brackets = frappe.get_all(
        "TER Bracket Table",
        filters={"ter_code": ter_code},
        fields=["min_income", "max_income", "rate_percent"],
        order_by="min_income asc",
    )
    
    if not brackets:
        error_msg = f"TER Bracket Table: No brackets found for ter_code '{ter_code}'."
        logger.error(error_msg)
        raise ValidationError(error_msg)
        
    for row in brackets:
        min_income = flt(row.get("min_income") or 0)
        max_income = flt(row.get("max_income") or 0)
        rate = flt(row.get("rate_percent") or 0)
        # If max_income == 0, treat as infinity
        if monthly_income >= min_income and (max_income == 0 or monthly_income <= max_income):
            return rate
            
    error_msg = f"TER Bracket Table: No bracket match for ter_code '{ter_code}' and monthly_income {monthly_income}."
    logger.error(error_msg)
    raise ValidationError(error_msg)
    
def get_biaya_jabatan_rate() -> float:
    """
    Persentase biaya jabatan (%).
    Bisa diganti di DocType 'Payroll Indonesia Settings'
    field biaya_jabatan_rate.
    """
    return get_numeric("biaya_jabatan_rate", "BIAYA_JABATAN_RATE")

def get_biaya_jabatan_cap_yearly() -> float:
    """
    Batas maksimum biaya jabatan setahun (Rp).
    Disimpan di field biaya_jabatan_cap_yearly.
    """
    return get_numeric("biaya_jabatan_cap_yearly", "BIAYA_JABATAN_CAP_YEARLY")

def get_biaya_jabatan_cap_monthly() -> float:
    """Hitung cap per bulan = cap tahunan / 12."""
    return get_biaya_jabatan_cap_yearly() / 12.0

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