# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 00:34:47 by dannyaudian

"""
Utilitas pusat untuk modul Payroll Indonesia.

Modul ini menyediakan fungsi-fungsi umum yang digunakan oleh berbagai
komponen Payroll Indonesia, dengan fokus pada pemisahan konfigurasi
dan logika bisnis.
"""

import logging
import os
from typing import Dict, Any, List, Optional, Union, Tuple, cast

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, now_datetime

from payroll_indonesia.config import get_live_config
from payroll_indonesia.frappe_helpers import (
    safe_execute,
    ensure_doc_exists,
    doc_exists
)

# Konfigurasi logger
logger = logging.getLogger('payroll_utils')


# =========== FUNGSI AKUN DAN GL ===========

@safe_execute(default_value=None, log_exception=True)
def get_or_create_account(
    company: str,
    account_name: str,
    account_type: str = "Payable",
    is_group: int = 0,
    root_type: Optional[str] = None
) -> Optional[str]:
    """
    Mendapatkan atau membuat akun GL jika belum ada.
    
    Args:
        company: Nama perusahaan
        account_name: Nama akun tanpa awalan perusahaan
        account_type: Tipe akun (Payable, Expense, dll)
        is_group: Apakah akun adalah grup (1) atau bukan (0)
        root_type: Tipe root (akan ditentukan dari account_type jika None)
        
    Returns:
        str: Nama akun lengkap, None jika gagal
    """
    # Validasi parameter
    if not company or not account_name:
        logger.error("Company dan account_name wajib diisi")
        return None
    
    # Dapatkan abbreviation perusahaan
    abbr = frappe.get_cached_value("Company", company, "abbr")
    if not abbr:
        logger.error(f"Perusahaan {company} tidak memiliki abbreviation")
        return None
    
    # Buat nama akun lengkap
    full_account_name = f"{account_name} - {abbr}"
    
    # Cek jika akun sudah ada
    if frappe.db.exists("Account", full_account_name):
        logger.info(f"Akun {full_account_name} sudah ada")
        return full_account_name
    
    # Tentukan root_type jika tidak diberikan
    if not root_type:
        if account_type in ["Payable", "Tax", "Receivable"]:
            root_type = "Liability"
        elif account_type in ["Expense", "Expense Account"]:
            root_type = "Expense"
        elif account_type in ["Income", "Income Account"]:
            root_type = "Income"
        elif account_type == "Asset":
            root_type = "Asset"
        else:
            root_type = "Liability"  # Default
    
    # Cari parent account
    parent = find_parent_account(company, account_type, root_type)
    if not parent:
        logger.error(
            f"Tidak dapat menemukan parent account untuk {account_name}"
        )
        return None
    
    # Buat objek akun
    account_data = {
        "doctype": "Account",
        "account_name": account_name,
        "company": company,
        "parent_account": parent,
        "is_group": cint(is_group),
        "root_type": root_type,
        "account_currency": frappe.get_cached_value(
            "Company", company, "default_currency"
        ),
    }
    
    # Tambahkan account_type untuk non-group accounts
    if not is_group and account_type:
        account_data["account_type"] = account_type
    
    # Buat akun
    try:
        doc = frappe.get_doc(account_data)
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        logger.info(f"Berhasil membuat akun: {full_account_name}")
        return full_account_name
    except Exception as e:
        logger.error(f"Gagal membuat akun {full_account_name}: {str(e)}")
        return None


@safe_execute(default_value=None, log_exception=True)
def find_parent_account(
    company: str,
    account_type: str,
    root_type: Optional[str] = None
) -> Optional[str]:
    """
    Mencari parent account yang sesuai berdasarkan tipe.
    
    Args:
        company: Nama perusahaan
        account_type: Tipe akun (Payable, Expense, dll)
        root_type: Tipe root (akan ditentukan dari account_type jika None)
        
    Returns:
        str: Nama parent account, None jika tidak ditemukan
    """
    # Tentukan root_type jika tidak diberikan
    if not root_type:
        if account_type in ["Payable", "Tax", "Receivable"]:
            root_type = "Liability"
        elif account_type in ["Expense", "Expense Account"]:
            root_type = "Expense"
        elif account_type in ["Income", "Income Account"]:
            root_type = "Income"
        elif account_type == "Asset":
            root_type = "Asset"
        else:
            root_type = "Liability"  # Default
    
    # Dapatkan abbreviation perusahaan
    abbr = frappe.get_cached_value("Company", company, "abbr")
    if not abbr:
        logger.error(f"Perusahaan {company} tidak memiliki abbreviation")
        return None
    
    # Dapatkan kandidat dari konfigurasi
    config = get_live_config()
    parent_candidates = config.get("parent_accounts", {}).get(root_type, [])
    
    # Gunakan default jika tidak ada di konfigurasi
    if not parent_candidates:
        if root_type == "Liability":
            parent_candidates = [
                "Duties and Taxes", "Current Liabilities", "Accounts Payable"
            ]
        elif root_type == "Expense":
            parent_candidates = [
                "Direct Expenses", "Indirect Expenses", "Expenses"
            ]
        elif root_type == "Income":
            parent_candidates = ["Income", "Direct Income", "Indirect Income"]
        elif root_type == "Asset":
            parent_candidates = ["Current Assets", "Fixed Assets"]
        else:
            parent_candidates = []
    
    # Cari parent account dari kandidat
    for candidate in parent_candidates:
        # Cek nama akun persis
        account = frappe.db.get_value(
            "Account",
            {
                "account_name": candidate,
                "company": company,
                "is_group": 1
            },
            "name"
        )
        
        if account:
            return account
        
        # Cek dengan suffix perusahaan
        account_with_suffix = f"{candidate} - {abbr}"
        if frappe.db.exists("Account", account_with_suffix):
            return account_with_suffix
    
    # Fallback: cari akun grup dengan root_type yang sesuai
    accounts = frappe.get_all(
        "Account",
        filters={
            "company": company,
            "is_group": 1,
            "root_type": root_type
        },
        order_by="lft",
        limit=1
    )
    
    if accounts:
        return accounts[0].name
    
    # Ultimate fallback: gunakan akun root perusahaan
    root_accounts = {
        "Asset": "Application of Funds (Assets)",
        "Liability": "Source of Funds (Liabilities)",
        "Expense": "Expenses",
        "Income": "Income",
        "Equity": "Equity"
    }
    
    root_account = root_accounts.get(root_type)
    if root_account:
        full_name = f"{root_account} - {abbr}"
        if frappe.db.exists("Account", full_name):
            return full_name
    
    return None


# =========== FUNGSI BPJS ===========

@safe_execute(default_value={}, log_exception=True)
def hitung_bpjs(gaji: float) -> Dict[str, Any]:
    """
    Menghitung kontribusi BPJS berdasarkan gaji.
    
    Args:
        gaji: Gaji pokok
        
    Returns:
        dict: Detail kontribusi BPJS
    """
    # Validasi input
    gaji = flt(gaji)
    if gaji < 0:
        logger.warning("Nilai gaji negatif, menggunakan nilai absolut")
        gaji = abs(gaji)
    
    # Dapatkan persentase BPJS dari konfigurasi
    config = get_live_config()
    bpjs_config = config.get('bpjs', {})
    
    # BPJS Kesehatan
    kesehatan_employee = flt(bpjs_config.get('kesehatan_employee_percent', 1.0))
    kesehatan_employer = flt(bpjs_config.get('kesehatan_employer_percent', 4.0))
    kesehatan_max = flt(bpjs_config.get('kesehatan_max_salary', 12000000))
    
    # BPJS Ketenagakerjaan - JHT
    jht_employee = flt(bpjs_config.get('jht_employee_percent', 2.0))
    jht_employer = flt(bpjs_config.get('jht_employer_percent', 3.7))
    
    # BPJS Ketenagakerjaan - JP
    jp_employee = flt(bpjs_config.get('jp_employee_percent', 1.0))
    jp_employer = flt(bpjs_config.get('jp_employer_percent', 2.0))
    jp_max = flt(bpjs_config.get('jp_max_salary', 9077600))
    
    # BPJS Ketenagakerjaan - JKK dan JKM
    jkk = flt(bpjs_config.get('jkk_percent', 0.24))
    jkm = flt(bpjs_config.get('jkm_percent', 0.3))
    
    # Batasi gaji dengan maksimum yang diatur
    kesehatan_gaji = min(gaji, kesehatan_max)
    jp_gaji = min(gaji, jp_max)
    
    # Hitung kontribusi
    kesehatan_karyawan = kesehatan_gaji * (kesehatan_employee / 100)
    kesehatan_perusahaan = kesehatan_gaji * (kesehatan_employer / 100)
    
    jht_karyawan = gaji * (jht_employee / 100)
    jht_perusahaan = gaji * (jht_employer / 100)
    
    jp_karyawan = jp_gaji * (jp_employee / 100)
    jp_perusahaan = jp_gaji * (jp_employer / 100)
    
    jkk_nilai = gaji * (jkk / 100)
    jkm_nilai = gaji * (jkm / 100)
    
    # Hasil
    return {
        "kesehatan": {
            "karyawan": kesehatan_karyawan,
            "perusahaan": kesehatan_perusahaan,
            "total": kesehatan_karyawan + kesehatan_perusahaan
        },
        "ketenagakerjaan": {
            "jht": {
                "karyawan": jht_karyawan,
                "perusahaan": jht_perusahaan,
                "total": jht_karyawan + jht_perusahaan
            },
            "jp": {
                "karyawan": jp_karyawan,
                "perusahaan": jp_perusahaan,
                "total": jp_karyawan + jp_perusahaan
            },
            "jkk": jkk_nilai,
            "jkm": jkm_nilai
        },
        "total_karyawan": (
            kesehatan_karyawan + jht_karyawan + jp_karyawan
        ),
        "total_perusahaan": (
            kesehatan_perusahaan + jht_perusahaan + 
            jp_perusahaan + jkk_nilai + jkm_nilai
        )
    }


@safe_execute(default_value=False, log_exception=True)
def validate_bpjs_limits(
    component: str,
    value: float,
    field_type: str = "percentage"
) -> bool:
    """
    Validasi nilai parameter BPJS berdasarkan batas konfigurasi.
    
    Args:
        component: Komponen BPJS (kesehatan_employee, jht_employer, dll)
        value: Nilai untuk divalidasi
        field_type: Tipe nilai (percentage atau max_salary)
        
    Returns:
        bool: True jika valid, False jika tidak
    """
    # Dapatkan batas dari konfigurasi
    config = get_live_config()
    bpjs_config = config.get('bpjs', {})
    validation = bpjs_config.get('validation', {})
    
    if field_type == "percentage":
        limits = validation.get('percentage_limits', {})
        component_limits = limits.get(component, {})
        
        min_val = component_limits.get('min', 0)
        max_val = component_limits.get('max', 100)
        
        return min_val <= flt(value) <= max_val
    elif field_type == "max_salary":
        limits = validation.get('salary_limits', {})
        component_limits = limits.get(component, {})
        
        min_val = component_limits.get('min', 0)
        max_val = component_limits.get('max', float('inf'))
        
        return min_val <= flt(value) <= max_val
    
    return True


# =========== FUNGSI PAJAK (PPH 21) ===========

@safe_execute(default_value=None, log_exception=True)
def get_ptkp_value(status_pajak: str) -> Optional[float]:
    """
    Mendapatkan nilai PTKP berdasarkan status pajak.
    
    Args:
        status_pajak: Kode status pajak (TK0, K1, dll)
        
    Returns:
        float: Nilai PTKP tahunan, None jika tidak ditemukan
    """
    # Dapatkan nilai PTKP dari konfigurasi
    config = get_live_config()
    ptkp_values = config.get('ptkp', {})
    
    # Jika status pajak ada di konfigurasi, gunakan nilai dari sana
    if status_pajak in ptkp_values:
        return flt(ptkp_values[status_pajak])
    
    # Jika tidak ada di konfigurasi, gunakan nilai default
    default_values = {
        "TK0": 54000000,
        "TK1": 58500000,
        "TK2": 63000000,
        "TK3": 67500000,
        "K0": 58500000,
        "K1": 63000000,
        "K2": 67500000,
        "K3": 72000000,
        "HB0": 112500000,
        "HB1": 117000000,
        "HB2": 121500000,
        "HB3": 126000000
    }
    
    return flt(default_values.get(status_pajak))


@safe_execute(default_value=[], log_exception=True)
def get_tax_brackets() -> List[Dict[str, Any]]:
    """
    Mendapatkan lapisan pajak progresif PPh 21.
    
    Returns:
        list: Daftar lapisan pajak dengan income_from, income_to, dan tax_rate
    """
    # Dapatkan lapisan pajak dari konfigurasi
    config = get_live_config()
    brackets = config.get('tax_brackets', [])
    
    # Jika ada di konfigurasi, urutkan dan gunakan
    if brackets:
        # Urutkan berdasarkan income_from
        return sorted(brackets, key=lambda x: x["income_from"])
    
    # Jika tidak ada di konfigurasi, gunakan nilai default
    return [
        {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
        {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
        {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
        {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
        {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
    ]


@safe_execute(default_value="TER C", log_exception=True)
def get_ter_category(status_pajak: str) -> str:
    """
    Memetakan status PTKP ke kategori TER.
    
    Args:
        status_pajak: Kode status pajak (TK0, K1, dll)
        
    Returns:
        str: Kategori TER ("TER A", "TER B", atau "TER C")
    """
    # Dapatkan pemetaan dari konfigurasi
    config = get_live_config()
    ptkp_to_ter = config.get('ptkp_to_ter_mapping', {})
    
    # Jika ada di konfigurasi, gunakan
    if status_pajak in ptkp_to_ter:
        return ptkp_to_ter[status_pajak]
    
    # Jika tidak ada di konfigurasi, gunakan logika default
    prefix = status_pajak[:2] if len(status_pajak) >= 2 else status_pajak
    suffix = status_pajak[2:] if len(status_pajak) >= 3 else "0"
    
    if status_pajak == "TK0":
        return "TER A"
    elif prefix == "TK" and suffix in ["1", "2", "3"]:
        return "TER B"
    elif prefix == "K" and suffix == "0":
        return "TER B"
    elif prefix == "K" and suffix in ["1", "2", "3"]:
        return "TER C"
    elif prefix == "HB":  # Single parent
        return "TER C"
    
    # Default: kategori tertinggi
    return "TER C"


@safe_execute(default_value=0.0, log_exception=True)
def calculate_ter(status_pajak: str, penghasilan: float) -> float:
    """
    Menghitung tarif pajak TER (Tarif Efektif Rata-rata).
    
    Args:
        status_pajak: Kode status pajak (TK0, K1, dll)
        penghasilan: Penghasilan bruto
        
    Returns:
        float: TER rate dalam desimal (mis. 0.05 untuk 5%)
    """
    # Validasi input
    penghasilan = flt(penghasilan)
    if penghasilan <= 0:
        return 0.0
    
    # Dapatkan kategori TER
    ter_category = get_ter_category(status_pajak)
    
    # Dapatkan tarif TER dari konfigurasi
    config = get_live_config()
    ter_rates = config.get('ter_rates', {}).get(ter_category, [])
    
    # Jika ada tarif di konfigurasi, cari yang sesuai
    if ter_rates:
        # Urutkan tarif berdasarkan income_from (descending)
        sorted_rates = sorted(
            ter_rates, key=lambda x: x.get("income_from", 0), reverse=True
        )
        
        # Cari tarif yang sesuai
        for rate_data in sorted_rates:
            income_from = flt(rate_data.get("income_from", 0))
            income_to = flt(rate_data.get("income_to", 0))
            is_highest = rate_data.get("is_highest_bracket", False)
            
            if penghasilan >= income_from and (
                is_highest or income_to == 0 or penghasilan < income_to
            ):
                return flt(rate_data.get("rate", 0)) / 100.0
    
    # Jika tidak ada di konfigurasi, gunakan tarif default
    default_rates = {
        "TER A": 0.05,  # 5%
        "TER B": 0.10,  # 10%
        "TER C": 0.15   # 15%
    }
    
    return default_rates.get(ter_category, 0.15)


@safe_execute(default_value=False, log_exception=True)
def should_use_ter(is_december: bool = False) -> bool:
    """
    Mengecek apakah metode TER harus digunakan berdasarkan konfigurasi.
    
    Args:
        is_december: Apakah ini slip gaji bulan Desember
        
    Returns:
        bool: True jika gunakan TER, False jika gunakan Progresif
    """
    # Jika Desember, selalu gunakan Progresif
    if is_december:
        logger.info("Bulan Desember, menggunakan perhitungan Progresif")
        return False
    
    # Dapatkan konfigurasi TER
    config = get_live_config()
    tax_config = config.get('tax', {})
    
    calculation_method = tax_config.get('tax_calculation_method', 'Progressive')
    use_ter = cint(tax_config.get('use_ter', 0))
    
    # Gunakan TER jika keduanya sesuai
    return calculation_method == 'TER' and use_ter == 1


@safe_execute(default_value=0.0, log_exception=True)
def calculate_biaya_jabatan(gross_pay: float) -> float:
    """
    Menghitung biaya jabatan berdasarkan aturan pajak.
    
    Args:
        gross_pay: Penghasilan bruto
        
    Returns:
        float: Nilai biaya jabatan
    """
    # Dapatkan parameter dari konfigurasi
    config = get_live_config()
    tax_config = config.get('tax', {})
    
    percent = flt(tax_config.get('biaya_jabatan_percent', 5.0))
    max_value = flt(tax_config.get('biaya_jabatan_max', 500000.0))
    
    # Hitung biaya jabatan
    biaya_jabatan = gross_pay * (percent / 100)
    
    # Batasi dengan nilai maksimum
    if biaya_jabatan > max_value:
        biaya_jabatan = max_value
    
    return biaya_jabatan


@safe_execute(default_value=0.0, log_exception=True)
def calculate_progressive_tax(
    netto_yearly: float,
    ptkp: float
) -> float:
    """
    Menghitung PPh 21 dengan metode progresif.
    
    Args:
        netto_yearly: Penghasilan netto tahunan
        ptkp: Nilai PTKP tahunan
        
    Returns:
        float: Pajak tahunan
    """
    # Hitung PKP (Penghasilan Kena Pajak)
    pkp = max(0, netto_yearly - ptkp)
    if pkp <= 0:
        return 0.0
    
    # Dapatkan lapisan pajak
    brackets = get_tax_brackets()
    
    # Hitung pajak per lapisan
    tax = 0.0
    remaining_income = pkp
    
    for bracket in brackets:
        income_from = flt(bracket["income_from"])
        income_to = flt(bracket["income_to"])
        rate = flt(bracket["tax_rate"]) / 100.0
        
        # Lapisan terakhir
        if income_to == 0 or income_to > remaining_income:
            tax += remaining_income * rate
            break
        
        # Lapisan tengah
        taxable_in_bracket = income_to - income_from
        if remaining_income <= taxable_in_bracket:
            tax += remaining_income * rate
            break
        else:
            tax += taxable_in_bracket * rate
            remaining_income -= taxable_in_bracket
    
    return tax


# =========== FUNGSI UTILITAS UMUM ===========

@safe_execute(default_value=None, log_exception=True)
def get_settings():
    """
    Mendapatkan dokumen Payroll Indonesia Settings.
    
    Returns:
        Dokumen settings atau None jika error
    """
    settings_name = "Payroll Indonesia Settings"
    
    if not doc_exists(settings_name, settings_name):
        # Buat settings default jika belum ada
        settings = create_default_settings()
    else:
        settings = frappe.get_doc(settings_name, settings_name)
    
    return settings


@safe_execute(default_value=None, log_exception=True)
def create_default_settings():
    """
    Membuat Payroll Indonesia Settings default.
    
    Returns:
        Dokumen settings yang dibuat
    """
    # Dapatkan konfigurasi default
    config = get_live_config()
    
    # Ekstrak nilai dengan default
    bpjs = config.get('bpjs', {})
    tax = config.get('tax', {})
    defaults = config.get('defaults', {})
    
    settings = frappe.get_doc({
        "doctype": "Payroll Indonesia Settings",
        "app_version": "1.0.0",
        "app_last_updated": now_datetime(),
        "app_updated_by": frappe.session.user,
        
        # BPJS defaults
        "kesehatan_employee_percent": bpjs.get("kesehatan_employee_percent", 1.0),
        "kesehatan_employer_percent": bpjs.get("kesehatan_employer_percent", 4.0),
        "kesehatan_max_salary": bpjs.get("kesehatan_max_salary", 12000000.0),
        "jht_employee_percent": bpjs.get("jht_employee_percent", 2.0),
        "jht_employer_percent": bpjs.get("jht_employer_percent", 3.7),
        "jp_employee_percent": bpjs.get("jp_employee_percent", 1.0),
        "jp_employer_percent": bpjs.get("jp_employer_percent", 2.0),
        "jp_max_salary": bpjs.get("jp_max_salary", 9077600.0),
        "jkk_percent": bpjs.get("jkk_percent", 0.24),
        "jkm_percent": bpjs.get("jkm_percent", 0.3),
        
        # Tax defaults
        "biaya_jabatan_percent": tax.get("biaya_jabatan_percent", 5.0),
        "biaya_jabatan_max": tax.get("biaya_jabatan_max", 500000.0),
        "tax_calculation_method": tax.get("tax_calculation_method", "TER"),
        "use_ter": tax.get("use_ter", 1),
        
        # Default settings
        "default_currency": defaults.get("currency", "IDR"),
        "payroll_frequency": defaults.get("payroll_frequency", "Monthly"),
        "max_working_days_per_month": defaults.get("max_working_days", 22),
        "working_hours_per_day": defaults.get("working_hours", 8),
    })
    
    # Insert dengan bypass permission
    settings.flags.ignore_permissions = True
    settings.flags.ignore_mandatory = True
    settings.insert(ignore_permissions=True)
    
    frappe.db.commit()
    return settings


@safe_execute(default_value=None, log_exception=True)
def get_employee_details(employee_id: str) -> Optional[Dict[str, Any]]:
    """
    Mendapatkan detail karyawan dengan data pajak dan BPJS.
    
    Args:
        employee_id: ID karyawan
        
    Returns:
        dict: Detail karyawan, None jika tidak ditemukan
    """
    # Pastikan karyawan ada
    if not frappe.db.exists("Employee", employee_id):
        logger.warning(f"Karyawan {employee_id} tidak ditemukan")
        return None
    
    # Ambil dokumen karyawan
    employee = frappe.get_doc("Employee", employee_id)
    
    # Ekstrak informasi yang relevan
    result = {
        "name": employee.name,
        "employee_name": employee.employee_name,
        "company": employee.company,
        "department": employee.department,
        "designation": employee.designation,
        "status_pajak": getattr(employee, "status_pajak", "TK0"),
        "npwp": getattr(employee, "npwp", ""),
        "ktp": getattr(employee, "ktp", ""),
        "ikut_bpjs_kesehatan": cint(
            getattr(employee, "ikut_bpjs_kesehatan", 1)
        ),
        "ikut_bpjs_ketenagakerjaan": cint(
            getattr(employee, "ikut_bpjs_ketenagakerjaan", 1)
        ),
    }
    
    return result


def get_month_name(month: int) -> str:
    """
    Mendapatkan nama bulan dari nomor bulan.
    
    Args:
        month: Nomor bulan (1-12)
        
    Returns:
        str: Nama bulan
    """
    month_names = [
        "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ]
    
    if 1 <= month <= 12:
        return month_names[month - 1]
    
    return f"Bulan {month}"
