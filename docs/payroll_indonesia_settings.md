# Payroll Indonesia Settings

Modul ini menyimpan semua konfigurasi penggajian sesuai regulasi Indonesia seperti PPh 21, BPJS, PTKP, dan metode TER. Semua pengaturan bersifat **dinamis**, terpusat, dan terhubung dengan `Salary Component`, `Salary Slip`, dan `Income Tax Slab`.

---

## 1. General Settings

| Fieldname                         | Fieldtype                   | Description |
| --------------------------------- | --------------------------- | ----------- |
| `pph21_method`                    | Select (`TER`, `Progresif`) | Metode perhitungan PPh 21 default |
| `validate_tax_status_strict`      | Check                       | Validasi `tax_status` terhadap PTKP table |
| `salary_slip_use_component_cache` | Check                       | Aktifkan cache komponen Salary Slip |
| `auto_queue_salary_slip`          | Check                       | Salary Slip diproses via background job |

---

## 2. BPJS Settings

Semua rate BPJS + batas maksimal (cap) ditentukan di sini, digunakan langsung dalam formula komponen gaji:

| Fieldname                    | Fieldtype | Description |
|-----------------------------|-----------|-------------|
| `bpjs_health_employer_rate`  | Float     | % iuran BPJS Kesehatan (Perusahaan) |
| `bpjs_health_employer_cap`   | Currency  | Plafon gaji kena iuran (Perusahaan) |
| `bpjs_health_employee_rate`  | Float     | % iuran BPJS Kesehatan (Karyawan) |
| `bpjs_health_employee_cap`   | Currency  | Plafon gaji kena iuran (Karyawan) |
| `bpjs_jht_employer_rate`     | Float     | % JHT (Perusahaan) |
| `bpjs_jht_employer_cap`      | Currency  | Plafon JHT (Perusahaan) |
| `bpjs_jht_employee_rate`     | Float     | % JHT (Karyawan) |
| `bpjs_jht_employee_cap`      | Currency  | Plafon JHT (Karyawan) |
| `bpjs_jkk_rate`              | Float     | % JKK |
| `bpjs_jkk_cap`               | Currency  | Plafon JKK |
| `bpjs_jkm_rate`              | Float     | % JKM |
| `bpjs_jkm_cap`               | Currency  | Plafon JKM |
| `bpjs_pension_employer_rate` | Float     | % JP (Perusahaan) |
| `bpjs_pension_employer_cap`  | Currency  | Plafon JP (Perusahaan) |
| `bpjs_pension_employee_rate` | Float     | % JP (Karyawan) |
| `bpjs_pension_employee_cap`  | Currency  | Plafon JP (Karyawan) |
| `biaya_jabatan_rate`         | Float     | % Biaya Jabatan |
| `biaya_jabatan_cap`          | Currency  | Maksimum Biaya Jabatan tahunan |

---

## 3. PTKP Table (Child Table)

| Field         | Type     | Description |
|---------------|----------|-------------|
| `tax_status`  | Data     | Status seperti TK/0, K/3, HB/2 |
| `ptkp_amount` | Currency | Nilai PTKP tahunan |

---

## 4. TER Mapping Table (Child Table)

| Field        | Type | Description |
|--------------|------|-------------|
| `tax_status` | Data | Contoh: TK/1, K/3, HB/2 |
| `ter_code`   | Data | Contoh: A, B, C |

---

## 5. TER Bracket Table (Child Table)

| Field          | Type     | Description |
|----------------|----------|-------------|
| `ter_code`     | Data     | Kode TER: A, B, C |
| `min_income`   | Currency | Minimal penghasilan tahunan |
| `max_income`   | Currency | Maksimal penghasilan tahunan |
| `rate_percent` | Float    | Tarif pajak (%) |

---

## 6. Payroll Options

| Field                      | Type                   | Notes |
|----------------------------|------------------------|-------|
| `fallback_income_tax_slab` | Link (Income Tax Slab) | Jika `tax_status` tidak ditemukan |

---

## 7. Formula di Salary Component

Komponen seperti BPJS akan menggunakan helper function untuk membaca rate/cap:

```python
bpjs_calc(base, "bpjs_health_employer_cap", "bpjs_health_employer_rate")
