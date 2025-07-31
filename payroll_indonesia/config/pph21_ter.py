import frappe
from frappe import ValidationError
from frappe.utils import flt
from payroll_indonesia.config import (
    get_ptkp_amount,
    get_ter_code,
    get_ter_rate,
    get_biaya_jabatan_rate,
    get_biaya_jabatan_cap_monthly,
)
from payroll_indonesia.utils import round_half_up

PENGURANG_NETTO_NAMES = {
    "bpjs kesehatan employee",   # 1 % karyawan
    "bpjs jht employee",         # 2 % karyawan
    "bpjs jp employee",          # 1 % karyawan
    # tambahkan jika ada iuran pensiun lain:
    "iuran pensiun",
    "dana pensiun",
}

def sum_bruto_earnings(salary_slip):
    """
    Sum all earning components contributing to bruto pay (including taxable natura).
    Criteria:
      - is_tax_applicable = 1
      - OR is_income_tax_component = 1
      - OR variable_based_on_taxable_salary = 1
      - do_not_include_in_total = 0
      - statistical_component = 0
      - exempted_from_income_tax = 0 (if field exists)
    """
    total = 0.0
    earnings = salary_slip.get("earnings", [])
    for row in earnings:
        if (
            (row.get("is_tax_applicable", 0) == 1 or
             row.get("is_income_tax_component", 0) == 1 or
             row.get("variable_based_on_taxable_salary", 0) == 1)
            and row.get("do_not_include_in_total", 0) == 0
            and row.get("statistical_component", 0) == 0
            and row.get("exempted_from_income_tax", 0) == 0
        ):
            total += flt(row.get("amount", 0))
    return total

def sum_pengurang_netto(slip):
    """
    Total pengurang netto:
      • baris deduction ber-flag is_pengurang_netto = 1  ──► fleksibel
      • ATAU nama komponen ada di PENGURANG_NETTO_NAMES
    Abaikan baris 'Biaya Jabatan'.
    """
    total = 0.0
    for row in slip.get("deductions", []):
        if "biaya jabatan" in (row.get("salary_component") or "").lower():
            continue
        if (
            row.get("is_pengurang_netto", 0) == 1
            or (row.get("salary_component") or "").lower() in PENGURANG_NETTO_NAMES
        ):
            total += flt(row.get("amount", 0))
    return total

def get_biaya_jabatan_from_component(salary_slip):
    """
    Get 'Biaya Jabatan' deduction from salary slip, return 0 if not present.
    """
    deductions = salary_slip.get("deductions", [])
    for row in deductions:
        if "biaya jabatan" in row.get("salary_component", "").lower():
            return flt(row.get("amount", 0))
    return 0.0

def calculate_pph21_TER(employee_doc, slip):
    """
    Hitung PPh-21 metode TER (varian: tarif × bruto).
    Mengembalikan dict lengkap utk debugging / tampilan.
    """
    # 0. Validasi jenis kepegawaian
    emp_type = (
        employee_doc["employment_type"]
        if isinstance(employee_doc, dict)
        else employee_doc.employment_type
    )
    if emp_type != "Full-time":
        return {"employment_type_checked": False, "pph21": 0.0}

    # 1. Bruto
    bruto = sum_bruto_earnings(slip)

    # 2. Biaya jabatan (info saja)
    bj_rate = get_biaya_jabatan_rate()
    bj_cap = get_biaya_jabatan_cap_monthly()
    biaya_jabatan = get_biaya_jabatan_from_component(slip) or min(
        bruto * bj_rate / 100, bj_cap
    )

    # 3. Pengurang netto & netto
    pengurang_netto = sum_pengurang_netto(slip)
    netto = bruto - biaya_jabatan - pengurang_netto

    # 4. PTKP & PKP (hanya info)
    ptkp = flt(get_ptkp_amount(employee_doc) / 12)
    pkp = max(netto - ptkp, 0)

    # 5. Tarif TER (lookup pakai BRUTO)
    ter_code = get_ter_code(employee_doc)
    try:
        rate = get_ter_rate(ter_code, bruto)
    except ValidationError as e:
        frappe.logger().warning(str(e))
        rate = 0.0

    # 6. Pajak = BRUTO × rate %
    pph21 = round_half_up(bruto * rate / 100)

    # 7. Return
    return {
        "ptkp": ptkp,
        "bruto": bruto,
        "pengurang_netto": pengurang_netto,
        "biaya_jabatan": biaya_jabatan,
        "netto": netto,
        "pkp": pkp,
        "rate": rate,
        "pph21": pph21,
        "employment_type_checked": True,
    }