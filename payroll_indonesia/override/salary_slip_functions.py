
from frappe.utils import flt, cint
from payroll_indonesia.constants import (
    BIAYA_JABATAN_PERCENT,
    BIAYA_JABATAN_MAX,
    MONTHS_PER_YEAR,
    TAX_DEDUCTION_EFFECT,
    TAX_OBJEK_EFFECT,
    NATURA_OBJEK_EFFECT,
)
from payroll_indonesia.override.salary_slip.tax_calculator import (
    calculate_december_pph,
    calculate_monthly_pph_progressive,
    categorize_components_by_tax_effect,
    get_ptkp_value,
    get_tax_status,
    get_slip_year_month,
    get_ytd_totals,
    is_december_calculation,
)



























































































































def after_save(doc, method=None):
    """
    After save hook for Salary Slip.
    
    Args:
        doc: Salary Slip document
        method: Method name (not used)
    """
    try:
        # Skip if document is already processed
        if hasattr(doc, "flags") and getattr(doc.flags, "skip_indonesia_hooks", False):
            return
        
        # Only process if Indonesia payroll is enabled
        if cint(getattr(doc, "calculate_indonesia_tax", 0)) != 1:
            return
        
        logger.debug(f"Completed after_save for slip {getattr(doc, 'name', 'unknown')}")
    
    except Exception as e:
        logger.exception(f"Error in after_save: {str(e)}")


def _update_deduction_amounts(doc):
    """
    Update deduction amounts based on tax effect types.
    
    Args:
        doc: Salary Slip document
    """
    try:
        # Get categorized components
        tax_components = categorize_components_by_tax_effect(doc)
        
        # Get BPJS details
        bpjs = get_bpjs_deductions(doc)
        
        # Update BPJS fields
        if hasattr(doc, "total_bpjs"):
            doc.total_bpjs = bpjs["total_employee"]
        
        if hasattr(doc, "bpjs_jht_employee"):
            doc.bpjs_jht_employee = bpjs["jht_employee"]
        
        if hasattr(doc, "bpjs_jp_employee"):
            doc.bpjs_jp_employee = bpjs["jp_employee"]
        
        if hasattr(doc, "bpjs_jkn_employee"):
            doc.bpjs_jkn_employee = bpjs["jkn_employee"]
        
        # Update tax deduction fields
        if hasattr(doc, "total_tax_deductions"):
            doc.total_tax_deductions = tax_components["totals"].get(TAX_DEDUCTION_EFFECT, 0)
        
        # Update PPh 21
        pph21_details = get_component_details(doc, "PPh 21")
        if hasattr(doc, "pph21") and pph21_details["found"]:
            doc.pph21 = pph21_details["amount"]
        
        logger.debug(f"Updated deduction amounts for slip {getattr(doc, 'name', 'unknown')}")
    
    except Exception as e:
        logger.exception(f"Error updating deduction amounts: {str(e)}")


def _update_custom_fields(doc):







    """Update custom fields for reporting."""
    try:
        # Update taxable earnings
        if hasattr(doc, "taxable_earnings"):
            doc.taxable_earnings = calculate_taxable_earnings(doc)
        
        # Update gross pay in base currency
        if hasattr(doc, "base_gross_pay") and hasattr(doc, "gross_pay"):
            doc.base_gross_pay = doc.gross_pay
        
        # Update net pay in base currency
        if hasattr(doc, "base_net_pay") and hasattr(doc, "net_pay"):
            doc.base_net_pay = doc.net_pay
        
        # Update total deduction in base currency
        if hasattr(doc, "base_total_deduction") and hasattr(doc, "total_deduction"):
            doc.base_total_deduction = doc.total_deduction
        
        # Update year and month fields
        year, month = get_slip_year_month(doc)
        
        if hasattr(doc, "salary_year"):
            doc.salary_year = year
        
        if hasattr(doc, "salary_month"):
            doc.salary_month = month
        
        # Update YTD fields from tax calculation
        if hasattr(doc, "ytd_gross") and not doc.ytd_gross:
            ytd = get_ytd_totals(doc)
            if hasattr(doc, "ytd_gross"):
                doc.ytd_gross = ytd.get("gross", 0)
            if hasattr(doc, "ytd_bpjs"):
                doc.ytd_bpjs = ytd.get("bpjs", 0)
            if hasattr(doc, "ytd_pph21"):
                doc.ytd_pph21 = ytd.get("pph21", 0)
        
        # Update December flag
        if hasattr(doc, "is_december_slip"):
            doc.is_december_slip = 1 if is_december_calculation(doc) else 0
        
        # Update koreksi_pph21 for December
        if is_december_calculation(doc):
            # Use correction amount from December tax calculation
            _, details = calculate_december_pph(doc)
            doc.koreksi_pph21 = flt(details.get("correction_amount", 0))

        # Update is_final_gabung_suami
        if hasattr(doc, "is_final_gabung_suami"):
            employee_doc = frappe.get_doc("Employee", doc.employee)
            doc.is_final_gabung_suami = cint(getattr(employee_doc, "npwp_gabung_suami", 0))

        # Update netto and related tax fields
        if (
            hasattr(doc, "netto")
            or hasattr(doc, "biaya_jabatan")
            or hasattr(doc, "annual_taxable_income")
            or hasattr(doc, "annual_pkp")
        ):
            tax_components = categorize_components_by_tax_effect(doc)

            gross_income = tax_components["totals"].get(TAX_OBJEK_EFFECT, 0)
            gross_income += tax_components["totals"].get(NATURA_OBJEK_EFFECT, 0)
            deductions = tax_components["totals"].get(TAX_DEDUCTION_EFFECT, 0)

            netto = gross_income - deductions

            if hasattr(doc, "netto"):
                doc.netto = netto

            if hasattr(doc, "biaya_jabatan"):
                doc.biaya_jabatan = min(
                    netto * BIAYA_JABATAN_PERCENT / 100, BIAYA_JABATAN_MAX
                )

            annual_taxable = gross_income * MONTHS_PER_YEAR

            if hasattr(doc, "annual_taxable_income"):
                doc.annual_taxable_income = annual_taxable

            if hasattr(doc, "annual_pkp"):
                annual_ptkp = get_ptkp_value(get_tax_status(doc))
                annual_deductions = deductions * MONTHS_PER_YEAR
                annual_biaya_jabatan = min(
                    annual_taxable * BIAYA_JABATAN_PERCENT / 100,
                    BIAYA_JABATAN_MAX * MONTHS_PER_YEAR,
                )
                doc.annual_pkp = max(
                    0, annual_taxable - annual_biaya_jabatan - annual_deductions - annual_ptkp
                )

        logger.debug(f"Updated custom fields for slip {getattr(doc, 'name', 'unknown')}")
    
    except Exception as e:
        logger.exception(f"Error updating custom fields: {str(e)}")
