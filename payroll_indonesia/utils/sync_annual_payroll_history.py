import frappe

def sync_annual_payroll_history(employee, fiscal_year, monthly_results, summary=None):
    """
    Sinkronisasi data hasil kalkulasi PPh21 TER ke Annual Payroll History dan child-nya.
    - Jika dokumen sudah ada untuk employee & fiscal_year, update.
    - Jika belum ada, create baru.

    Args:
        employee: dict/obj Employee (harus ada `name`)
        fiscal_year: str (misal "2025")
        monthly_results: list of dict, masing-masing dict punya keys:
            - bulan, bruto, pengurang_netto, biaya_jabatan, netto, pkp, rate, pph21, salary_slip
        summary: dict, optional, berisi field parent seperti:
            - bruto_total, netto_total, ptkp_annual, pkp_annual, pph21_annual, koreksi_pph21
    """
    employee_name = employee.get("name") if isinstance(employee, dict) else getattr(employee, "name", None)
    if not employee_name:
        raise Exception("Employee harus punya field 'name'!")

    # Cari/ciptakan dokumen Annual Payroll History
    doc = frappe.get_all(
        "Annual Payroll History",
        filters={"employee": employee_name, "fiscal_year": fiscal_year},
        fields=["name"]
    )
    doc_name = doc[0]["name"] if doc else None

    if doc_name:
        history = frappe.get_doc("Annual Payroll History", doc_name)
        history.set("monthly_details", [])
    else:
        history = frappe.new_doc("Annual Payroll History")
        history.employee = employee_name
        history.fiscal_year = fiscal_year

    # Set field summary (parent)
    if summary:
        for k, v in summary.items():
            if hasattr(history, k):
                setattr(history, k, v)
            else:
                history.set(k, v)

    # Tambah child (bulanan)
    for row in monthly_results:
        detail = history.append("monthly_details", {})
        for k, v in row.items():
            if k in ["bulan", "bruto", "pengurang_netto", "biaya_jabatan", "netto", "pkp", "rate", "pph21", "salary_slip"]:
                detail.set(k, v)

    history.save(ignore_permissions=True)
    frappe.db.commit()
    return history.name