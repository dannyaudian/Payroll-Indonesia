import frappe
import re
from frappe.utils import cint


def get_or_create_annual_payroll_history(employee_name, fiscal_year, month, create_if_missing=True):
    """Ambil doc Annual Payroll History berdasarkan employee, fiscal_year, dan month.

    Jika tidak ada dan ``create_if_missing`` bernilai ``True`` akan membuat doc baru.
    Bila ``create_if_missing`` ``False`` dan dokumen tidak ditemukan, kembalikan ``None``.
    """
    # Menggunakan frappe.db.exists untuk pengecekan cepat keberadaan dokumen
    doc_name = frappe.db.get_value(
        "Annual Payroll History",
        {"employee": employee_name, "fiscal_year": fiscal_year, "month": month},
        "name"
    )
    
    if doc_name:
        return frappe.get_doc("Annual Payroll History", doc_name)

    if not create_if_missing:
        return None

    # Buat dokumen baru
    history = frappe.new_doc("Annual Payroll History")
    history.employee = employee_name
    history.fiscal_year = fiscal_year
    history.month = month

    # Set name ke kombinasi unik employee-fiscal_year-month jika skema doctype mendukung
    # Catatan: Ini hanya akan berhasil jika Annual Payroll History DocType dikonfigurasi
    # untuk menerima nama kustom (autoname: field:employee-field:fiscal_year-field:month atau prompt)
    history.name = f"{employee_name}-{fiscal_year}-{month}"
    
    return history


def update_annual_payroll_summary(history, summary):
    """
    Update summary (parent) fields pada Annual Payroll History.
    """
    if not summary:
        return
    for k, v in summary.items():
        if hasattr(history, k):
            setattr(history, k, v)
        else:
            history.set(k, v)


def is_salary_slip_valid(salary_slip_name):
    """
    Verifikasi apakah Salary Slip valid dan telah disimpan (submitted).
    
    Args:
        salary_slip_name: Nama Salary Slip yang akan diverifikasi
    
    Returns:
        tuple: (valid, reason)
            - valid: Boolean yang menunjukkan apakah Salary Slip valid
            - reason: Alasan jika tidak valid, atau None jika valid
    """
    if not salary_slip_name:
        return False, "Salary slip name is empty"
    
    # Periksa string terlihat seperti temporary/unsaved name
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
    
    # Periksa jika dokumen ada di database
    if not frappe.db.exists("Salary Slip", salary_slip_name):
        return False, f"Salary slip does not exist in database: {salary_slip_name}"
    
    # Periksa docstatus
    docstatus = frappe.db.get_value("Salary Slip", salary_slip_name, "docstatus")
    if cint(docstatus) != 1:  # 0=Draft, 1=Submitted, 2=Cancelled
        status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
        return False, f"Salary slip exists but has invalid status: {status_map.get(cint(docstatus), 'Unknown')}"
    
    return True, None


def upsert_monthly_detail(history, month_data):
    """
    Tambah atau update child (monthly_details) di Annual Payroll History.
    Unik berdasarkan bulan/salary_slip.
    Jika data dengan salary_slip/bulan sudah ada, update. Jika tidak, append baru.
    
    Periksa validitas salary_slip dengan docstatus dan keberadaannya di database.
    
    Returns:
        bool: True jika berhasil ditambah/diupdate, False jika dilewati karena invalid
    """
    month = month_data.get("bulan")
    salary_slip = month_data.get("salary_slip")
    
    # Validasi salary slip jika ada
    if salary_slip:
        is_valid, reason = is_salary_slip_valid(salary_slip)
        if not is_valid:
            frappe.logger().warning(
                f"Skipping invalid Salary Slip in Annual Payroll History sync: {salary_slip}. Reason: {reason}"
            )
            return False
    
    # Cari child yang sama (by bulan atau salary_slip)
    found = None
    for detail in history.get("monthly_details", []):
        # Match by exact salary slip match or (month match and no conflicting salary slip)
        if (salary_slip and detail.salary_slip == salary_slip) or \
           (month and detail.bulan == month and (not salary_slip or not detail.salary_slip)):
            found = detail
            break
            
    if found:
        # Update existing record
        for k, v in month_data.items():
            if k in ["bulan", "bruto", "pengurang_netto", "biaya_jabatan", "netto", "pkp", "rate", "pph21", "salary_slip"]:
                found.set(k, v)
    else:
        # Create new record
        detail = history.append("monthly_details", {})
        for k, v in month_data.items():
            if k in ["bulan", "bruto", "pengurang_netto", "biaya_jabatan", "netto", "pkp", "rate", "pph21", "salary_slip"]:
                detail.set(k, v)
                
    return True


def remove_monthly_detail_by_salary_slip(history, salary_slip):
    """
    Hapus baris child monthly_details berdasarkan nomor salary_slip.
    Biasanya dipakai saat slip gaji dicancel.
    
    Returns:
        int: Jumlah baris yang dihapus
    """
    if not salary_slip:
        return 0
    
    to_remove = []
    for i, detail in enumerate(history.get("monthly_details", [])):
        if detail.salary_slip == salary_slip:
            to_remove.append(i)
    
    # Hapus dari belakang supaya index tidak bergeser
    for i in reversed(to_remove):
        history.monthly_details.pop(i)
        
    return len(to_remove)


def sync_annual_payroll_history(
    employee,
    fiscal_year,
    month,
    monthly_results=None,
    summary=None,
    cancelled_salary_slip=None,
):
    """
    Sinkronisasi data hasil kalkulasi PPh21 TER ke Annual Payroll History dan child-nya.

    Fungsi ini menggunakan frappe.db.savepoint() untuk penanganan transaksi, namun
    tidak melakukan commit. Pemanggil harus mengelola commit/rollback sesuai kebutuhan.

    - Jika dokumen sudah ada untuk employee & fiscal_year & month, update.
    - Jika belum ada, create baru.
    - Jika salary_slip dicancel, hapus baris terkait pada child.
    - Perubahan akan di-rollback jika terjadi error setelah savepoint.
    - Salary Slip divalidasi dengan memeriksa docstatus dan keberadaannya.

    Args:
        employee: dict/obj Employee (harus ada `name`)
        fiscal_year: str (misal "2025")
        month: int (1-12)
        monthly_results: list of dict, masing-masing dict punya keys:
            - bulan, bruto, pengurang_netto, biaya_jabatan, netto, pkp, rate, pph21, salary_slip
        summary: dict, optional, berisi field parent seperti:
            - bruto_total, netto_total, ptkp_annual, pkp_annual, pph21_annual, koreksi_pph21
        cancelled_salary_slip: str, optional, jika ingin menghapus baris berdasarkan salary_slip

    Returns:
        str: Nama dokumen Annual Payroll History yang diupdate/dibuat, atau None jika gagal
    """
    # Extract employee name safely without assuming specific object structure
    employee_name = None
    if isinstance(employee, dict) and "name" in employee:
        employee_name = employee["name"]
    elif hasattr(employee, "name"):
        employee_name = employee.name
    
    if not employee_name:
        # Strict validation to prevent processing with invalid employee data
        frappe.throw("Employee harus punya field 'name'!", title="Validation Error")
    
    # Validate fiscal year
    if not fiscal_year or not isinstance(fiscal_year, str):
        frappe.throw("Fiscal year harus berupa string valid", title="Validation Error")
        
    # Validate month
    if month is not None:
        try:
            month = cint(month)
            if month < 0 or month > 12:
                frappe.throw(f"Month '{month}' harus 0-12", title="Validation Error")
        except (ValueError, TypeError):
            frappe.throw(f"Month '{month}' harus berupa integer", title="Validation Error")

    # Check for invalid salary slips in monthly_results
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
        # Update monthly_results to only include valid entries
        monthly_results = valid_results

    # Check if cancelled_salary_slip is valid
    if cancelled_salary_slip:
        if not frappe.db.exists("Salary Slip", cancelled_salary_slip):
            frappe.logger().warning(
                f"Cancelled Salary Slip '{cancelled_salary_slip}' not found in database, skipping removal"
            )
            cancelled_salary_slip = None
            
    only_cancel = cancelled_salary_slip and not monthly_results and not summary

    # Create a transaction savepoint to allow rollback if needed
    savepoint_name = f"annual_history_sync_{employee_name}_{fiscal_year}_{month}"
    frappe.db.savepoint(savepoint_name)

    try:
        history = get_or_create_annual_payroll_history(
            employee_name, fiscal_year, month, create_if_missing=not only_cancel
        )

        if not history:
            frappe.logger().info(
                f"No Annual Payroll History found for employee {employee_name}, "
                f"fiscal year {fiscal_year}, month {month} and not creating new record"
            )
            return None

        is_new_doc = history.is_new()
        rows_updated = 0
        rows_deleted = 0

        # Process cancellations first
        if cancelled_salary_slip:
            rows_deleted = remove_monthly_detail_by_salary_slip(history, cancelled_salary_slip)
            if rows_deleted:
                frappe.logger().info(
                    f"Removed {rows_deleted} entries for cancelled Salary Slip {cancelled_salary_slip}"
                )
            else:
                frappe.logger().info(
                    f"No entries found to remove for cancelled Salary Slip {cancelled_salary_slip}"
                )

        # Process updates/additions
        if monthly_results:
            for row in monthly_results:
                if upsert_monthly_detail(history, row):
                    rows_updated += 1
                    
        # Skip saving if no rows were actually updated or deleted
        if rows_updated == 0 and rows_deleted == 0:
            frappe.logger().info(
                f"No rows updated or deleted in Annual Payroll History for {employee_name}, skipping save"
            )
            return None

        # Update summary/parent fields
        if summary:
            update_annual_payroll_summary(history, summary)

        # Initialize default values for new docs
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

        # Save with error handling
        try:
            # Log detailed debug info
            frappe.logger().debug(
                f"[{frappe.session.user}] Saving Annual Payroll History '{history.name}' "
                f"for employee '{employee_name}', fiscal year {fiscal_year}, month {month} "
                f"with {rows_updated} rows updated and {rows_deleted} rows deleted "
                f"at {frappe.utils.now()}"
            )

            # Gunakan flags untuk mengabaikan validasi link & permissions
            history.flags.ignore_links = True
            history.flags.ignore_permissions = True
            history.save()
            
            # Jika kita sampai di sini, operasi save berhasil
            return history.name
            
        except frappe.LinkValidationError as e:
            # Rollback ke savepoint jika terjadi link validation error
            frappe.db.rollback(save_point=savepoint_name)
            
            frappe.logger().warning(
                f"Link validation error when saving Annual Payroll History for {employee_name}. "
                f"Error: {str(e)}"
            )
            frappe.throw(
                f"Gagal menyimpan Annual Payroll History: Referensi link tidak valid. "
                f"Kemungkinan Salary Slip belum tersimpan.",
                title="Link Validation Error"
            )

        except Exception as e:
            # Rollback ke savepoint jika terjadi exception umum
            frappe.db.rollback(save_point=savepoint_name)
            
            frappe.log_error(
                message=f"Failed to save Annual Payroll History: {str(e)}",
                title="Annual Payroll History Save Error"
            )
            
            # Improved error message with more diagnostic information
            error_message = f"Gagal menyimpan Annual Payroll History: {str(e)}"
            if "Could not find Row" in str(e) and "Salary Slip" in str(e):
                error_message += "\nKemungkinan penyebab: Salary Slip belum disimpan ke database"
            frappe.throw(error_message)
            
    except Exception as e:
        # Rollback ke savepoint jika terjadi exception di luar block save 
        frappe.db.rollback(save_point=savepoint_name)
        
        frappe.log_error(
            message=f"Error in sync_annual_payroll_history: {str(e)}",
            title="Annual Payroll History Sync Error"
        )
        frappe.throw(f"Gagal memproses Annual Payroll History: {str(e)}")