# Custom Salary Slip

`CustomSalarySlip` adalah turunan dari Doctype `Salary Slip` ERPNext yang menambahkan proses perhitungan PPh21 ketika slip digenerate.

## Integrasi PPh21

Kelas ini memanggil helper `calculate_pph21_TER` dan `calculate_pph21_TER_december` dari modul `config` untuk mengisi field `tax`, `tax_type`, serta `pph21_info` pada salary slip. Proses ini terjadi setiap kali salary slip dibuat melalui `Payroll Entry` atau saat disubmit ulang.

Fungsi `calculate_pph21_TER_december` menerima daftar salary slip selama satu
tahun penuh serta total PPh21 yang telah dibayar Januari-November. Nilai ini
digunakan untuk menghitung koreksi pajak pada bulan Desember.

## Mengaktifkan Override

Tambahkan mapping berikut pada `override_doctype_class` di `hooks.py` agar ERPNext menggunakan kelas ini:

```python
override_doctype_class = {
    "Salary Slip": "payroll_indonesia.override.salary_slip.CustomSalarySlip",
    "Payroll Entry": "payroll_indonesia.override.payroll_entry.CustomPayrollEntry",
}
```

Setelah disimpan jalankan perintah `bench clear-cache` dan `bench restart` di instance ERPNext.
