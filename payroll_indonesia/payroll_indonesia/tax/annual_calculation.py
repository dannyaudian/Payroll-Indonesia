# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-17 06:19:41 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, cint
from datetime import datetime
from payroll_indonesia.payroll_indonesia.utils import get_ptkp_settings

# Import necessary functions for TER mapping
from payroll_indonesia.override.salary_slip.ter_calculator import map_ptkp_to_ter_category


def hitung_pph_tahunan(employee, tahun_pajak, salary_slip=None):
    """
    Calculate annual progressive income tax (Pasal 17) for December correction
    with improved validation and error handling

    Args:
        employee (str): Employee ID
        tahun_pajak (int): Tax year
        salary_slip (obj, optional): Salary slip document

    Returns:
        dict: Annual tax calculation results
    """
    try:
        # Validate parameters
        if not employee:
            frappe.throw(
                _("Employee ID is required for annual tax calculation"),
                title=_("Missing Parameter"),
            )

        if not tahun_pajak:
            tahun_pajak = datetime.now().year
            frappe.msgprint(
                _("Tax year not specified, using current year ({0})").format(tahun_pajak),
                indicator="blue",
            )

        # Validate employee exists
        if not frappe.db.exists("Employee", employee):
            frappe.throw(_("Employee {0} not found").format(employee), title=_("Invalid Employee"))

        # Get annual income from salary slips
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters={
                "employee": employee,
                "docstatus": 1,
                "posting_date": ["between", [f"{tahun_pajak}-01-01", f"{tahun_pajak}-12-31"]],
            },
            fields=["name", "gross_pay", "total_deduction", "posting_date"],
        )

        if not salary_slips:
            frappe.msgprint(
                _("No approved salary slips found for employee {0} in tax year {1}").format(
                    employee, tahun_pajak
                ),
                indicator="orange",
            )
            return {
                "annual_income": 0,
                "annual_net": 0,
                "biaya_jabatan": 0,
                "bpjs_total": 0,
                "ptkp": 0,
                "pkp": 0,
                "annual_tax": 0,
                "already_paid": 0,
                "correction": 0,
                "slip_details": [],
                "tax_details": [],
                "status_pajak": "TK0",
                "ter_category": "",
            }

        # Calculate totals and get slips data
        total_gross = 0
        total_deduction = 0
        total_tax_paid = 0
        slip_details = []

        for slip in salary_slips:
            try:
                slip_doc = frappe.get_doc("Salary Slip", slip.name)
                slip_gross = flt(slip.gross_pay)
                slip_deduction = flt(slip.total_deduction)

                # Validate data
                if slip_gross < 0:
                    frappe.log_error(
                        "Negative gross pay {0} found in salary slip {1}".format(
                            slip_gross, slip.name
                        ),
                        "Annual Calculation Warning",
                    )
                    slip_gross = 0

                total_gross += slip_gross
                total_deduction += slip_deduction

                # Get PPh 21 from deductions
                tax_paid = 0
                is_using_ter = 0
                ter_rate = 0
                ter_category = ""  # Add TER category tracking

                # Check if deductions attribute exists
                if hasattr(slip_doc, "deductions"):
                    for deduction in slip_doc.deductions:
                        if deduction.salary_component == "PPh 21":
                            tax_paid = flt(deduction.amount)
                            break
                else:
                    frappe.log_error(
                        "Salary slip {0} has no deductions attribute".format(slip.name),
                        "Annual Calculation Warning",
                    )

                total_tax_paid += tax_paid

                # Get TER information if available
                if hasattr(slip_doc, "is_using_ter"):
                    is_using_ter = cint(slip_doc.is_using_ter)

                if hasattr(slip_doc, "ter_rate"):
                    ter_rate = flt(slip_doc.ter_rate)

                # Get TER category if available
                if hasattr(slip_doc, "ter_category"):
                    ter_category = slip_doc.ter_category

                # Store details for reporting
                slip_details.append(
                    {
                        "name": slip.name,
                        "date": slip.posting_date,
                        "gross": slip_gross,
                        "tax": tax_paid,
                        "using_ter": is_using_ter,
                        "ter_rate": ter_rate if is_using_ter else 0,
                        "ter_category": ter_category if is_using_ter else "",
                        "is_december_override": getattr(slip_doc, "is_december_override", 0),
                    }
                )
            except Exception as e:
                # Non-critical error - processing can continue with other slips
                frappe.log_error(
                    "Error processing salary slip {0}: {1}".format(slip.name, str(e)),
                    "Annual Calculation Warning",
                )
                continue

        # Get employee document
        try:
            employee_doc = frappe.get_doc("Employee", employee)
        except Exception as e:
            # Critical error - cannot continue without employee
            frappe.log_error(
                "Error retrieving employee {0} information: {1}".format(employee, str(e)),
                "Annual Tax Calculation Error",
            )
            frappe.throw(
                _("Error retrieving employee information: {0}").format(str(e)),
                title=_("Employee Access Error"),
            )

        # Calculate biaya jabatan (job allowance) - max 6M per year
        biaya_jabatan = min(total_gross * 0.05, 6000000)

        # Calculate annual BPJS
        annual_bpjs = 0
        for slip in salary_slips:
            try:
                slip_doc = frappe.get_doc("Salary Slip", slip.name)
                bpjs_components = [
                    "BPJS JHT Employee",
                    "BPJS JP Employee",
                    "BPJS Kesehatan Employee",
                ]

                if hasattr(slip_doc, "deductions"):
                    for component in bpjs_components:
                        for deduction in slip_doc.deductions:
                            if deduction.salary_component == component:
                                annual_bpjs += flt(deduction.amount)
                                break
            except Exception as e:
                # Non-critical error - processing can continue with other slips
                frappe.log_error(
                    "Error calculating BPJS for slip {0}: {1}".format(slip.name, str(e)),
                    "Annual BPJS Calculation Warning",
                )
                continue

        # Get net annual - for annual calculation we need to deduct biaya jabatan and BPJS
        net_annual = total_gross - biaya_jabatan - annual_bpjs

        # Get employee details with validation
        status_pajak = "TK0"  # Default to TK0
        if hasattr(employee_doc, "status_pajak") and employee_doc.status_pajak:
            status_pajak = employee_doc.status_pajak
        else:
            # Non-critical warning - default will be used
            frappe.log_error(
                "Tax status not set for employee {0}, using default (TK0)".format(employee),
                "Tax Status Warning",
            )
            frappe.msgprint(
                _("Tax status not set for employee {0}, using default (TK0)").format(employee),
                indicator="orange",
            )

        # Map PTKP status to TER category for reference
        ter_category = ""
        try:
            ter_category = map_ptkp_to_ter_category(status_pajak)
        except Exception as e:
            # Non-critical error - just for reference
            frappe.log_error(
                "Error mapping PTKP status {0} to TER category: {1}".format(status_pajak, str(e)),
                "TER Mapping Warning",
            )

        # Calculate PTKP (Annual non-taxable income)
        try:
            ptkp = calculate_ptkp(status_pajak)
        except Exception as e:
            # Critical error - cannot continue without PTKP
            frappe.log_error(
                "Error calculating PTKP for status {0}: {1}".format(status_pajak, str(e)),
                "PTKP Calculation Error",
            )
            frappe.throw(
                _("Error calculating PTKP: {0}").format(str(e)), title=_("PTKP Calculation Failed")
            )

        # Calculate PKP (taxable income)
        pkp = max(0, net_annual - ptkp)

        # Calculate progressive tax (Pasal 17)
        try:
            annual_tax, tax_details = calculate_progressive_tax(pkp)
        except Exception as e:
            # Critical error - cannot continue without tax calculation
            frappe.log_error(
                "Error calculating progressive tax for PKP {0}: {1}".format(pkp, str(e)),
                "Progressive Tax Calculation Error",
            )
            frappe.throw(
                _("Error calculating progressive tax: {0}").format(str(e)),
                title=_("Tax Calculation Failed"),
            )

        # Calculate correction needed
        correction = annual_tax - total_tax_paid

        # Determine if this is a December run based on salary_slip parameter or any slip with is_december_override
        is_december_override = 0
        if salary_slip:
            is_december_override = getattr(salary_slip, "is_december_override", 0)
        else:
            # Check if any of the salary slips has is_december_override=1
            for slip_detail in slip_details:
                if slip_detail.get("is_december_override"):
                    is_december_override = 1
                    break

        # Return the results with TER category and is_december_override flag
        return {
            "annual_income": total_gross,
            "annual_net": net_annual,
            "biaya_jabatan": biaya_jabatan,
            "bpjs_total": annual_bpjs,
            "ptkp": ptkp,
            "pkp": pkp,
            "annual_tax": annual_tax,
            "already_paid": total_tax_paid,
            "correction": correction,
            "slip_details": slip_details,
            "tax_details": tax_details,
            "status_pajak": status_pajak,
            "ter_category": ter_category,
            "is_december_override": is_december_override,
        }

    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise

        # Critical error - log and re-raise
        frappe.log_error(
            "Error in annual tax calculation for employee {0}, year {1}: {2}".format(
                employee, tahun_pajak, str(e)
            ),
            "Annual Tax Calculation Error",
        )
        frappe.throw(
            _("Error in annual tax calculation: {0}").format(str(e)), title=_("Calculation Failed")
        )


def calculate_ptkp(status_pajak):
    """
    Calculate PTKP (Annual non-taxable income) based on tax status

    Args:
        status_pajak (str): Tax status code (e.g., TK0, K1)

    Returns:
        float: PTKP amount
    """
    try:
        # Get PTKP settings
        ptkp_settings = get_ptkp_settings()

        # Check if status_pajak directly exists in settings
        if status_pajak in ptkp_settings:
            return flt(ptkp_settings[status_pajak])

        # If not found, try to match prefix (TK, K, etc.)
        prefix = status_pajak[:2] if len(status_pajak) >= 2 else status_pajak

        # Get default values from settings based on prefix
        for key, value in ptkp_settings.items():
            if key.startswith(prefix):
                # Non-critical warning - fallback used
                frappe.log_error(
                    "PTKP status {0} not found, using closest match {1}".format(status_pajak, key),
                    "PTKP Mapping Warning",
                )
                frappe.msgprint(
                    _("PTKP status {0} not found, using closest match {1}").format(
                        status_pajak, key
                    ),
                    indicator="orange",
                )
                return flt(value)

        # Default values if not found
        default_values = {"TK": 54000000, "K": 58500000, "HB": 112500000}  # TK/0  # K/0  # HB/0

        if prefix in default_values:
            # Non-critical warning - default used
            frappe.log_error(
                "PTKP status {0} not found in settings, using default value {1}".format(
                    status_pajak, default_values[prefix]
                ),
                "PTKP Default Used",
            )
            frappe.msgprint(
                _("PTKP status {0} not found in settings. Using default value.").format(
                    status_pajak
                ),
                indicator="orange",
            )
            return flt(default_values[prefix])

        # Last resort - use TK0 default
        frappe.log_error(
            "Could not find PTKP match for {0}, using TK0 default (54,000,000)".format(
                status_pajak
            ),
            "PTKP Default Used",
        )
        frappe.msgprint(
            _("Could not find PTKP match for {0}. Using TK0 default.").format(status_pajak),
            indicator="red",
        )
        return 54000000

    except Exception as e:
        # Critical error - PTKP is required
        frappe.log_error(
            "Error calculating PTKP for status {0}: {1}".format(status_pajak, str(e)),
            "PTKP Calculation Error",
        )
        frappe.throw(
            _("Error calculating PTKP: {0}").format(str(e)), title=_("PTKP Calculation Failed")
        )


def calculate_progressive_tax(pkp):
    """
    Calculate progressive income tax (Pasal 17)

    Args:
        pkp (float): Taxable income (Penghasilan Kena Pajak)

    Returns:
        tuple: (total tax, list of tax details by bracket)
    """
    try:
        # Progressive tax brackets according to UU HPP
        brackets = [
            {"from": 0, "to": 60000000, "rate": 0.05},
            {"from": 60000000, "to": 250000000, "rate": 0.15},
            {"from": 250000000, "to": 500000000, "rate": 0.25},
            {"from": 500000000, "to": 5000000000, "rate": 0.30},
            {"from": 5000000000, "to": float("inf"), "rate": 0.35},
        ]

        remaining_pkp = pkp
        total_tax = 0
        tax_details = []

        for bracket in brackets:
            bracket_from = flt(bracket["from"])
            bracket_to = flt(bracket["to"])
            bracket_rate = flt(bracket["rate"])

            if remaining_pkp <= 0:
                break

            # Calculate taxable amount in this bracket
            if bracket_to == float("inf"):
                taxable = remaining_pkp
            else:
                taxable = min(remaining_pkp, bracket_to - bracket_from)

            # Calculate tax for this bracket
            tax = taxable * bracket_rate

            # Add to total
            total_tax += tax

            # Add to details
            tax_details.append(
                {
                    "from": bracket_from,
                    "to": bracket_to,
                    "rate": bracket_rate,
                    "taxable": taxable,
                    "tax": tax,
                }
            )

            # Reduce remaining PKP
            remaining_pkp -= taxable

        return total_tax, tax_details

    except Exception as e:
        # Critical error - tax calculation is required
        frappe.log_error(
            "Error calculating progressive tax for PKP {0}: {1}".format(pkp, str(e)),
            "Progressive Tax Calculation Error",
        )
        frappe.throw(
            _("Error calculating progressive tax: {0}").format(str(e)),
            title=_("Tax Calculation Failed"),
        )


def generate_december_correction_note(calc_result, salary_slip=None):
    """
    Generate detailed note for December correction with improved validation

    Args:
        calc_result (dict): Result from hitung_pph_tahunan function
        salary_slip (obj, optional): Salary slip document

    Returns:
        str: Formatted note for December correction
    """
    try:
        # Validate input
        if not calc_result or not isinstance(calc_result, dict):
            frappe.throw(_("Invalid calculation result provided"), title=_("Invalid Input"))

        # Check required keys
        required_keys = [
            "annual_income",
            "biaya_jabatan",
            "bpjs_total",
            "annual_net",
            "ptkp",
            "pkp",
            "tax_details",
            "annual_tax",
            "already_paid",
            "correction",
            "slip_details",
            "status_pajak",
            "ter_category",
        ]

        for key in required_keys:
            if key not in calc_result:
                # Non-critical error - continue with defaults
                frappe.log_error(
                    "Missing key {0} in calculation result".format(key),
                    "December Note Generation Warning",
                )

                # Initialize missing keys with 0 or empty string
                if key in ["tax_details", "slip_details"]:
                    calc_result[key] = []
                elif key in ["status_pajak", "ter_category"]:
                    calc_result[key] = ""
                else:
                    calc_result[key] = 0

        # Determine if this is a December run based on salary_slip parameter or calculation result
        is_december_override = 0
        if salary_slip:
            is_december_override = getattr(salary_slip, "is_december_override", 0)
        elif "is_december_override" in calc_result:
            is_december_override = calc_result["is_december_override"]

        # Build the note with December indication from is_december_override
        note_title = "=== Perhitungan PPh 21 Tahunan"
        if is_december_override:
            note_title += " (December Override)"
        note_title += " ==="

        note = [
            note_title,
            "Status Pajak: {0}{1}".format(
                calc_result["status_pajak"],
                " ({0})".format(calc_result["ter_category"]) if calc_result["ter_category"] else "",
            ),
            "Penghasilan Bruto Setahun: Rp {0:,.0f}".format(flt(calc_result["annual_income"])),
            "Biaya Jabatan: Rp {0:,.0f}".format(flt(calc_result["biaya_jabatan"])),
            "Total BPJS: Rp {0:,.0f}".format(flt(calc_result["bpjs_total"])),
            "Penghasilan Neto: Rp {0:,.0f}".format(flt(calc_result["annual_net"])),
            "PTKP: Rp {0:,.0f}".format(flt(calc_result["ptkp"])),
            "PKP: Rp {0:,.0f}".format(flt(calc_result["pkp"])),
            "",
            "Perhitungan Per Lapisan Pajak:",
        ]

        # Add tax bracket details
        tax_details = calc_result.get("tax_details", [])
        if tax_details and isinstance(tax_details, list):
            for i, bracket in enumerate(tax_details):
                from_amount = flt(bracket.get("from", 0))
                to_amount = flt(bracket.get("to", 0))
                rate = flt(bracket.get("rate", 0)) * 100
                taxable = flt(bracket.get("taxable", 0))
                tax = flt(bracket.get("tax", 0))

                # Format "to" amount for infinity
                to_text = "∞" if to_amount == float("inf") else f"{to_amount:,.0f}"

                note.append(f"Lapisan {i + 1}: Rp {from_amount:,.0f} - Rp {to_text} ({rate:.1f}%)")
                note.append(f"  PKP: Rp {taxable:,.0f} x {rate:.1f}% = Rp {tax:,.0f}")

        # Add summary
        note.extend(
            [
                "",
                f"PPh 21 Terutang Setahun: Rp {flt(calc_result['annual_tax']):,.0f}",
                f"PPh 21 Sudah Dipotong: Rp {flt(calc_result['already_paid']):,.0f}",
                f"Selisih PPh 21: Rp {flt(calc_result['correction']):,.0f}",
            ]
        )

        # Add details of slips using TER
        slip_details = calc_result.get("slip_details", [])
        if slip_details and isinstance(slip_details, list):
            # Filter slips that used TER
            ter_slips = [slip for slip in slip_details if slip.get("using_ter")]

            if ter_slips:
                note.append("\nRiwayat Perhitungan Dengan TER:")
                for slip in ter_slips:
                    slip_date = slip.get("date", "")
                    ter_rate = flt(slip.get("ter_rate", 0))
                    tax = flt(slip.get("tax", 0))
                    ter_category = slip.get("ter_category", "")
                    is_december = slip.get("is_december_override", 0)

                    ter_info = "Rate {0:.2f}%".format(ter_rate)
                    if ter_category:
                        ter_info = "{0}: {1}".format(ter_category, ter_info)
                    if is_december:
                        ter_info += " (December Override)"

                    note.append("- {0}: {1}, PPh 21: Rp {2:,.0f}".format(slip_date, ter_info, tax))

        return "\n".join(note)

    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise

        # Non-critical error - return basic note
        frappe.log_error(
            "Error generating December correction note: {0}".format(str(e)), "December Note Error"
        )
        # Return basic note to avoid breaking
        return "Error generating detailed note. Please check calculation results."
