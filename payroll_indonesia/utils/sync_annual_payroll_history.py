import frappe
import re
import json
import traceback
from typing import Dict, List, Optional, Tuple, Union, Any

try:
    from frappe.utils import cint, flt, getdate
except Exception:  # pragma: no cover - fallback for test stubs without cint/flt
    def cint(value: Any) -> int:
        """Convert value to integer safely."""
        try:
            return int(value)
        except Exception:
            return 0

    def flt(value: Any) -> float:
        """Convert value to float safely."""
        try:
            return float(value)
        except Exception:
            return 0.0


def sanitize_savepoint_name(name: str) -> str:
    """
    Sanitize savepoint name to contain only safe characters and limit its length.
    
    Args:
        name: Original savepoint name
        
    Returns:
        Sanitized savepoint name
    """
    # Replace unsafe characters with underscores
    safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', str(name))
    # Limit length to 63 characters (common DB savepoint name limit)
    return safe_name[:63]


def truncate_doc_name(name: str, max_length: int = 140) -> str:
    """
    Truncate document name to ensure it doesn't exceed maximum length.
    
    Args:
        name: Original document name
        max_length: Maximum allowed length (default 140)
        
    Returns:
        Truncated name
    """
    if not name:
        return name
    
    if len(name) <= max_length:
        return name
    
    # If name exceeds limit, truncate preserving important parts
    parts = name.split('-')
    if len(parts) >= 2:
        # For format like "EMPLOYEE-YEAR", ensure we keep both parts
        employee_id = parts[0]
        fiscal_year = parts[-1]
        
        # Calculate how much to truncate employee_id
        available_length = max_length - len(fiscal_year) - 1  # -1 for hyphen
        if available_length > 10:
            return f"{employee_id[:available_length]}-{fiscal_year}"
        else:
            # If too short, just truncate the whole string
            return name[:max_length]
    else:
        # Simple truncation for other formats
        return name[:max_length]


def get_or_create_annual_payroll_history(
    employee_id: str, 
    fiscal_year: str, 
    create_if_missing: bool = True
) -> Optional[Any]:
    """
    Get or create Annual Payroll History document.
    
    Args:
        employee_id: Employee ID
        fiscal_year: Fiscal year
        create_if_missing: Whether to create document if not found
        
    Returns:
        Annual Payroll History document or None
    """
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

    # Validate and truncate document name
    history.name = truncate_doc_name(f"{employee_id}-{fiscal_year}")
    
    # Don't set default values here - they'll be set by the DocType itself
    # This allows the system to respect any changes to the DocType defaults

    return history


def update_annual_payroll_summary(history: Any, summary: Dict[str, Any]) -> None:
    """
    Update Annual Payroll History summary fields.
    
    Args:
        history: Annual Payroll History document
        summary: Dictionary of summary values
    """
    if not summary:
        return
        
    # Map of summary field keys to DocType field names for any fields that don't match exactly
    field_mapping = {
        "pengurang_netto_total": "pengurang_netto_total",
        "biaya_jabatan_total": "biaya_jabatan_total",
        # Add more mappings as needed
    }
        
    for k, v in summary.items():
        # Check if there's a mapping for this field
        field_name = field_mapping.get(k, k)
        
        # If value is None, don't explicitly set it to 0
        # This allows the DocType's default value to be used
        if v is None:
            continue
            
        if hasattr(history, field_name):
            setattr(history, field_name, v)
        else:
            # Fallback to using set method if attribute doesn't exist
            history.set(field_name, v)


def is_salary_slip_valid(
    salary_slip_name: str, 
    in_transaction_context: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    Check if a salary slip is valid for inclusion in Annual Payroll History.
    
    Args:
        salary_slip_name: Name of the salary slip
        in_transaction_context: Whether this is called within a transaction context
                              like a savepoint (affects database access)
        
    Returns:
        Tuple of (is_valid, reason_if_invalid)
    """
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
    
    # If we're in a transaction context, use frappe.get_doc() instead of direct DB access
    # This ensures we use the current transaction's view of the database
    if in_transaction_context:
        try:
            slip = frappe.get_doc("Salary Slip", salary_slip_name)
            if cint(slip.docstatus) != 1:
                status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
                return False, f"Salary slip exists but has invalid status: {status_map.get(cint(slip.docstatus), 'Unknown')}"
            return True, None
        except frappe.DoesNotExistError:
            return False, f"Salary slip does not exist in database: {salary_slip_name}"
        except Exception as e:
            return False, f"Error checking salary slip: {str(e)}"
    else:
        # Outside transaction context, direct DB access is fine
        if not frappe.db.exists("Salary Slip", salary_slip_name):
            return False, f"Salary slip does not exist in database: {salary_slip_name}"
        
        docstatus = frappe.db.get_value("Salary Slip", salary_slip_name, "docstatus")
        if cint(docstatus) != 1:
            status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
            return False, f"Salary slip exists but has invalid status: {status_map.get(cint(docstatus), 'Unknown')}"
        
        return True, None


def upsert_monthly_detail(history: Any, month_data: Dict[str, Any]) -> bool:
    """
    Update or insert monthly detail in Annual Payroll History.
    
    Args:
        history: Annual Payroll History document
        month_data: Monthly data to insert or update
        
    Returns:
        True if detail was updated, False otherwise
    """
    bulan = month_data.get("bulan")
    salary_slip = month_data.get("salary_slip")

    if bulan is None:
        logger = frappe.logger("payroll_indonesia")
        logger.warning("Skipping monthly detail without required 'bulan'")
        return False

    # Normalize month to integer within valid range
    try:
        bulan = cint(bulan)
        if bulan < 1:
            bulan = 1
        elif bulan > 12:
            bulan = 12
    except (ValueError, TypeError):
        bulan = 1  # Default to January if invalid

    if salary_slip:
        # Pass in_transaction_context=True since this is typically called within a savepoint
        is_valid, reason = is_salary_slip_valid(salary_slip, in_transaction_context=True)
        if not is_valid:
            logger = frappe.logger("payroll_indonesia")
            logger.warning(
                "Skipping invalid Salary Slip in Annual Payroll History sync: "
                f"{salary_slip}. Reason: {reason}"
            )
            return False

    # Improved duplicate detection logic - require both month and slip to match
    found = None
    for detail in history.get("monthly_details", []):
        # If salary slip is provided, match by salary slip first
        if salary_slip and detail.salary_slip == salary_slip:
            found = detail
            break
        # If no match by salary slip but month matches, use it only if no slip is set
        if not found and detail.bulan == bulan and not salary_slip:
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
        
    # Serialize error_state to JSON consistently
    if month_data.get("error_state") is not None:
        error_state = month_data.get("error_state")
        if not isinstance(error_state, str):
            target.set("error_state", json.dumps(error_state))
        else:
            # Check if it's already JSON string
            try:
                json.loads(error_state)
                target.set("error_state", error_state)
            except Exception:
                target.set("error_state", json.dumps(error_state))
    
    # Get DocType metadata to check field defaults
    doctype_meta = None
    try:
        doctype_meta = frappe.get_meta("Annual Payroll History Child")
    except Exception:
        # If we can't get meta, we'll just use values as is
        pass
    
    for field in numeric_fields:
        if field in month_data:
            value = month_data.get(field)
            
            # Only process fields that are present in month_data
            # If value is None, check if we should use the DocType default
            if value is None and doctype_meta:
                # Try to get the default from DocType definition
                field_def = doctype_meta.get_field(field)
                if field_def and field_def.default is not None:
                    value = field_def.default
                else:
                    # If no default in DocType, use 0 as last resort
                    value = 0
            elif value is None:
                # If we couldn't get meta, default to 0 for None values
                value = 0
                
            target.set(field, flt(value))

    return True


def remove_monthly_detail_by_salary_slip(
    history: Any, 
    salary_slip: str, 
    error_state: Optional[Dict[str, Any]] = None
) -> int:
    """
    Remove monthly detail entries by salary slip from Annual Payroll History.
    
    Args:
        history: Annual Payroll History document
        salary_slip: Salary slip to remove
        error_state: Optional error state to set
        
    Returns:
        Number of entries removed
    """
    if not salary_slip:
        return 0

    # Set error state if provided (now consistently serialized to JSON)
    if error_state is not None:
        for detail in history.get("monthly_details", []):
            if detail.salary_slip == salary_slip:
                # Ensure error_state is properly serialized
                if not isinstance(error_state, str):
                    detail.error_state = json.dumps(error_state)
                else:
                    # Check if it's already JSON string
                    try:
                        json.loads(error_state)
                        detail.error_state = error_state
                    except Exception:
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
    employee: Union[str, Dict[str, Any], Any],
    fiscal_year: str,
    monthly_results: Optional[List[Dict[str, Any]]] = None,
    summary: Optional[Dict[str, Any]] = None,
    cancelled_salary_slip: Optional[str] = None,
    error_state: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Synchronize Annual Payroll History for an employee.
    
    Args:
        employee: Employee ID, dict or object
        fiscal_year: Fiscal year
        monthly_results: List of monthly results to sync
        summary: Summary values to update
        cancelled_salary_slip: Salary slip to mark as cancelled
        error_state: Error state to set
        
    Returns:
        Name of the updated document or None
    """
    monthly_results = monthly_results or []
    last_doc = None

    # Validate employee parameter
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

    # Validate fiscal year
    if not fiscal_year or not isinstance(fiscal_year, str):
        frappe.throw("Fiscal year must be a valid string", title="Validation Error")

    # Get additional employee data if needed
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

    # Get company if not found
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
    
    # Process each monthly result
    for idx, row in enumerate(monthly_results):
        bulan = row.get("bulan")
        logger.debug("sync_annual_payroll_history processing month %s: %s", bulan, row)
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

    # Apply summary and cancelled_salary_slip if needed
    if not monthly_results or cancelled_salary_slip:
        last_doc = sync_annual_payroll_history_for_bulan(
            employee=employee_info,
            fiscal_year=fiscal_year,
            bulan=None,
            monthly_results=None,
            # Always apply summary when there are cancelled slips
            summary=summary,
            cancelled_salary_slip=cancelled_salary_slip,
            error_state=error_state if not monthly_results else None,
        )

    return last_doc


def sync_annual_payroll_history_legacy(
    employee: Union[str, Dict[str, Any], Any],
    fiscal_year: str,
    bulan: Optional[int] = None,
    monthly_results: Optional[List[Dict[str, Any]]] = None,
    summary: Optional[Dict[str, Any]] = None,
    cancelled_salary_slip: Optional[str] = None,
    error_state: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Legacy function to synchronize Annual Payroll History.
    
    Args:
        employee: Employee ID, dict or object
        fiscal_year: Fiscal year
        bulan: Month number (1-12)
        monthly_results: List of monthly results to sync
        summary: Summary values to update
        cancelled_salary_slip: Salary slip to mark as cancelled
        error_state: Error state to set
        
    Returns:
        Name of the updated document or None
    """
    # Normalize month parameter
    if bulan is not None:
        try:
            bulan = cint(bulan)
            if bulan < 1:
                bulan = 1
            elif bulan > 12:
                bulan = 12
        except (ValueError, TypeError):
            bulan = None
    
    if monthly_results:
        enriched = []
        for row in monthly_results:
            if "bulan" not in row and bulan is not None:
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
    employee: Union[str, Dict[str, Any], Any],
    fiscal_year: str,
    bulan: Optional[int] = None,
    monthly_results: Optional[List[Dict[str, Any]]] = None,
    summary: Optional[Dict[str, Any]] = None,
    cancelled_salary_slip: Optional[str] = None,
    error_state: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Synchronize Annual Payroll History for a specific month.
    
    Args:
        employee: Employee ID, dict or object
        fiscal_year: Fiscal year
        bulan: Month number (1-12)
        monthly_results: List of monthly results to sync
        summary: Summary values to update
        cancelled_salary_slip: Salary slip to mark as cancelled
        error_state: Error state to set
        
    Returns:
        Name of the updated document or None
    """
    # Validate employee parameter
    employee_id = None
    if isinstance(employee, str) and employee:
        employee_id = employee
    elif isinstance(employee, dict) and "name" in employee:
        employee_id = employee["name"]
    elif hasattr(employee, "name"):
        employee_id = employee.name

    if not employee_id:
        frappe.throw("Employee harus punya field 'name'!", title="Validation Error")
    
    # Validate fiscal year
    if not fiscal_year or not isinstance(fiscal_year, str):
        frappe.throw("Fiscal year harus berupa string valid", title="Validation Error")
        
    # Normalize month parameter
    if bulan is not None:
        try:
            bulan = cint(bulan)
            if bulan < 1:
                bulan = 1
            elif bulan > 12:
                bulan = 12
        except (ValueError, TypeError):
            frappe.logger("payroll_indonesia").warning(
                "Bulan '%s' tidak valid, dinormalisasi ke bulan 1", bulan
            )
            bulan = 1

    # Validate salary slips in monthly results
    if monthly_results:
        valid_results = []
        for row in monthly_results:
            salary_slip = row.get("salary_slip", "")
            if salary_slip:
                # Pass in_transaction_context=False since we're not in a savepoint yet
                is_valid, reason = is_salary_slip_valid(salary_slip, in_transaction_context=False)
                if not is_valid:
                    frappe.logger("payroll_indonesia").warning(
                        "Annual Payroll History: Skipping invalid slip: %s. Reason: %s",
                        salary_slip, reason
                    )
                    continue
            valid_results.append(row)
            
        if not valid_results:
            frappe.logger("payroll_indonesia").info(
                "No valid salary slips found for Annual Payroll History sync"
            )
            return None
        monthly_results = valid_results

    # Validate cancelled salary slip
    if cancelled_salary_slip:
        if not frappe.db.exists("Salary Slip", cancelled_salary_slip):
            frappe.logger("payroll_indonesia").warning(
                "Cancelled Salary Slip '%s' not found in database, skipping removal",
                cancelled_salary_slip
            )
            cancelled_salary_slip = None
            
    only_cancel = cancelled_salary_slip and not monthly_results and not summary

    # Create sanitized savepoint name
    savepoint_base = f"annual_history_sync_{employee_id}_{fiscal_year}"
    if bulan is not None:
        savepoint_base = f"{savepoint_base}_{bulan}"
    savepoint_name = sanitize_savepoint_name(savepoint_base)
    
    frappe.db.savepoint(savepoint_name)

    try:
        history = get_or_create_annual_payroll_history(
            employee_id, fiscal_year, create_if_missing=not only_cancel
        )

        if not history:
            frappe.logger("payroll_indonesia").info(
                "No Annual Payroll History found for employee %s, "
                "fiscal year %s and not creating new record",
                employee_id, fiscal_year
            )
            return None

        is_new_doc = history.is_new()
        rows_updated = 0
        rows_deleted = 0

        # Remove cancelled salary slip entries
        if cancelled_salary_slip:
            rows_deleted = remove_monthly_detail_by_salary_slip(
                history, cancelled_salary_slip, error_state=error_state
            )
            if rows_deleted:
                frappe.logger("payroll_indonesia").info(
                    "Removed %d entries for cancelled Salary Slip %s",
                    rows_deleted, cancelled_salary_slip
                )
            else:
                frappe.logger("payroll_indonesia").info(
                    "No entries found to remove for cancelled Salary Slip %s",
                    cancelled_salary_slip
                )

        # Update monthly details
        if monthly_results:
            for row in monthly_results:
                if upsert_monthly_detail(history, row):
                    rows_updated += 1
                    
        # Set error state
        if error_state is not None:
            # Ensure error_state is properly serialized
            if isinstance(error_state, str):
                try:
                    # Check if it's already a JSON string
                    json.loads(error_state)
                    history.set("error_state", error_state)
                except Exception:
                    history.set("error_state", json.dumps(error_state))
            else:
                history.set("error_state", json.dumps(error_state))

        # Apply summary even with cancelled slip and no updates
        if summary:
            update_annual_payroll_summary(history, summary)
            # Force save when summary is provided
            rows_updated = 1

        # Skip save if no changes
        if rows_updated == 0 and rows_deleted == 0 and error_state is None and not summary:
            frappe.logger("payroll_indonesia").info(
                "No rows updated, deleted, or summary provided in Annual Payroll History for %s, skipping save",
                employee_id
            )
            return None

        # Initialize numeric fields for new documents
        if is_new_doc:
            # Get DocType metadata to check field defaults
            try:
                doctype_meta = frappe.get_meta("Annual Payroll History")
                for field in [
                    "bruto_total",
                    "netto_total",
                    "pengurang_netto_total",
                    "biaya_jabatan_total",
                    "ptkp_annual",
                    "pkp_annual",
                    "pph21_annual",
                    "koreksi_pph21",
                ]:
                    # Only set default if field is None (not already set)
                    if history.get(field) is None:
                        # Try to get default from DocType
                        field_def = doctype_meta.get_field(field)
                        if field_def and field_def.default is not None:
                            history.set(field, field_def.default)
                        else:
                            # Fall back to 0 if no DocType default
                            history.set(field, 0)
            except Exception:
                # If we can't get meta, fall back to simple initialization
                for field in [
                    "bruto_total",
                    "netto_total",
                    "pengurang_netto_total",
                    "biaya_jabatan_total",
                    "ptkp_annual",
                    "pkp_annual",
                    "pph21_annual",
                    "koreksi_pph21",
                ]:
                    if history.get(field) is None:
                        history.set(field, 0)

        # Calculate totals from monthly details if summary is not provided
        if not summary and monthly_results:
            try:
                # Aggregate monthly details to calculate totals
                recalculate_summary_from_monthly_details(history)
            except Exception as calc_error:
                # Non-critical error, log but continue
                frappe.logger("payroll_indonesia").warning(
                    "Failed to recalculate summary from monthly details: %s", str(calc_error)
                )

        try:
            frappe.logger("payroll_indonesia").debug(
                "[%s] Saving Annual Payroll History '%s' for employee '%s', "
                "fiscal year %s, bulan %s with %d rows updated and %d rows deleted at %s",
                frappe.session.user, history.name, employee_id, fiscal_year, bulan,
                rows_updated, rows_deleted, frappe.utils.now()
            )

            history.flags.ignore_links = True
            history.flags.ignore_permissions = True
            history.save()
            
            # Auto-submit the document if still in Draft status
            if history.docstatus == 0:
                try:
                    history.flags.ignore_links = True
                    history.flags.ignore_permissions = True
                    history.submit()
                    frappe.logger("payroll_indonesia").info(
                        "Auto-submitted Annual Payroll History '%s' for employee '%s', fiscal year %s",
                        history.name, employee_id, fiscal_year
                    )
                except Exception as submit_error:
                    # Log error but don't throw - we already saved the document successfully
                    error_trace = traceback.format_exc()
                    frappe.log_error(
                        message=f"Failed to auto-submit Annual Payroll History '{history.name}': {str(submit_error)}\n{error_trace}",
                        title="Annual Payroll History Auto-Submit Error"
                    )
                    frappe.logger("payroll_indonesia").warning(
                        "Failed to auto-submit Annual Payroll History '%s': %s",
                        history.name, str(submit_error)
                    )
            
            return history.name
            
        except frappe.LinkValidationError as e:
            frappe.db.rollback(save_point=savepoint_name)
            
            frappe.logger("payroll_indonesia").warning(
                "Link validation error when saving Annual Payroll History for %s. Error: %s",
                employee_id, str(e)
            )
            frappe.throw(
                f"Gagal menyimpan Annual Payroll History: Referensi link tidak valid. "
                f"Kemungkinan Salary Slip belum tersimpan.",
                title="Link Validation Error"
            )

        except Exception as e:
            frappe.db.rollback(save_point=savepoint_name)
            
            error_trace = traceback.format_exc()
            frappe.log_error(
                message=f"Failed to save Annual Payroll History: {str(e)}\n{error_trace}",
                title="Annual Payroll History Save Error"
            )
            
            error_message = f"Gagal menyimpan Annual Payroll History: {str(e)}"
            if "Could not find Row" in str(e) and "Salary Slip" in str(e):
                error_message += "\nKemungkinan penyebab: Salary Slip belum disimpan ke database"
            frappe.throw(error_message)
            
    except Exception as e:
        frappe.db.rollback(save_point=savepoint_name)
        
        error_trace = traceback.format_exc()
        frappe.log_error(
            message=f"Error in sync_annual_payroll_history: {str(e)}\n{error_trace}",
            title="Annual Payroll History Sync Error"
        )
        # Re-raise exception after logging
        frappe.throw(f"Gagal memproses Annual Payroll History: {str(e)}")


def recalculate_summary_from_monthly_details(history: Any) -> None:
    """
    Recalculate summary fields based on monthly details.
    
    Args:
        history: Annual Payroll History document
    """
    if not history or not hasattr(history, "monthly_details"):
        return
    
    # Initialize totals
    bruto_total = 0
    pengurang_netto_total = 0
    biaya_jabatan_total = 0
    pph21_total = 0
    
    # Sum up values from monthly details
    for detail in history.monthly_details:
        bruto_total += flt(getattr(detail, "bruto", 0))
        pengurang_netto_total += flt(getattr(detail, "pengurang_netto", 0))
        biaya_jabatan_total += flt(getattr(detail, "biaya_jabatan", 0))
        pph21_total += flt(getattr(detail, "pph21", 0))
    
    # Calculate netto_total
    netto_total = bruto_total - pengurang_netto_total - biaya_jabatan_total
    
    # Update summary fields
    history.bruto_total = bruto_total
    history.pengurang_netto_total = pengurang_netto_total
    history.biaya_jabatan_total = biaya_jabatan_total
    history.netto_total = netto_total
    
    # Only update these fields if they don't already have values
    # since they may be set from external calculations
    if not history.pph21_annual or history.pph21_annual == 0:
        history.pph21_annual = pph21_total
    
    # Calculate koreksi_pph21 if pph21_annual is set
    if history.pph21_annual:
        # koreksi_pph21 is the difference between annual PPh21 and sum of monthly PPh21
        history.koreksi_pph21 = history.pph21_annual - pph21_total


def normalize_month(bulan: Any) -> int:
    """
    Normalize month value to ensure it's within valid range 1-12.
    
    Args:
        bulan: Month value to normalize
        
    Returns:
        Normalized month as integer (1-12)
    """
    if bulan is None:
        from datetime import datetime
        return datetime.now().month
        
    try:
        month_int = cint(bulan)
        if month_int < 1:
            return 1
        elif month_int > 12:
            return 12
        return month_int
    except (ValueError, TypeError):
        # Default to current month if invalid
        from datetime import datetime
        return datetime.now().month


def sync_salary_slip_to_annual(doc: Any, method: Optional[str] = None) -> None:
    """
    Synchronize Salary Slip to Annual Payroll History.
    
    Args:
        doc: Salary Slip document
        method: Hook method name
    """
    logger = frappe.logger("payroll_indonesia")
    warning_shown = False
    
    try:
        # Handle cancellation
        if method == "on_cancel" or getattr(doc, "docstatus", 0) == 2:
            fiscal_year = getattr(doc, "fiscal_year", None)
            if not fiscal_year and hasattr(doc, "start_date") and doc.start_date:
                fiscal_year = str(getdate(doc.start_date).year)

            if not fiscal_year and not warning_shown:
                logger.warning(
                    "Cannot determine fiscal year for cancelled Salary Slip %s", 
                    getattr(doc, "name", "unknown")
                )
                warning_shown = True
                
            if fiscal_year:
                # Apply summary even for cancelled slips
                summary = None
                if hasattr(doc, "pph21_info") and doc.pph21_info:
                    try:
                        pph21_info = json.loads(doc.pph21_info)
                        summary = {
                            "bruto_total": pph21_info.get("bruto_total", 0),
                            "netto_total": pph21_info.get("netto_total", 0),
                            "pengurang_netto_total": pph21_info.get("pengurang_netto_total", 0),
                            "biaya_jabatan_total": pph21_info.get("biaya_jabatan_total", 0),
                            "ptkp_annual": pph21_info.get("ptkp_annual", 0),
                            "pkp_annual": pph21_info.get("pkp_annual", 0),
                            "pph21_annual": pph21_info.get("pph21_annual", 0),
                            "koreksi_pph21": pph21_info.get("koreksi_pph21", 0),
                        }
                    except Exception as e:
                        logger.warning(
                            "Error parsing pph21_info for cancelled slip %s: %s", 
                            getattr(doc, "name", "unknown"), str(e)
                        )
                
                sync_annual_payroll_history(
                    employee=doc.employee,
                    fiscal_year=fiscal_year,
                    monthly_results=None,
                    summary=summary,
                    cancelled_salary_slip=doc.name
                )
                logger.info(
                    "Removed cancelled Salary Slip %s from Annual Payroll History",
                    doc.name
                )
            return

        # Skip non-submitted documents
        if method != "on_submit" and getattr(doc, "docstatus", 0) != 1:
            return

        # Determine month with stricter validation
        bulan = None
        if hasattr(doc, "start_date") and doc.start_date:
            try:
                bulan = getdate(doc.start_date).month
            except Exception:
                bulan = None
                
        if bulan is None and hasattr(doc, "bulan") and doc.bulan:
            try:
                bulan = cint(doc.bulan)
            except Exception:
                bulan = None

        # Use normalize_month to ensure valid range
        bulan = normalize_month(bulan)
        
        # Warning for source data is logged before normalization if needed
        if not hasattr(doc, "start_date") and not hasattr(doc, "bulan"):
            logger.warning(
                "Missing month data for Salary Slip %s, using current month as fallback",
                getattr(doc, "name", "unknown")
            )

        # Determine fiscal year
        fiscal_year = getattr(doc, "fiscal_year", None)
        if not fiscal_year and hasattr(doc, "start_date") and doc.start_date:
            fiscal_year = str(getdate(doc.start_date).year)
        if not fiscal_year:
            logger.warning(
                "Cannot determine fiscal year for Salary Slip %s, using current year",
                getattr(doc, "name", "unknown")
            )
            from datetime import datetime
            fiscal_year = str(datetime.now().year)

        # Parse PPH21 info
        pph21_info = {}
        if hasattr(doc, "pph21_info") and doc.pph21_info:
            try:
                pph21_info = json.loads(doc.pph21_info)
            except Exception as e:
                logger.warning(
                    "Error parsing pph21_info for %s: %s",
                    getattr(doc, "name", "unknown"), str(e)
                )

        # Prepare monthly data
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

        # Prepare summary for December or if requested
        summary = None
        if getattr(doc, "tax_type", "") == "DECEMBER" and pph21_info:
            summary = {
                "bruto_total": pph21_info.get("bruto_total", 0),
                "netto_total": pph21_info.get("netto_total", 0),
                "pengurang_netto_total": pph21_info.get("pengurang_netto_total", 0),
                "biaya_jabatan_total": pph21_info.get("biaya_jabatan_total", 0),
                "ptkp_annual": pph21_info.get("ptkp_annual", 0),
                "pkp_annual": pph21_info.get("pkp_annual", 0),
                "pph21_annual": pph21_info.get("pph21_annual", 0),
                "koreksi_pph21": pph21_info.get("koreksi_pph21", 0),
            }

        # Sync to Annual Payroll History
        sync_annual_payroll_history(
            employee=doc.employee,
            fiscal_year=fiscal_year,
            monthly_results=[row],
            summary=summary,
        )

        logger.info(
            "Successfully synced Salary Slip %s to Annual Payroll History",
            getattr(doc, "name", "unknown")
        )

    except Exception as e:
        error_trace = traceback.format_exc()
        # Gabungkan f-string menjadi satu pesan yang utuh
        frappe.log_error(
            message=f"Failed to sync Salary Slip {getattr(doc, 'name', 'unknown')} to Annual Payroll History: {str(e)}\n{error_trace}",
            title="Annual Payroll History Sync Error"
        )
        logger.error("Error in sync_salary_slip_to_annual: %s", str(e))
        # Re-raise the exception to ensure proper error handling
        raise