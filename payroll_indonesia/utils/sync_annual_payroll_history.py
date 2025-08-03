import frappe
import re
import json
try:
    from frappe.utils import cint, flt, getdate
except Exception:  # pragma: no cover - fallback for test stubs without cint/flt
    def cint(value):
        try:
            return int(value)
        except Exception:
            return 0

    def flt(value):
        try:
            return float(value)
        except Exception:
            return 0.0

def get_or_create_annual_payroll_history(employee_id, fiscal_year, create_if_missing=True):
    doc_name = frappe.db.get_value(
        "Annual Payroll History",
        {"employee": employee_id, "fiscal_year": fiscal_year},
        "name"
    )
    
    if doc_name:
        return frappe.get_doc("Annual Payroll History", doc_name)

    if not create_if_missing:
        return None

    history = frappe.new_doc("Annual Payroll History")
    history.employee = employee_id
    history.fiscal_year = fiscal_year

    employee_doc = None
    try:
        employee_doc = frappe.get_doc("Employee", employee_id)
    except Exception:
        employee_doc = None

    company = getattr(employee_doc, "company", None)
    if not company and getattr(frappe, "defaults", None):
        try:
            company = frappe.defaults.get_global_default("company")
        except Exception:
            company = None
    if not company and hasattr(frappe, "get_all"):
        try:
            first_company = frappe.get_all("Company", fields=["name"], limit=1)
            if first_company:
                company = first_company[0].get("name")
        except Exception:
            company = None

    history.company = company
    history.employee_name = getattr(employee_doc, "employee_name", None) or employee_id

    history.name = f"{employee_id}-{fiscal_year}"
    for field in [
        "bruto_total",
        "netto_total",
        "ptkp_annual",
        "pkp_annual",
        "pph21_annual",
        "koreksi_pph21",
    ]:
        setattr(history, field, 0)

    return history

def update_annual_payroll_summary(history, summary):
    if not summary:
        return
    for k, v in summary.items():
        if hasattr(history, k):
            setattr(history, k, v)
        else:
            history.set(k, v)

def is_salary_slip_valid(salary_slip_name):
    if not salary_slip_name:
        return False, "Salary slip name is empty"
    
    temp_patterns = [
        r"^new-salary-slip-",
        r"unsaved",
        r"^\d+-salary-slip-",
        r"^Sal Slip/.*?/unsaved$",
        r"^Sal Slip/.*?/draft$",
        r"^Sal Slip/.*?/tmp$"
    ]
    
    for pattern in temp_patterns:
        if re.search(pattern, str(salary_slip_name), re.IGNORECASE):
            return False, f"Salary slip has temporary name pattern: {pattern}"
    
    if not frappe.db.exists("Salary Slip", salary_slip_name):
        return False, f"Salary slip does not exist in database: {salary_slip_name}"
    
    docstatus = frappe.db.get_value("Salary Slip", salary_slip_name, "docstatus")
    if cint(docstatus) != 1:
        status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
        return False, f"Salary slip exists but has invalid status: {status_map.get(cint(docstatus), 'Unknown')}"
    
    return True, None

def upsert_monthly_detail(history, month_data):
    bulan = month_data.get("bulan")
    salary_slip = month_data.get("salary_slip")

    if bulan is None:
        frappe.logger().warning("Skipping monthly detail without required 'bulan'")
        return False

    bulan = cint(bulan)

    if salary_slip:
        is_valid, reason = is_salary_slip_valid(salary_slip)
        if not is_valid:
            frappe.logger().warning(
                f"Skipping invalid Salary Slip in Annual Payroll History sync: {salary_slip}. Reason: {reason}"
            )
            return False

    found = None
    for detail in history.get("monthly_details", []):
        if salary_slip and detail.salary_slip == salary_slip:
            found = detail
            break
        if detail.bulan == bulan:
            found = detail
            break

    numeric_fields = [
        "bruto",
        "pengurang_netto",
        "biaya_jabatan",
        "netto",
        "pkp",
        "rate",
        "pph21",
    ]

    if found:
        target = found
    else:
        target = history.append("monthly_details", {})

    target.set("bulan", bulan)
    if salary_slip:
        target.set("salary_slip", salary_slip)
    if month_data.get("error_state") is not None:
        target.set("error_state", month_data.get("error_state"))

    for field in numeric_fields:
        if field in month_data:
            target.set(field, flt(month_data.get(field)))

    return True

def remove_monthly_detail_by_salary_slip(history, salary_slip, error_state=None):
    if not salary_slip:
        return 0

    if error_state is not None:
        for detail in history.get("monthly_details", []):
            if detail.salary_slip == salary_slip:
                detail.error_state = json.dumps(error_state)
                break
        return 0

    to_remove = []
    for i, detail in enumerate(history.get("monthly_details", [])):
        if detail.salary_slip == salary_slip:
            to_remove.append(i)

    for i in reversed(to_remove):
        history.monthly_details.pop(i)

    return len(to_remove)

def sync_annual_payroll_history(
    employee,
    fiscal_year,
    monthly_results=None,
    summary=None,
    cancelled_salary_slip=None,
    error_state=None,
):
    monthly_results = monthly_results or []
    last_doc = None

    employee_info = {"name": None, "company": None, "employee_name": None}
    if isinstance(employee, str):
        employee_info["name"] = employee
    elif isinstance(employee, dict):
        employee_info["name"] = employee.get("name")
        employee_info["company"] = employee.get("company")
        employee_info["employee_name"] = employee.get("employee_name")
    else:
        employee_info["name"] = getattr(employee, "name", None)
        employee_info["company"] = getattr(employee, "company", None)
        employee_info["employee_name"] = getattr(employee, "employee_name", None)

    employee_id = employee_info.get("name")

    if not employee_id:
        frappe.throw("Employee must have an ID", title="Validation Error")

    if not employee_info.get("company") or not employee_info.get("employee_name"):
        try:
            if hasattr(frappe, "db") and hasattr(frappe.db, "get_value"):
                extra = frappe.db.get_value(
                    "Employee",
                    employee_id,
                    ["name", "company", "employee_name"],
                    as_dict=True,
                )
                if extra:
                    employee_info.setdefault("company", extra.get("company"))
                    employee_info.setdefault("employee_name", extra.get("employee_name"))
        except Exception:
            pass

    if not employee_info.get("company"):
        company = None
        if getattr(frappe, "defaults", None):
            try:
                company = frappe.defaults.get_global_default("company")
            except Exception:
                company = None
        if not company and hasattr(frappe, "get_all"):
            try:
                first_company = frappe.get_all("Company", fields=["name"], limit=1)
                if first_company:
                    company = first_company[0].get("name")
            except Exception:
                company = None
        employee_info["company"] = company

    logger = frappe.logger("payroll_indonesia")
    for idx, row in enumerate(monthly_results):
        bulan = row.get("bulan")
        logger.debug(f"sync_annual_payroll_history processing month {bulan}: {row}")
        is_last = idx == len(monthly_results) - 1
        last_doc = sync_annual_payroll_history_for_bulan(
            employee=employee_info,
            fiscal_year=fiscal_year,
            bulan=bulan,
            monthly_results=[row],
            summary=summary if is_last else None,
            cancelled_salary_slip=None,
            error_state=error_state if is_last else None,
        )

    if not monthly_results or cancelled_salary_slip:
        last_doc = sync_annual_payroll_history_for_bulan(
            employee=employee_info,
            fiscal_year=fiscal_year,
            bulan=None,
            monthly_results=None,
            summary=summary if not monthly_results else None,
            cancelled_salary_slip=cancelled_salary_slip,
            error_state=error_state if not monthly_results else None,
        )

    return last_doc

def sync_annual_payroll_history_legacy(
    employee,
    fiscal_year,
    bulan,
    monthly_results=None,
    summary=None,
    cancelled_salary_slip=None,
    error_state=None,
):
    if monthly_results:
        enriched = []
        for row in monthly_results:
            if "bulan" not in row:
                row = dict(row)
                row["bulan"] = bulan
            enriched.append(row)
        monthly_results = enriched
    elif bulan is not None:
        monthly_results = [{"bulan": bulan}]

    employee_id = (
        employee
        if isinstance(employee, str)
        else employee.get("name")
        if isinstance(employee, dict)
        else getattr(employee, "name", None)
    )

    return sync_annual_payroll_history(
        employee=employee_id,
        fiscal_year=fiscal_year,
        monthly_results=monthly_results,
        summary=summary,
        cancelled_salary_slip=cancelled_salary_slip,
        error_state=error_state,
    )

def sync_annual_payroll_history_for_bulan(
    employee,
    fiscal_year,
    bulan,
    monthly_results=None,
    summary=None,
    cancelled_salary_slip=None,
    error_state=None,
):
    employee_id = None
    if isinstance(employee, str) and employee:
        employee_id = employee
    elif isinstance(employee, dict) and "name" in employee:
        employee_id = employee["name"]
    elif hasattr(employee, "name"):
        employee_id = employee.name

    if not employee_id:
        frappe.throw("Employee harus punya field 'name'!", title="Validation Error")
    
    if not fiscal_year or not isinstance(fiscal_year, str):
        frappe.throw("Fiscal year harus berupa string valid", title="Validation Error")
        
    if bulan is not None:
        try:
            bulan = cint(bulan)
            if bulan < 0 or bulan > 12:
                frappe.throw(f"Bulan '{bulan}' harus 0-12", title="Validation Error")
        except (ValueError, TypeError):
            frappe.throw(f"Bulan '{bulan}' harus berupa integer", title="Validation Error")

    if monthly_results:
        valid_results = []
        for row in monthly_results:
            salary_slip = row.get("salary_slip", "")
            if salary_slip:
                is_valid, reason = is_salary_slip_valid(salary_slip)
                if not is_valid:
                    frappe.logger().warning(
                        f"Annual Payroll History: Skipping invalid slip: {salary_slip}. Reason: {reason}"
                    )
                    continue
            valid_results.append(row)
            
        if not valid_results:
            frappe.logger().info("No valid salary slips found for Annual Payroll History sync")
            return None
        monthly_results = valid_results

    if cancelled_salary_slip:
        if not frappe.db.exists("Salary Slip", cancelled_salary_slip):
            frappe.logger().warning(
                f"Cancelled Salary Slip '{cancelled_salary_slip}' not found in database, skipping removal"
            )
            cancelled_salary_slip = None
            
    only_cancel = cancelled_salary_slip and not monthly_results and not summary

    savepoint_name = f"annual_history_sync_{employee_id}_{fiscal_year}_{bulan}"
    frappe.db.savepoint(savepoint_name)

    try:
        history = get_or_create_annual_payroll_history(
            employee_id, fiscal_year, create_if_missing=not only_cancel
        )

        if not history:
            frappe.logger().info(
                f"No Annual Payroll History found for employee {employee_id}, "
                f"fiscal year {fiscal_year} and not creating new record"
            )
            return None

        is_new_doc = history.is_new()
        rows_updated = 0
        rows_deleted = 0

        if cancelled_salary_slip:
            rows_deleted = remove_monthly_detail_by_salary_slip(
                history, cancelled_salary_slip, error_state=error_state
            )
            if rows_deleted:
                frappe.logger().info(
                    f"Removed {rows_deleted} entries for cancelled Salary Slip {cancelled_salary_slip}"
                )
            else:
                frappe.logger().info(
                    f"No entries found to remove for cancelled Salary Slip {cancelled_salary_slip}"
                )

        if monthly_results:
            for row in monthly_results:
                if upsert_monthly_detail(history, row):
                    rows_updated += 1
                    
        if error_state is not None:
            history.set("error_state", frappe.as_json(error_state))

        if rows_updated == 0 and rows_deleted == 0 and error_state is None and not summary:
            frappe.logger().info(
                f"No rows updated, deleted, or summary provided in Annual Payroll History for {employee_id}, skipping save"
            )
            return None

        if summary:
            update_annual_payroll_summary(history, summary)

        if is_new_doc:
            for field in [
                "bruto_total",
                "netto_total",
                "ptkp_annual",
                "pkp_annual",
                "pph21_annual",
                "koreksi_pph21",
            ]:
                if history.get(field) is None:
                    history.set(field, 0)

        try:
            frappe.logger().debug(
                f"[{frappe.session.user}] Saving Annual Payroll History '{history.name}' "
                f"for employee '{employee_id}', fiscal year {fiscal_year}, bulan {bulan} "
                f"with {rows_updated} rows updated and {rows_deleted} rows deleted "
                f"at {frappe.utils.now()}"
            )

            history.flags.ignore_links = True
            history.flags.ignore_permissions = True
            history.save()
            
            return history.name
            
        except frappe.LinkValidationError as e:
            frappe.db.rollback(save_point=savepoint_name)
            
            frappe.logger().warning(
                f"Link validation error when saving Annual Payroll History for {employee_id}. "
                f"Error: {str(e)}"
            )
            frappe.throw(
                f"Gagal menyimpan Annual Payroll History: Referensi link tidak valid. "
                f"Kemungkinan Salary Slip belum tersimpan.",
                title="Link Validation Error"
            )

        except Exception as e:
            frappe.db.rollback(save_point=savepoint_name)
            
            frappe.log_error(
                message=f"Failed to save Annual Payroll History: {str(e)}",
                title="Annual Payroll History Save Error"
            )
            
            error_message = f"Gagal menyimpan Annual Payroll History: {str(e)}"
            if "Could not find Row" in str(e) and "Salary Slip" in str(e):
                error_message += "\nKemungkinan penyebab: Salary Slip belum disimpan ke database"
            frappe.throw(error_message)
            
    except Exception as e:
        frappe.db.rollback(save_point=savepoint_name)
        
        frappe.log_error(
            message=f"Error in sync_annual_payroll_history: {str(e)}",
            title="Annual Payroll History Sync Error"
        )
        frappe.throw(f"Gagal memproses Annual Payroll History: {str(e)}")

def sync_salary_slip_to_annual(doc, method=None):
    try:
        if method == "on_cancel" or getattr(doc, "docstatus", 0) == 2:
            fiscal_year = getattr(doc, "fiscal_year", None)
            if not fiscal_year and hasattr(doc, "start_date") and doc.start_date:
                fiscal_year = str(getdate(doc.start_date).year)

            if fiscal_year:
                sync_annual_payroll_history(
                    employee=doc.employee,
                    fiscal_year=fiscal_year,
                    monthly_results=None,
                    summary=None,
                    cancelled_salary_slip=doc.name
                )
                frappe.logger().info(f"Removed cancelled Salary Slip {doc.name} from Annual Payroll History")
            return

        if method != "on_submit" and getattr(doc, "docstatus", 0) != 1:
            return

        bulan = None
        if hasattr(doc, "start_date") and doc.start_date:
            bulan = getdate(doc.start_date).month
        elif hasattr(doc, "bulan") and doc.bulan:
            bulan = cint(doc.bulan)

        if not bulan:
            frappe.logger().warning(f"Cannot determine month for Salary Slip {doc.name}, using current month")
            from datetime import datetime
            bulan = datetime.now().month

        fiscal_year = getattr(doc, "fiscal_year", None)
        if not fiscal_year and hasattr(doc, "start_date") and doc.start_date:
            fiscal_year = str(getdate(doc.start_date).year)
        if not fiscal_year:
            frappe.logger().warning(f"Cannot determine fiscal year for Salary Slip {doc.name}, using current year")
            from datetime import datetime
            fiscal_year = str(datetime.now().year)

        pph21_info = {}
        if hasattr(doc, "pph21_info") and doc.pph21_info:
            try:
                import json
                pph21_info = json.loads(doc.pph21_info)
            except Exception as e:
                frappe.logger().warning(f"Error parsing pph21_info for {doc.name}: {str(e)}")

        row = {
            "bulan": bulan,
            "bruto": getattr(doc, "gross_pay", 0),
            "pengurang_netto": pph21_info.get("pengurang_netto", 0),
            "biaya_jabatan": pph21_info.get("biaya_jabatan", 0),
            "netto": getattr(doc, "net_pay", 0),
            "pkp": pph21_info.get("pkp", 0),
            "rate": pph21_info.get("rate", 0),
            "pph21": getattr(doc, "tax", pph21_info.get("pph21", 0)),
            "salary_slip": doc.name,
        }

        summary = None
        if getattr(doc, "tax_type", "") == "DECEMBER" and pph21_info:
            summary = {
                "bruto_total": pph21_info.get("bruto_total", 0),
                "netto_total": pph21_info.get("netto_total", 0),
                "ptkp_annual": pph21_info.get("ptkp_annual", 0),
                "pkp_annual": pph21_info.get("pkp_annual", 0),
                "pph21_annual": pph21_info.get("pph21_annual", 0),
                "koreksi_pph21": pph21_info.get("koreksi_pph21", 0),
            }

        sync_annual_payroll_history(
            employee=doc.employee,
            fiscal_year=fiscal_year,
            monthly_results=[row],
            summary=summary,
        )

        frappe.logger().info(f"Successfully synced Salary Slip {doc.name} to Annual Payroll History")

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        frappe.log_error(
            message=f"Failed to sync Salary Slip {getattr(doc, 'name', 'unknown')} to Annual Payroll History: {str(e)}\n{error_trace}",
            title="Annual Payroll History Sync Error"
        )
        frappe.logger().error(f"Error in sync_salary_slip_to_annual: {str(e)}")
