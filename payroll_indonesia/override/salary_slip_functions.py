





































































































































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
            # Use the difference between calculated tax and normal monthly tax
            normal_tax, _ = calculate_monthly_pph_progressive(doc)
            december_tax, _ = calculate_december_pph(doc)
            doc.koreksi_pph21 = december_tax - normal_tax

        # Update is_final_gabung_suami
        if hasattr(doc, "is_final_gabung_suami"):
            employee_doc = frappe.get_doc("Employee", doc.employee)
            doc.is_final_gabung_suami = cint(getattr(employee_doc, "npwp_gabung_suami", 0))

        # Update netto field
        if hasattr(doc, "netto"):
            tax_components = categorize_components_by_tax_effect(doc)
            gross_income = tax_components["totals"].get(TAX_OBJEK_EFFECT, 0)
            deductions = tax_components["totals"].get(TAX_DEDUCTION_EFFECT, 0)
            doc.netto = gross_income - deductions

        logger.debug(f"Updated custom fields for slip {getattr(doc, 'name', 'unknown')}")
    
    except Exception as e:
        logger.exception(f"Error updating custom fields: {str(e)}")
