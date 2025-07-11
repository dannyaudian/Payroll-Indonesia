# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Functions for Salary Slip customization for Indonesian payroll.

These functions handle component updates, calculations, and post-submit operations.
"""

from typing import Dict, List, Optional, Any, Union, Tuple

import frappe
import logging
from frappe import _
from frappe.utils import flt, cint, getdate

from payroll_indonesia.config.config import get_live_config
from payroll_indonesia.payroll_indonesia import utils as pi_utils
from payroll_indonesia.payroll_indonesia.utils import (
    get_ptkp_to_ter_mapping,
    get_status_pajak,
)
from payroll_indonesia.constants import BIAYA_JABATAN_PERCENT, BIAYA_JABATAN_MAX
from payroll_indonesia.override.salary_slip.tax_calculator import (
    calculate_monthly_pph_progressive,
    calculate_december_pph,
    calculate_monthly_pph_with_ter,
)

logger = logging.getLogger(__name__)

calc_bpjs = pi_utils.calculate_bpjs

EMPLOYER_COMPONENTS = (
    "BPJS Kesehatan Employer",
    "BPJS JHT Employer",
    "BPJS JP Employer",
    "BPJS JKK",
    "BPJS JKM",
)

__all__ = [
    "enqueue_tax_summary_update",
    "update_tax_summary",
    "update_employee_history",
    "update_component_amount",
    "salary_slip_post_submit",
    "initialize_fields",
]


def initialize_fields(doc, method: Optional[str] = None) -> None:
    defaults = {
        "biaya_jabatan": 0,
        "netto": 0,
        "total_bpjs": 0,
        "is_using_ter": 0,
        "ter_rate": 0,
        "koreksi_pph21": 0,
        "ytd_gross_pay": 0,
        "ytd_bpjs_deductions": 0,
        "kesehatan_employee": 0,
        "jht_employee": 0,
        "jp_employee": 0,
        "pph21": 0,
    }

    for field, default in defaults.items():
        if not hasattr(doc, field) or getattr(doc, field) is None:
            setattr(doc, field, default)
            logger.debug(f"Initialized field {field}={default} for {doc.name}")


def update_component_amount(doc, method: Optional[str] = None) -> None:
    logger.debug(f"Updating component amounts for Salary Slip {doc.name}")

    initialize_fields(doc)

    config = get_live_config()
    bpjs_config = config.get("bpjs", {})

    if not doc.gross_pay:
        doc.gross_pay = _calculate_gross_pay(doc)
        logger.debug(f"Calculated gross pay: {doc.gross_pay}")

    settings = frappe.get_cached_doc("Payroll Indonesia Settings")
    status_raw = get_status_pajak(doc)
    mapping = get_ptkp_to_ter_mapping()
    ter_category = mapping.get(status_raw, "")
    is_ter_employee = bool(ter_category)

    logger.warning(
        "PPh21 route — slip=%s | status=%s | ter_cat=%s | is_ter=%s | use_ter=%s",
        doc.name,
        status_raw,
        ter_category,
        is_ter_employee,
        settings.use_ter,
    )

    logger.info(
        "TER debugging - settings.use_ter: %s, settings.tax_calculation_method: %s, "
        "status_pajak: %s, is_ter_employee: %s",
        settings.use_ter,
        settings.tax_calculation_method,
        status_raw,
        is_ter_employee,
    )

    try:
        bpjs_components = _calculate_bpjs_components(doc, bpjs_config)
        _update_bpjs_fields(doc, bpjs_components)

        _update_deduction_amounts(doc, bpjs_components, bpjs_config)

        if settings.tax_calculation_method == "TER" and settings.use_ter and is_ter_employee:
            doc.is_using_ter = 1
            result = calculate_monthly_pph_with_ter(
                ter_category=ter_category,
                gross_pay=doc.gross_pay,
                slip=doc,
            )
            tax_amount = result.get("monthly_tax", 0.0)
            logger.info(f"TER method applied for {doc.name} - tax: {tax_amount}")
        else:
            doc.is_using_ter = 0
            if getattr(doc, "is_december_override", 0):
                result = calculate_december_pph(doc)
                tax_amount = result.get("correction", 0.0)
                logger.info(f"December correction applied for {doc.name} - tax: {tax_amount}")
            else:
                result = calculate_monthly_pph_progressive(doc)
                tax_amount = result.get("monthly_tax", 0.0)
                logger.info(f"Progressive method applied for {doc.name} - tax: {tax_amount}")

        _update_component_amount(doc, "PPh 21", tax_amount)
        doc.pph21 = tax_amount

        biaya_jabatan = min(doc.gross_pay * (BIAYA_JABATAN_PERCENT / 100), BIAYA_JABATAN_MAX)
        doc.biaya_jabatan = biaya_jabatan
        doc.netto = doc.gross_pay - biaya_jabatan - (doc.total_bpjs or 0)

        _update_ytd_values(doc)
        _set_payroll_note(doc)

    except Exception as e:
        logger.exception(f"Error updating component amounts for {doc.name}: {e}")

    update_tax_summary(doc.name)
    try:
        doc.calculate_totals()
        logger.debug(f"Component update completed for Salary Slip {doc.name}")
    except Exception as e:
        logger.exception(f"Error calculating totals for {doc.name}: {e}")


def _calculate_gross_pay(doc) -> float:
    total = 0.0

    if hasattr(doc, "earnings"):
        for earning in doc.earnings:
            total += flt(earning.amount)

    return total


def _calculate_bpjs_components(doc, bpjs_config: Dict) -> Dict[str, float]:
    base_salary = flt(doc.gross_pay) or 0

    kesehatan_max = flt(bpjs_config.get("kesehatan_max_salary", 12000000))
    jp_max = flt(bpjs_config.get("jp_max_salary", 9077600))

    kesehatan_employee = calc_bpjs(
        base_salary, bpjs_config.get("kesehatan_employee_percent", 1.0), max_salary=kesehatan_max
    )

    jht_employee = calc_bpjs(base_salary, bpjs_config.get("jht_employee_percent", 2.0))

    jp_employee = calc_bpjs(
        base_salary, bpjs_config.get("jp_employee_percent", 1.0), max_salary=jp_max
    )

    kesehatan_employer = calc_bpjs(
        base_salary, bpjs_config.get("kesehatan_employer_percent", 4.0), max_salary=kesehatan_max
    )

    jht_employer = calc_bpjs(base_salary, bpjs_config.get("jht_employer_percent", 3.7))

    jp_employer = calc_bpjs(
        base_salary, bpjs_config.get("jp_employer_percent", 2.0), max_salary=jp_max
    )

    jkk = calc_bpjs(base_salary, bpjs_config.get("jkk_percent", 0.24))
    jkm = calc_bpjs(base_salary, bpjs_config.get("jkm_percent", 0.3))

    total_employee = kesehatan_employee + jht_employee + jp_employee
    total_employer = kesehatan_employer + jht_employer + jp_employer + jkk + jkm

    return {
        "kesehatan_employee": kesehatan_employee,
        "jht_employee": jht_employee,
        "jp_employee": jp_employee,
        "kesehatan_employer": kesehatan_employer,
        "jht_employer": jht_employer,
        "jp_employer": jp_employer,
        "jkk": jkk,
        "jkm": jkm,
        "total_employee": total_employee,
        "total_employer": total_employer,
    }


def _update_bpjs_fields(doc, components: Dict[str, float]) -> None:
    doc.kesehatan_employee = components.get("kesehatan_employee", 0)
    doc.jht_employee = components.get("jht_employee", 0)
    doc.jp_employee = components.get("jp_employee", 0)
    doc.total_bpjs = components.get("total_employee", 0)

    logger.debug(f"Updated BPJS fields for {doc.name}: total_bpjs={doc.total_bpjs}")


def _update_deduction_amounts(doc, components: Dict[str, float], bpjs_config: Dict) -> None:
    if not hasattr(doc, "deductions"):
        logger.warning(f"No deductions found in {doc.name}")
        return

    for deduction in doc.deductions:
        component_name = deduction.salary_component

        if component_name == "BPJS Kesehatan Employee":
            deduction.amount = components.get("kesehatan_employee", 0)
            logger.debug(f"Updated BPJS Kesehatan Employee: {deduction.amount}")

        elif component_name == "BPJS JHT Employee":
            deduction.amount = components.get("jht_employee", 0)
            logger.debug(f"Updated BPJS JHT Employee: {deduction.amount}")

        elif component_name == "BPJS JP Employee":
            deduction.amount = components.get("jp_employee", 0)
            logger.debug(f"Updated BPJS JP Employee: {deduction.amount}")

        elif component_name == "BPJS Kesehatan Employer":
            deduction.amount = components.get("kesehatan_employer", 0)
        elif component_name == "BPJS JHT Employer":
            deduction.amount = components.get("jht_employer", 0)
        elif component_name == "BPJS JP Employer":
            deduction.amount = components.get("jp_employer", 0)
        elif component_name == "BPJS JKK":
            deduction.amount = components.get("jkk", 0)
        elif component_name == "BPJS JKM":
            deduction.amount = components.get("jkm", 0)


def _update_ytd_values(doc) -> None:
    try:
        if not doc.employee or not doc.posting_date:
            return

        year = getdate(doc.posting_date).year

        ytd_data = frappe.db.sql(
            """
            SELECT 
                SUM(gross_pay) as gross_pay,
                SUM(total_bpjs) as total_bpjs
            FROM `tabSalary Slip`
            WHERE docstatus = 1
              AND employee = %s
              AND YEAR(posting_date) = %s
              AND name != %s
            """,
            (doc.employee, year, doc.name),
            as_dict=1,
        )

        if ytd_data and len(ytd_data) > 0:
            doc.ytd_gross_pay = flt(ytd_data[0].gross_pay) or 0
            doc.ytd_bpjs_deductions = flt(ytd_data[0].total_bpjs) or 0

            logger.debug(
                f"Updated YTD values for {doc.name}: "
                f"ytd_gross={doc.ytd_gross_pay}, ytd_bpjs={doc.ytd_bpjs_deductions}"
            )

    except Exception as e:
        logger.exception(f"Error updating YTD values for {doc.name}: {e}")


def _set_payroll_note(doc) -> None:
    notes = []

    if getattr(doc, "is_using_ter", 0):
        notes.append(f"Perhitungan pajak menggunakan metode TER ({getattr(doc, 'ter_rate', 0)}%)")

    if getattr(doc, "is_december_override", 0):
        notes.append("Slip ini menggunakan perhitungan koreksi pajak akhir tahun (Desember)")

    if notes:
        doc.payroll_note = "\n".join(notes)
        logger.debug(f"Set payroll note for {doc.name}")


def calculate_employer_contributions(doc) -> Dict[str, float]:
    return {}


def store_employer_contributions(doc, contributions: Dict[str, float]) -> None:
    return None


def salary_slip_post_submit(doc, method: Optional[str] = None) -> None:
    logger.debug(f"Processing post-submit for Salary Slip {doc.name}")

    try:
        initialize_fields(doc)

        enqueue_tax_summary_update(doc)

        logger.debug(f"Post-submit processing completed for Salary Slip {doc.name}")

    except Exception as e:
        logger.exception(f"Error in post-submit processing for {doc.name}: {e}")


def _update_component_amount(doc, component_name: str, amount: float) -> None:
    if not hasattr(doc, "deductions"):
        return

    for deduction in doc.deductions:
        if deduction.salary_component == component_name:
            deduction.amount = amount
            logger.debug(f"Updated {component_name}: {amount}")
            break


def _get_component_amount(doc, component_name: str) -> float:
    if not hasattr(doc, "deductions"):
        return 0.0

    for deduction in doc.deductions:
        if deduction.salary_component == component_name:
            return flt(deduction.amount)

    return 0.0


def _get_or_create_tax_row(slip) -> Tuple[Any, Any]:
    employee = slip.employee
    if hasattr(slip, "start_date") and slip.start_date:
        year = getdate(slip.start_date).year
    else:
        year = getdate(slip.posting_date).year

    filters = {"employee": employee, "year": year}

    summary_name = frappe.db.get_value("Employee Tax Summary", filters)

    if summary_name:
        summary = frappe.get_doc("Employee Tax Summary", summary_name)
    else:
        summary = frappe.new_doc("Employee Tax Summary")
        summary.employee = employee
        summary.year = year

    month = getattr(slip, "month", None)
    if not month and hasattr(slip, "start_date") and slip.start_date:
        month = getdate(slip.start_date).month

    if not month:
        month = getdate(slip.posting_date).month

    row = None
    for detail in summary.monthly_details:
        if detail.month == month:
            row = detail
            break

    if not row:
        row = summary.append(
            "monthly_details",
            {
                "month": month,
                "gross_pay": 0,
                "tax_amount": 0,
                "bpjs_deductions_employee": 0,
                "bpjs_deductions": 0,
                "other_deductions": 0,
            },
        )

    return row, summary


def enqueue_tax_summary_update(doc) -> None:
    try:
        if not doc or not hasattr(doc, "name") or not doc.name:
            logger.warning("Cannot enqueue tax update: Invalid document")
            return

        job_name = f"tax_summary_{doc.name}_{doc.docstatus}"

        frappe.enqueue(
            "payroll_indonesia.override.salary_slip_functions.update_tax_summary",
            queue="default",
            job_name=job_name,
            enqueue_after_commit=True,
            slip_name=doc.name,
        )

        logger.info(f"Enqueued tax summary update for {doc.name} (status: {doc.docstatus})")
        except Exception as e:
        logger.exception(f"Failed to enqueue tax summary update for {doc.name}: {str(e)}")
        try:
            update_tax_summary(doc.name)
        except Exception as fallback_error:
            logger.exception(f"Fallback tax update also failed for {doc.name}: {str(fallback_error)}")


def update_tax_summary(slip_name: str) -> None:
    def process_slip():
        slip = frappe.get_doc("Salary Slip", slip_name)
        
        if not slip.employee:
            logger.warning(f"Slip {slip_name} has no employee, skipping tax summary update")
            return

        logger.debug(f"Processing tax summary for {slip_name} (status: {slip.docstatus})")

        detail_row, summary = _get_or_create_tax_row(slip)

        if slip.docstatus == 1:
            _update_tax_detail_from_slip(detail_row, slip)
            detail_row.salary_slip = slip.name
        elif slip.docstatus == 2:
            _zero_tax_detail(detail_row)
            detail_row.salary_slip = ""

        _calculate_ytd_totals(summary)

        summary.flags.ignore_permissions = True
        summary.save()

        logger.info(
            f"Tax summary updated for {slip.employee} - Month {detail_row.month}/{summary.year}, "
            f"docstatus={slip.docstatus}"
            )

    try:
        from frappe.utils.background_jobs import retry

        retry(
            process_slip,
            max_retries=3,
            delay=5,
            backoff_factor=2,
            exceptions=(frappe.DoesNotExistError, frappe.LinkValidationError)
        )
    except ImportError:
        try:
            import time
            max_retries = 3
            delay = 5
            
            for attempt in range(max_retries):
                try:
                    process_slip()
                    break
                except (frappe.DoesNotExistError, frappe.LinkValidationError) as e:
                    if attempt < max_retries - 1:
                        wait_time = delay * (2 ** attempt)
                        logger.warning(
                            f"Retry {attempt+1}/{max_retries} for {slip_name} in {wait_time}s: {str(e)}"
                        )
                        time.sleep(wait_time)
                    else:
                        raise
        except Exception as e:
            logger.exception(f"Error updating tax summary for slip {slip_name}: {str(e)}")
            frappe.log_error(
                f"Error updating tax summary for slip {slip_name}: {str(e)}",
                "Tax Summary Update Error"
            )


def _get_or_create_tax_row(slip: Document) -> Tuple[Any, Any]:
    employee = slip.employee
    year = getdate(slip.posting_date).year

    filters = {"employee": employee, "year": year}
    summary_name = frappe.db.get_value("Employee Tax Summary", filters)

    if summary_name:
        summary = frappe.get_doc("Employee Tax Summary", summary_name)
    else:
        summary = frappe.new_doc("Employee Tax Summary")
        summary.employee = employee
        summary.year = year

    if hasattr(slip, "start_date") and slip.start_date:
        month = getdate(slip.start_date).month
    else:
        month = getdate(slip.posting_date).month

    row = None
    for detail in summary.get("monthly_details", []):
        if detail.month == month:
            row = detail
            break

    if not row:
        row = summary.append(
            "monthly_details",
            {
                "month": month,
                "gross_pay": 0,
                "tax_amount": 0,
                "bpjs_deductions_employee": 0,
                "other_deductions": 0,
                "salary_slip": "",
                "is_using_ter": 0,
                "ter_rate": 0,
            },
        )

    return row, summary


def _update_tax_detail_from_slip(row: Any, slip: Document) -> None:
    tax_amount = 0
    bpjs_deductions = 0
    other_deductions = 0

    if hasattr(slip, "deductions"):
        for deduction in slip.deductions:
            if deduction.salary_component == "PPh 21":
                tax_amount = flt(deduction.amount)
            elif deduction.salary_component in [
                "BPJS JHT Employee",
                "BPJS JP Employee",
                "BPJS Kesehatan Employee",
            ]:
                bpjs_deductions += flt(deduction.amount)
            else:
                other_deductions += flt(deduction.amount)

    row.gross_pay = flt(getattr(slip, "gross_pay", 0))
    row.tax_amount = tax_amount

    if hasattr(row, "bpjs_deductions"):
        row.bpjs_deductions = bpjs_deductions
    if hasattr(row, "bpjs_deductions_employee"):
        row.bpjs_deductions_employee = bpjs_deductions
    if hasattr(row, "other_deductions"):
        row.other_deductions = other_deductions

    if hasattr(row, "is_using_ter") and hasattr(slip, "is_using_ter"):
        row.is_using_ter = cint(slip.is_using_ter)
    if hasattr(row, "ter_rate") and hasattr(slip, "ter_rate"):
        row.ter_rate = flt(slip.ter_rate)


def _zero_tax_detail(row: Any) -> None:
    row.gross_pay = 0
    row.tax_amount = 0

    if hasattr(row, "bpjs_deductions"):
        row.bpjs_deductions = 0
    if hasattr(row, "bpjs_deductions_employee"):
        row.bpjs_deductions_employee = 0
    if hasattr(row, "other_deductions"):
        row.other_deductions = 0
    if hasattr(row, "is_using_ter"):
        row.is_using_ter = 0
    if hasattr(row, "ter_rate"):
        row.ter_rate = 0


def _calculate_ytd_totals(summary: Document) -> None:
    ytd_totals = {
        "gross_pay": 0,
        "tax_amount": 0,
        "bpjs_deductions": 0,
        "other_deductions": 0,
    }

    for detail in summary.get("monthly_details", []):
        ytd_totals["gross_pay"] += flt(detail.gross_pay)
        ytd_totals["tax_amount"] += flt(detail.tax_amount)

        if hasattr(detail, "bpjs_deductions_employee"):
            ytd_totals["bpjs_deductions"] += flt(detail.bpjs_deductions_employee)
        elif hasattr(detail, "bpjs_deductions"):
            ytd_totals["bpjs_deductions"] += flt(detail.bpjs_deductions)

        if hasattr(detail, "other_deductions"):
            ytd_totals["other_deductions"] += flt(detail.other_deductions)

    if hasattr(summary, "ytd_gross_pay"):
        summary.ytd_gross_pay = ytd_totals["gross_pay"]
    if hasattr(summary, "ytd_tax"):
        summary.ytd_tax = ytd_totals["tax_amount"]
    if hasattr(summary, "ytd_bpjs"):
        summary.ytd_bpjs = ytd_totals["bpjs_deductions"]
    if hasattr(summary, "ytd_other_deductions"):
        summary.ytd_other_deductions = ytd_totals["other_deductions"]
update_employee_history = update_tax_summary
