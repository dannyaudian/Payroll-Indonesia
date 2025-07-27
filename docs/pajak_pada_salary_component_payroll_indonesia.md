# 📘 Pajak pada Salary Component Payroll Indonesia

Dokumen ini menjelaskan arti dan penggunaan berbagai flag/field pada `Salary Component` dalam modul Payroll Indonesia. Sumber utama adalah file fixture [`salary_component.json`](../payroll_indonesia/fixtures/salary_component.json). Pengetahuan ini membantu developer maupun admin payroll memastikan perhitungan PPh 21 selalu konsisten dengan konfigurasi komponen gaji.

## Flag pada Komponen **Earning**

| Field/Flag | Deskripsi Singkat | Pengaruh PPh 21 |
|------------|------------------|-----------------|
| `is_tax_applicable` | 1 jika nilai komponen menambah penghasilan bruto. | Menambah bruto |
| `depends_on_payment_days` | 1 artinya nominal prorata kehadiran/hari kerja. | Menyesuaikan nominal |
| `round_to_the_nearest_integer` | Membulatkan hasil ke integer terdekat. | Tidak langsung |
| `statistical_component` | 1 berarti hanya untuk statistik, tidak ikut perhitungan. | Tidak berpengaruh |
| `do_not_include_in_total` | 1 maka tidak dijumlah pada total earning di slip. | Tidak berpengaruh |
| `remove_if_zero_valued` | Baris di slip dihapus jika nilainya 0. | Administratif |
| `disabled` | 1 menonaktifkan komponen sepenuhnya. | Tidak dihitung |

## Flag pada Komponen **Deduction**

| Field/Flag | Deskripsi Singkat | Pengaruh PPh 21 |
|------------|------------------|-----------------|
| `depends_on_payment_days` | 1 jika prorata kehadiran/hari kerja. | Menyesuaikan nominal |
| `is_income_tax_component` | 1 menjadikan deduction pengurang penghasilan netto. | Mengurangi netto |
| `round_to_the_nearest_integer` | Membulatkan hasil ke integer terdekat. | Tidak langsung |
| `statistical_component` | 1 hanya untuk catatan, tidak memengaruhi perhitungan. | Tidak berpengaruh |
| `do_not_include_in_total` | 1 tidak ikut total deduction di slip. | Tidak berpengaruh |
| `remove_if_zero_valued` | Baris dihapus jika nilainya 0. | Administratif |
| `disabled` | 1 menonaktifkan komponen sepenuhnya. | Tidak dihitung |

## Contoh Penggunaan

### Natura Dikecualikan dari Pajak
```json
{
    "name": "Makan di Kantor",
    "salary_component": "Makan di Kantor",
    "salary_component_abbr": "MK",
    "type": "Earning",
    "description": "Makanan/minuman di tempat kerja (dikecualikan dari PPh 21 sesuai PMK 66/2023)",
    "depends_on_payment_days": 1,
    "is_tax_applicable": 0,
    "statistical_component": 0,
    "do_not_include_in_total": 0,
    "remove_if_zero_valued": 1,
    "round_to_the_nearest_integer": 1,
    "disabled": 0
}
```

### Natura Dikenakan Pajak
```json
{
    "name": "Asuransi Tambahan",
    "salary_component": "Asuransi Tambahan",
    "salary_component_abbr": "AT",
    "type": "Earning",
    "description": "Asuransi tambahan non-BPJS (natura yang dikenakan PPh 21)",
    "depends_on_payment_days": 0,
    "is_tax_applicable": 1,
    "statistical_component": 0,
    "do_not_include_in_total": 0,
    "remove_if_zero_valued": 1,
    "round_to_the_nearest_integer": 1,
    "disabled": 0
}
```

### Komponen Penambah Bruto
```json
{
    "name": "Tunjangan Transport",
    "salary_component": "Tunjangan Transport",
    "salary_component_abbr": "TT",
    "type": "Earning",
    "description": "Tunjangan transportasi",
    "depends_on_payment_days": 1,
    "is_tax_applicable": 1,
    "statistical_component": 0,
    "do_not_include_in_total": 0,
    "remove_if_zero_valued": 1,
    "round_to_the_nearest_integer": 1,
    "disabled": 0
}
```

### Komponen Pengurang Netto
```json
{
    "name": "BPJS Kesehatan Employee",
    "salary_component": "BPJS Kesehatan Employee",
    "salary_component_abbr": "BPJS KES-EE",
    "type": "Deduction",
    "description": "Potongan BPJS Kesehatan 1% dari karyawan",
    "depends_on_payment_days": 1,
    "statistical_component": 0,
    "do_not_include_in_total": 0,
    "remove_if_zero_valued": 1,
    "is_income_tax_component": 1,
    "round_to_the_nearest_integer": 1,
    "disabled": 0,
    "formula": "min(base, get_bpjs_cap(\"bpjs_health_employee_cap\")) * get_bpjs_rate(\"bpjs_health_employee_rate\") / 100"
}
```

### Komponen Statistik
```json
{
    "name": "Kendaraan Dinas",
    "salary_component": "Kendaraan Dinas",
    "salary_component_abbr": "KD",
    "type": "Earning",
    "description": "Mobil dinas pribadi (natura yang dikenakan PPh 21)",
    "depends_on_payment_days": 1,
    "is_tax_applicable": 1,
    "statistical_component": 1,
    "do_not_include_in_total": 1,
    "remove_if_zero_valued": 1,
    "round_to_the_nearest_integer": 1,
    "disabled": 0
}
```

## Cara Utility PPh 21 Menggunakan Flag

Fungsi `sum_taxable_earnings` dan `sum_income_tax_deductions` pada [`pph21_ter.py`](../payroll_indonesia/config/pph21_ter.py) membaca flag di setiap baris slip gaji. Komponen baru tidak perlu ditambah di kode, cukup isi field pada `salary_component.json`.

```python
for row in salary_slip.get("earnings", []):
    if (
        row.get("is_tax_applicable", 0) == 1
        and row.get("do_not_include_in_total", 0) == 0
        and row.get("statistical_component", 0) == 0
    ):
        total += flt(row.amount)
```

Dengan pendekatan ini, logika PPh 21 selalu konsisten dengan konfigurasi Salary Component.

