# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
"""
Employee Tax Summary management for Indonesian payroll.

This module handles the creation, updating, and management of Employee Tax Summary records
which track annual tax payments and related information for employees. It provides
functionality for:

1. Creating and retrieving tax summaries for employees
2. Updating summaries when salary slips are submitted or cancelled
3. Managing monthly detail records and calculating YTD totals
4. Handling TER (Tax Exemption Ratio) data

These functions are designed to be called from hooks, background jobs, or directly
from the UI to ensure tax data is properly maintained.
"""

from typing import Dict, Any, Optional
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, cint
from payroll_indonesia.frappe_helpers.logger import get_logger

logger = get_logger(__name__)
class EmployeeTaxSummary(Document):
    def validate(self) -> None:
        try:
            self._validate_required_fields()
            self._validate_duplicate()
            self._set_title()
            self.calculate_ytd_totals()
            self._validate_monthly_details()
        except Exception as e:
            logger.exception(f"Error validating Employee Tax Summary {self.name}: {str(e)}")
            frappe.throw(_("Error validating tax summary: {0}").format(str(e)))

    def _validate_required_fields(self) -> None:
        if not self.employee:
            frappe.throw(_("Employee is mandatory for Employee Tax Summary"))
        if not self.year:
            frappe.throw(_("Year is mandatory for Employee Tax Summary"))
        try:
            year_val = int(self.year)
            if year_val < 2000 or year_val > 2100:
                frappe.throw(_("Year must be between 2000 and 2100"))
        except (ValueError, TypeError):
            frappe.throw(_("Invalid year value: {0}").format(self.year))

    def _validate_duplicate(self) -> None:
        if self.is_new():
            return
        existing = frappe.db.exists(
            "Employee Tax Summary",
            {
                "name": ["!=", self.name],
                "employee": self.employee,
                "year": self.year
            }
        )
        if existing:
            frappe.throw(
                _("Tax summary for employee {0} for year {1} already exists (ID: {2})").format(
                    self.employee_name or self.employee, self.year, existing
                )
            )

    def _set_title(self) -> None:
        if not self.employee_name:
            self.employee_name = frappe.db.get_value(
                "Employee", self.employee, "employee_name"
            ) or self.employee
        self.title = f"{self.employee_name} - {self.year}"

    def _validate_monthly_details(self) -> None:
        if not self.monthly_details:
            return
        months_seen = {}
        for detail in self.monthly_details:
            if not detail.month:
                frappe.throw(_("Month is required in row {0}").format(detail.idx))
            if detail.month < 1 or detail.month > 12:
                frappe.throw(_("Invalid month {0} in row {1}").format(detail.month, detail.idx))
            if detail.month in months_seen:
                frappe.throw(
                    _("Duplicate month {0} in rows {1} and {2}").format(
                        detail.month, months_seen[detail.month], detail.idx
                    )
                )
            months_seen[detail.month] = detail.idx
            if flt(detail.gross_pay) < 0:
                detail.gross_pay = 0
            if flt(detail.tax_amount) < 0:
                detail.tax_amount = 0
            if cint(detail.is_using_ter) and (
                flt(detail.ter_rate) <= 0 or flt(detail.ter_rate) > 50
            ):
                frappe.msgprint(
                    _("Invalid TER rate {0}% in month {1}").format(detail.ter_rate, detail.month)
                )

    def calculate_ytd_totals(self) -> None:
        ytd_gross = 0
        ytd_tax = 0
        ytd_bpjs = 0
        ytd_other = 0
        for detail in self.monthly_details or []:
            ytd_gross += flt(detail.gross_pay)
            ytd_tax += flt(detail.tax_amount)
            ytd_bpjs += flt(getattr(detail, "bpjs_deductions_employee", 0))
            ytd_other += flt(getattr(detail, "other_deductions", 0))
        self.ytd_gross_pay = ytd_gross
        self.ytd_tax = ytd_tax
        self.ytd_bpjs = ytd_bpjs
        if hasattr(self, "ytd_other_deductions"):
            self.ytd_other_deductions = ytd_other

    def update_month_from_slip(self, slip: Document) -> None:
        if not slip or not hasattr(slip, "posting_date"):
            logger.error("Invalid salary slip provided to update_month_from_slip")
            return
        month = getdate(slip.posting_date).month if slip.posting_date else None
        if not month and hasattr(slip, "start_date") and slip.start_date:
            month = getdate(slip.start_date).month
        if not month:
            logger.error(f"Could not determine month from slip {slip.name}")
            return
        values = extract_slip_values(slip)
        detail = None
        for row in self.monthly_details:
            if row.month == month:
                detail = row
                break
        if not detail:
            detail = self.append("monthly_details", {"month": month})
        detail.gross_pay = values["gross_pay"]
        detail.tax_amount = values["tax_amount"]
        detail.bpjs_deductions_employee = values["bpjs_amount"]
        detail.other_deductions = values["other_deductions"]
        detail.salary_slip = slip.name
        detail.is_using_ter = values["is_using_ter"]
        detail.ter_rate = values["ter_rate"]
        for field, value in values.items():
            if hasattr(detail, field) and field not in [
                "gross_pay", "tax_amount", "bpjs_amount", "other_deductions",
                "is_using_ter", "ter_rate"
            ]:
                setattr(detail, field, value)
        self.calculate_ytd_totals()

    def reset_month(self, month: int, slip_name: Optional[str] = None) -> bool:
        if month < 1 or month > 12:
            logger.warning(f"Invalid month {month} in reset_month")
            return False
        changed = False
        for detail in self.monthly_details:
            if detail.month == month:
                if slip_name and detail.salary_slip != slip_name:
                    continue
                detail.gross_pay = 0
                detail.tax_amount = 0
                detail.bpjs_deductions_employee = 0
                detail.other_deductions = 0
                detail.salary_slip = ""
                detail.is_using_ter = 0
                detail.ter_rate = 0
                for field in ["biaya_jabatan", "netto", "annual_taxable_income"]:
                    if hasattr(detail, field):
                        setattr(detail, field, 0)
                if hasattr(detail, "ter_category"):
                    detail.ter_category = ""
                changed = True
                break
        return changed

    def on_update(self) -> None:
        try:
            if not self.title:
                self._set_title()
                self.db_set("title", self.title, update_modified=False)
            has_ter = False
            max_ter_rate = 0
            for detail in self.monthly_details or []:
                if cint(detail.is_using_ter):
                    has_ter = True
                    max_ter_rate = max(max_ter_rate, flt(detail.ter_rate))
            if hasattr(self, "is_using_ter"):
                self.db_set("is_using_ter", 1 if has_ter else 0, update_modified=False)
            if hasattr(self, "ter_rate") and has_ter:
                self.db_set("ter_rate", max_ter_rate, update_modified=False)
    except Exception as e:
            logger.exception(f"Error in on_update for Employee Tax Summary {self.name}: {str(e)}")

def get_summary(employee: str, year: int) -> Document:
    if not employee:
        frappe.throw(_("Employee is required to get tax summary"))
    try:
        year = int(year)
    except (ValueError, TypeError):
        frappe.throw(_("Invalid year value: {0}").format(year))
    filters = {"employee": employee, "year": year}
    summary_name = frappe.db.get_value("Employee Tax Summary", filters)
    if summary_name:
        return frappe.get_doc("Employee Tax Summary", summary_name)
    return create_new_summary(employee, year)

def create_new_summary(employee: str, year: int) -> Document:
    summary = frappe.new_doc("Employee Tax Summary")
    summary.employee = employee
    summary.year = year
    emp = frappe.db.get_value(
        "Employee",
        employee,
        ["employee_name", "department", "designation", "npwp", "ptkp_status"],
        as_dict=True
        )
    if emp:
        summary.employee_name = emp.employee_name
        for field in ["department", "designation", "npwp", "ptkp_status"]:
            if emp.get(field) and hasattr(summary, field):
                setattr(summary, field, emp.get(field))
    for month in range(1, 13):
        summary.append(
            "monthly_details",
            {
                "month": month,
                "gross_pay": 0,
                "tax_amount": 0,
                "bpjs_deductions_employee": 0,
                "other_deductions": 0,
                "is_using_ter": 0,
                "ter_rate": 0
            }
        )
    try:
        summary.insert(ignore_permissions=True)
        logger.info(f"Created new Employee Tax Summary for {employee}, year {year}")
        return summary
    except Exception as e:
        logger.exception(
            f"Error creating Employee Tax Summary for {employee}, year {year}: {str(e)}"
        )
        frappe.throw(_("Error creating tax summary: {0}").format(str(e)))

def extract_slip_values(slip: Document) -> Dict[str, Any]:
    result = {
        "gross_pay": 0,
        "tax_amount": 0,
        "bpjs_amount": 0,
        "other_deductions": 0,
        "is_using_ter": 0,
        "ter_rate": 0,
        "biaya_jabatan": 0,
        "netto": 0,
        "ter_category": ""
    }
    if hasattr(slip, "gross_pay"):
        result["gross_pay"] = flt(slip.gross_pay)
    if hasattr(slip, "deductions"):
        for deduction in slip.deductions:
            if deduction.salary_component == "PPh 21":
                result["tax_amount"] = flt(deduction.amount)
            elif deduction.salary_component in [
                "BPJS JHT Employee",
                "BPJS JP Employee",
                "BPJS Kesehatan Employee"
            ]:
                result["bpjs_amount"] += flt(deduction.amount)
            else:
                result["other_deductions"] += flt(deduction.amount)
    if hasattr(slip, "is_using_ter"):
        result["is_using_ter"] = cint(slip.is_using_ter)
    if hasattr(slip, "ter_rate"):
        result["ter_rate"] = flt(slip.ter_rate)
    if hasattr(slip, "ter_category"):
        result["ter_category"] = slip.ter_category
    for field in ["biaya_jabatan", "netto"]:
        if hasattr(slip, field):
            result[field] = flt(getattr(slip, field))
    return result

def update_summary(slip_name: str) -> None:
    try:
        slip = frappe.get_doc("Salary Slip", slip_name)
        if not slip.employee:
            logger.warning(f"Salary slip {slip_name} has no employee, skipping tax summary update")
            return
        if slip.docstatus != 1:
            logger.warning(
                f"Salary slip {slip_name} is not submitted (status={slip.docstatus}), "
                "skipping tax summary update"
            )
            return
        if hasattr(slip, "posting_date") and slip.posting_date:
            year = getdate(slip.posting_date).year
        elif hasattr(slip, "start_date") and slip.start_date:
            year = getdate(slip.start_date).year
        else:
            logger.error(f"Could not determine year from slip {slip_name}")
            return
        summary = get_summary(slip.employee, year)
        summary.update_month_from_slip(slip)
        summary.flags.ignore_permissions = True
        summary.flags.ignore_validate_update_after_submit = True
        summary.save()
        logger.info(f"Updated tax summary for employee {slip.employee}, year {year}")
    except Exception as e:
        logger.exception(f"Error updating tax summary from slip {slip_name}: {str(e)}")
        frappe.log_error(
            f"Error updating tax summary from slip {slip_name}: {str(e)}",
            "Employee Tax Summary Error"
        )

def reset_month(slip_name: str) -> None:
    try:
        slip = frappe.get_doc("Salary Slip", slip_name)
        if not slip.employee:
            logger.warning(f"Salary slip {slip_name} has no employee, skipping tax reset")
            return
        if slip.docstatus != 2:
            logger.warning(
                f"Salary slip {slip_name} is not cancelled (status={slip.docstatus}), "
                "skipping tax reset"
            )
            return
        month = None
        year = None
        if hasattr(slip, "start_date") and slip.start_date:
            month = getdate(slip.start_date).month
            year = getdate(slip.start_date).year
        elif hasattr(slip, "posting_date") and slip.posting_date:
            month = getdate(slip.posting_date).month
            year = getdate(slip.posting_date).year
        if not month or not year:
            logger.error(f"Could not determine month/year from slip {slip_name}")
            return
        summary_name = frappe.db.get_value(
            "Employee Tax Summary",
            {"employee": slip.employee, "year": year}
        )
        if not summary_name:
            logger.info(f"No tax summary found for employee {slip.employee}, year {year}")
            return
        summary = frappe.get_doc("Employee Tax Summary", summary_name)
        changed = summary.reset_month(month, slip_name)
        if changed:
            summary.calculate_ytd_totals()
            summary.flags.ignore_permissions = True
            summary.flags.ignore_validate_update_after_submit = True
            summary.save()
            logger.info(
                f"Reset tax data for employee {slip.employee}, year {year}, month {month}"
            )
    except Exception as e:
        logger.exception(f"Error resetting tax data for slip {slip_name}: {str(e)}")
        frappe.log_error(
            f"Error resetting tax data for slip {slip_name}: {str(e)}",
            "Employee Tax Summary Error"
        )

@frappe.whitelist()
def refresh_tax_summary(employee: str, year: Optional[int] = None) -> Dict[str, Any]:
    try:
        if not year:
            year = getdate().year
        try:
            year = int(year)
        except (ValueError, TypeError):
            return {"status": "error", "message": f"Invalid year value: {year}"}
        slips = frappe.get_all(
            "Salary Slip",
            filters={
                "employee": employee,
                "docstatus": 1,
                "start_date": [">=", f"{year}-01-01"],
                "end_date": ["<=", f"{year}-12-31"]
            },
            fields=["name"]
        )
        if not slips:
            return {
                "status": "error",
                "message": f"No submitted salary slips found for {employee} in {year}"
            }
        summary = get_summary(employee, year)
        for month in range(1, 13):
            summary.reset_month(month)
        summary.flags.ignore_permissions = True
        summary.flags.ignore_validate_update_after_submit = True
        summary.save()
        processed = 0
        for slip in slips:
            update_summary(slip.name)
            processed += 1
        return {
            "status": "success",
            "message": f"Refreshed tax summary with {processed} salary slips",
            "tax_summary": summary.name,
            "processed": processed,
            "total_slips": len(slips)
        }
    except Exception as e:
        logger.exception(f"Error refreshing tax summary for {employee}, {year}: {str(e)}")
        return {"status": "error", "message": str(e)}

@frappe.whitelist()
def get_ytd_data(employee: str, year: int, month: int) -> Dict[str, Any]:
    try:
        month = int(month)
        if month < 1 or month > 12:
            return {"status": "error", "message": f"Invalid month: {month}"}
        summary_name = frappe.db.get_value(
            "Employee Tax Summary",
            {"employee": employee, "year": year}
        )
        if not summary_name:
            return {
                "status": "error",
                "message": f"No tax summary found for {employee} in {year}"
            }
        summary = frappe.get_doc("Employee Tax Summary", summary_name)
        ytd_gross = 0
        ytd_tax = 0
        ytd_bpjs = 0
        monthly_data = []
        for detail in summary.monthly_details:
            if detail.month <= month:
                ytd_gross += flt(detail.gross_pay)
                ytd_tax += flt(detail.tax_amount)
                ytd_bpjs += flt(detail.bpjs_deductions_employee)
                monthly_data.append({
                    "month": detail.month,
                    "gross_pay": detail.gross_pay,
                    "tax_amount": detail.tax_amount,
                    "bpjs": detail.bpjs_deductions_employee,
                    "is_using_ter": detail.is_using_ter,
                    "ter_rate": detail.ter_rate
                })
        return {
            "status": "success",
            "employee": employee,
            "year": year,
            "month": month,
            "ytd_gross": ytd_gross,
            "ytd_tax": ytd_tax,
            "ytd_bpjs": ytd_bpjs,
            "monthly_data": monthly_data
        }
    except Exception as e:
        logger.exception(f"Error getting YTD data for {employee}, {year}, month {month}: {str(e)}")
        return {"status": "error", "message": str(e)}
