import frappe
import re
import json
try:
    from frappe.utils import cint, flt
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
    """Ambil doc Annual Payroll History berdasarkan ``employee`` dan ``fiscal_year``.

    Jika tidak ada dan ``create_if_missing`` bernilai ``True`` akan membuat doc baru.
    Bila ``create_if_missing`` ``False`` dan dokumen tidak ditemukan, kembalikan ``None``.
    """
    # Menggunakan frappe.db.exists untuk pengecekan cepat keberadaan dokumen
    doc_name = frappe.db.get_value(
        "Annual Payroll History",
        {"employee": employee_id, "fiscal_year": fiscal_year},
        "name"
    )
    
    if doc_name:
        return frappe.get_doc("Annual Payroll History", doc_name)

    if not create_if_missing:
        return None

    # Buat dokumen baru
    history = frappe.new_doc("Annual Payroll History")
    history.employee = employee_id
    history.fiscal_year = fiscal_year

    # Ambil informasi tambahan dari dokumen Employee
    employee_doc = None
    try:
        employee_doc = frappe.get_doc("Employee", employee_id)
    except Exception:
        employee_doc = None

    default_company = (
        frappe.defaults.get_user_default("Company") if getattr(frappe, "defaults", None) else None
    )
    history.company = getattr(employee_doc, "company", None) or default_company
    history.employee_name = getattr(employee_doc, "employee_name", None) or employee_id

    # Set explicit name dan inisialisasi nilai parent
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
    Unik berdasarkan ``bulan``/``salary_slip``.
    Jika data dengan ``salary_slip``/``bulan`` sudah ada, update. Jika tidak, append baru.

    Periksa validitas ``salary_slip`` dengan docstatus dan keberadaannya di database.

    Returns:
        bool: True jika berhasil ditambah/diupdate, False jika dilewati karena invalid
    """
    bulan = month_data.get("bulan")
    salary_slip = month_data.get("salary_slip")

    if bulan is None:
        frappe.logger().warning("Skipping monthly detail without required 'bulan'")
        return False

    bulan = cint(bulan)

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
    """
    Hapus baris child ``monthly_details`` berdasarkan ``salary_slip``.
    Bila ``error_state`` diberikan, baris tidak dihapus melainkan kolom
    ``error_state`` pada detail diisi dengan JSON dari struktur yang
    diberikan.

    Args:
        history: Dokumen Annual Payroll History.
        salary_slip: Nama Salary Slip yang menjadi acuan.
        error_state: Optional, struktur error yang ingin disimpan.

    Returns:
        int: Jumlah baris yang dihapus.
    """
    if not salary_slip:
        return 0

    # Jika error_state diberikan, cari detail dan simpan error_state tanpa menghapus
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

    # Hapus dari belakang supaya index tidak bergeser
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
    """Sync Annual Payroll History untuk satu atau lebih bulan.

    Parameter ``employee`` dapat berupa object, dict, ataupun langsung
    berupa string ID karyawan. Jika hanya ID string yang diberikan,
    fungsi ini akan mengambil data tambahan seperti ``company`` dan
    ``employee_name`` dari DocType Employee sebelum meneruskan ke
    :func:`sync_annual_payroll_history_for_bulan`.

    Iterasi setiap entri ``monthly_results`` berdasarkan field ``bulan`` dan
    delegasikan ke :func:`sync_annual_payroll_history_for_bulan`.

    Fungsi lama dengan parameter ``bulan`` tetap tersedia sebagai
    :func:`sync_annual_payroll_history_for_bulan` untuk kompatibilitas
    sementara."""

    monthly_results = monthly_results or []
    last_doc = None

    # Normalisasi data employee dan lengkapi company/employee_name jika perlu
    if isinstance(employee, str):
        employee_info = {"name": employee}
    elif isinstance(employee, dict):
        employee_info = dict(employee)
    else:
        employee_info = {
            "name": getattr(employee, "name", None),
            "company": getattr(employee, "company", None),
            "employee_name": getattr(employee, "employee_name", None),
        }

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

    # Proses setiap hasil bulanan secara terpisah agar fungsi lama dapat
    # melakukan validasi dan penyimpanan seperti sebelumnya.
    for idx, row in enumerate(monthly_results):
        bulan = row.get("bulan")
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

    # Jika tidak ada monthly_results, tetap panggil fungsi lama untuk
    # menangani summary/cancel/error_state.
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
    """Wrapper untuk kompatibilitas lama yang menerima parameter ``bulan``."""

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

    # Terima input ``employee`` dalam berbagai bentuk dan teruskan sebagai ID string
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
    """
    Sinkronisasi data hasil kalkulasi PPh21 TER ke Annual Payroll History dan child-nya.

    Fungsi ini menggunakan frappe.db.savepoint() untuk penanganan transaksi, namun
    tidak melakukan commit. Pemanggil harus mengelola commit/rollback sesuai kebutuhan.

    - Jika dokumen sudah ada untuk employee & fiscal_year, update.
    - Jika belum ada, create baru.
    - Jika salary_slip dicancel, hapus baris terkait pada child.
    - Perubahan akan di-rollback jika terjadi error setelah savepoint.
    - Salary Slip divalidasi dengan memeriksa docstatus dan keberadaannya.

    Args:
        employee: str atau dict/obj Employee (harus ada `name`)
        fiscal_year: str (misal "2025")
        bulan: int (1-12)
        monthly_results: list of dict, masing-masing dict punya keys:
            - bulan, bruto, pengurang_netto, biaya_jabatan, netto, pkp, rate, pph21, salary_slip
        summary: dict, optional, berisi field parent seperti:
            - bruto_total, netto_total, ptkp_annual, pkp_annual, pph21_annual, koreksi_pph21
        cancelled_salary_slip: str, optional, jika ingin menghapus baris berdasarkan salary_slip
        error_state: optional, struktur untuk menyimpan informasi error secara persisten

    Returns:
        str: Nama dokumen Annual Payroll History yang diupdate/dibuat, atau None jika gagal
    """
    # Extract employee name safely without assuming specific object structure
    # ``employee`` boleh langsung berupa string ID karyawan.
    employee_id = None
    if isinstance(employee, str) and employee:
        employee_id = employee
    elif isinstance(employee, dict) and "name" in employee:
        employee_id = employee["name"]
    elif hasattr(employee, "name"):
        employee_id = employee.name

    if not employee_id:
        # Strict validation to prevent processing with invalid employee data
        frappe.throw("Employee harus punya field 'name'!", title="Validation Error")
    
    # Validate fiscal year
    if not fiscal_year or not isinstance(fiscal_year, str):
        frappe.throw("Fiscal year harus berupa string valid", title="Validation Error")
        
    # Validate bulan
    if bulan is not None:
        try:
            bulan = cint(bulan)
            if bulan < 0 or bulan > 12:
                frappe.throw(f"Bulan '{bulan}' harus 0-12", title="Validation Error")
        except (ValueError, TypeError):
            frappe.throw(f"Bulan '{bulan}' harus berupa integer", title="Validation Error")

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

        # Process cancellations first
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

        # Process updates/additions
        if monthly_results:
            for row in monthly_results:
                if upsert_monthly_detail(history, row):
                    rows_updated += 1
                    
        # Persist provided error state for auditing
        if error_state is not None:
            history.set("error_state", frappe.as_json(error_state))

        # Skip saving only when no changes occurred, no summary provided, and no error state recorded
        if rows_updated == 0 and rows_deleted == 0 and error_state is None and not summary:
            frappe.logger().info(
                f"No rows updated, deleted, or summary provided in Annual Payroll History for {employee_id}, skipping save"
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
                f"for employee '{employee_id}', fiscal year {fiscal_year}, bulan {bulan} "
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
                f"Link validation error when saving Annual Payroll History for {employee_id}. "
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
