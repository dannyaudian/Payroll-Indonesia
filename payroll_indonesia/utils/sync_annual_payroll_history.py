import frappe


def get_or_create_annual_payroll_history(employee_name, fiscal_year, create_if_missing=True):
    """Ambil doc Annual Payroll History berdasarkan employee dan fiscal_year.

    Jika tidak ada dan ``create_if_missing`` bernilai ``True`` akan membuat doc baru.
    Bila ``create_if_missing`` ``False`` dan dokumen tidak ditemukan, kembalikan ``None``.
    """
    # Menggunakan frappe.db.exists untuk pengecekan cepat keberadaan dokumen
    doc_name = frappe.db.get_value(
        "Annual Payroll History",
        {"employee": employee_name, "fiscal_year": fiscal_year},
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
    
    # Set name ke kombinasi unik employee-fiscal_year jika skema doctype mendukung
    # Catatan: Ini hanya akan berhasil jika Annual Payroll History DocType dikonfigurasi
    # untuk menerima nama kustom (autoname: field:employee-field:fiscal_year atau prompt)
    history.name = f"{employee_name}-{fiscal_year}"
    
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

def upsert_monthly_detail(history, month_data):
    """
    Tambah atau update child (monthly_details) di Annual Payroll History.
    Unik berdasarkan bulan/salary_slip.
    Jika data dengan salary_slip/bulan sudah ada, update. Jika tidak, append baru.
    """
    month = month_data.get("bulan")
    salary_slip = month_data.get("salary_slip")
    # Cari child yang sama (by bulan atau salary_slip)
    found = None
    for detail in history.get("monthly_details", []):
        if (salary_slip and detail.salary_slip == salary_slip) or (month and detail.bulan == month):
            found = detail
            break
    if found:
        for k, v in month_data.items():
            if k in ["bulan", "bruto", "pengurang_netto", "biaya_jabatan", "netto", "pkp", "rate", "pph21", "salary_slip"]:
                found.set(k, v)
    else:
        detail = history.append("monthly_details", {})
        for k, v in month_data.items():
            if k in ["bulan", "bruto", "pengurang_netto", "biaya_jabatan", "netto", "pkp", "rate", "pph21", "salary_slip"]:
                detail.set(k, v)

def remove_monthly_detail_by_salary_slip(history, salary_slip):
    """
    Hapus baris child monthly_details berdasarkan nomor salary_slip.
    Biasanya dipakai saat slip gaji dicancel.
    """
    if not salary_slip:
        return
    to_remove = []
    for i, detail in enumerate(history.get("monthly_details", [])):
        if detail.salary_slip == salary_slip:
            to_remove.append(i)
    # Hapus dari belakang supaya index tidak bergeser
    for i in reversed(to_remove):
        history.monthly_details.pop(i)

def sync_annual_payroll_history(employee, fiscal_year, monthly_results=None, summary=None, cancelled_salary_slip=None):
    """
    Sinkronisasi data hasil kalkulasi PPh21 TER ke Annual Payroll History dan child-nya.
    - Jika dokumen sudah ada untuk employee & fiscal_year, update.
    - Jika belum ada, create baru.
    - Jika salary_slip dicancel, hapus baris terkait pada child.
    - Fungsi ini tidak melakukan ``frappe.db.commit``; transaksi ditangani oleh pemanggil.

    Args:
        employee: dict/obj Employee (harus ada `name`)
        fiscal_year: str (misal "2025")
        monthly_results: list of dict, masing-masing dict punya keys:
            - bulan, bruto, pengurang_netto, biaya_jabatan, netto, pkp, rate, pph21, salary_slip
        summary: dict, optional, berisi field parent seperti:
            - bruto_total, netto_total, ptkp_annual, pkp_annual, pph21_annual, koreksi_pph21
        cancelled_salary_slip: str, optional, jika ingin menghapus baris berdasarkan salary_slip
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

    only_cancel = cancelled_salary_slip and not monthly_results and not summary
    history = get_or_create_annual_payroll_history(
        employee_name, fiscal_year, create_if_missing=not only_cancel
    )

    if not history:
        return

    is_new_doc = history.is_new()

    # Cancel: hapus baris child berdasarkan salary_slip
    if cancelled_salary_slip:
        remove_monthly_detail_by_salary_slip(history, cancelled_salary_slip)

    # Update/append child (bulanan)
    if monthly_results:
        for row in monthly_results:
            upsert_monthly_detail(history, row)

    # Update summary/parent
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

    # Save with error handling
    try:
        # Log untuk debug
        frappe.logger().debug(
            f"[{frappe.session.user}] Saving Annual Payroll History '{history.name}' "
            f"for employee '{employee_name}', fiscal year {fiscal_year} "
            f"at {frappe.utils.now()}"
        )
        history.save(ignore_permissions=True)
        return history.name
    except Exception as e:
        frappe.log_error(
            message=f"Failed to save Annual Payroll History: {str(e)}",
            title="Annual Payroll History Save Error"
        )
        # Re-raise as a more specific error for better handling by the caller
        frappe.throw(f"Gagal menyimpan Annual Payroll History: {str(e)}")