File salary_component.json berisi definisi seluruh komponen gaji. Contoh struktur komponen dasar dapat dilihat pada entri “Basic Salary” berikut:

{
    "doctype": "Salary Component",
    "name": "Basic Salary",
    "salary_component": "Basic Salary",
    "salary_component_abbr": "BS",
    "type": "Earning",
    "description": "Basic salary component",
    "depends_on_payment_days": 1,
    "is_tax_applicable": 1,
    "statistical_component": 0,
    "do_not_include_in_total": 0,
    "round_to_the_nearest_integer": 1,
    "disabled": 0,
    "remove_if_zero_valued": 0
}

1. Arti Field/Flag pada Komponen Earning
Field/Flag	Deskripsi Singkat	Pengaruh PPh 21
is_tax_applicable	1 jika komponen masuk penghasilan bruto.	Menambah bruto
depends_on_payment_days	1 berarti prorata berdasarkan hadir/hari kerja.	Sesuai jumlah hari
round_to_the_nearest_integer	Hasil komponen dibulatkan ke integer terdekat.	Tidak langsung
statistical_component	1 bila hanya statistik (tidak menambah bruto/netto).	Tidak berpengaruh
do_not_include_in_total	1 bila nilai tidak dijumlahkan pada total earning.	Tidak berpengaruh
remove_if_zero_valued	Baris di slip dihapus bila nilainya 0.	Administratif
disabled	1 untuk menonaktifkan komponen.	Tidak dihitung
formula	(Opsional) Formula perhitungan otomatis.	Berdampak bila isinya menambah komponen
2. Arti Field/Flag pada Komponen Deduction
Field/Flag	Deskripsi Singkat	Pengaruh PPh 21
depends_on_payment_days	1 jika prorata terhadap hari kerja.	Sesuai hari
is_income_tax_component	1 bila deduction menjadi pengurang netto pada perhitungan PPh 21.	Mengurangi netto
variable_based_on_taxable_salary	(Tidak ada pada fixture, tapi didukung fungsi) gunakan 1 bila deduction dihitung dari penghasilan bruto kena pajak.	Mengurangi netto
exempted_from_income_tax	(Opsional) 1 bila deduction dibebaskan dari pengaruh pajak.	Tidak berpengaruh
round_to_the_nearest_integer	Nilai dibulatkan ke integer terdekat.	Tidak langsung
statistical_component	1 bila hanya statistik (tidak mempengaruhi total).	Tidak berpengaruh
do_not_include_in_total	1 bila nominalnya tidak dimasukkan ke total deduction.	Tidak berpengaruh
remove_if_zero_valued	Baris dihapus bila nilai 0.	Administratif
disabled	1 untuk menonaktifkan komponen.	Tidak dihitung
formula	(Opsional) Rumus perhitungan otomatis deduction.	Berdampak sesuai hasil
3. Contoh Penggunaan Field
a. Natura yang Dikecualikan dari Pajak (Earning)
Komponen “Makan di Kantor” menunjukan is_tax_applicable: 0 sehingga tidak menambah bruto:

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

b. Natura yang Dikenakan Pajak (Earning)
“Asuransi Tambahan” dikenakan PPh 21 (is_tax_applicable: 1):

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

c. Komponen Penambah Bruto (Earning)
“Tunjangan Transport” menambah penghasilan bruto dan prorata hari kerja:

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

d. Komponen Pengurang Netto (Deduction)
Potongan BPJS Kesehatan Employee (is_income_tax_component: 1) menjadi pengurang penghasilan netto:

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

e. Komponen Statistik / Tidak Berpengaruh
“Kendaraan Dinas” di-set sebagai statistical_component: 1 dan do_not_include_in_total: 1 sehingga hanya untuk pencatatan:

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

Deduction statistik dapat dilihat pada “Biaya Jabatan” (statistical_component: 1 dan do_not_include_in_total: 1):

{
    "name": "Biaya Jabatan",
    "salary_component": "Biaya Jabatan",
    "salary_component_abbr": "BJ",
    "type": "Deduction",
    "description": "Biaya Jabatan 5% (maksimal Rp500.000 per bulan atau Rp6.000.000 per tahun)",
    "depends_on_payment_days": 0,
    "statistical_component": 1,
    "do_not_include_in_total": 1,
    "remove_if_zero_valued": 1,
    "is_income_tax_component": 1,
    "round_to_the_nearest_integer": 1,
    "disabled": 0,
    "formula": "min(gross_pay * get_bpjs_rate(\"biaya_jabatan_rate\") / 100, get_bpjs_cap(\"biaya_jabatan_cap\") / 12)"
}

4. Ringkasan Flag Komponen Earning
Flag/Field	Pengaruh ke PPh 21
is_tax_applicable	Jika 1 → nilai komponen masuk ke penghasilan bruto.
depends_on_payment_days	Jika 1 → prorata hari kerja; mempengaruhi besaran bruto.
round_to_the_nearest_integer	Membulatkan hasil, tidak mengubah status pajak.
statistical_component	Jika 1 → tidak memengaruhi bruto/netto (hanya catatan).
do_not_include_in_total	Jika 1 → tidak masuk total earning pada slip; umumnya tidak berpengaruh ke pajak.
remove_if_zero_valued	Baris dihapus jika nilai 0 (administratif).
disabled	Komponen diabaikan sepenuhnya.
formula	Rumus perhitungan otomatis (mengacu ke field setting).
5. Ringkasan Flag Komponen Deduction
Flag/Field	Pengaruh ke PPh 21
depends_on_payment_days	1 → prorata hari kerja.
is_income_tax_component	1 → deduction menjadi pengurang penghasilan netto.
variable_based_on_taxable_salary	1 → deduction dihitung dari bruto kena pajak (tidak dipakai di fixture tapi didukung).
exempted_from_income_tax	1 → deduction tidak memengaruhi perhitungan pajak.
round_to_the_nearest_integer	Pembulatan nilai.
statistical_component	1 → hanya catatan; tidak memengaruhi netto.
do_not_include_in_total	1 → tidak masuk total deduction.
remove_if_zero_valued	Baris dihapus bila nilainya 0.
disabled	Komponen diabaikan.
formula	Rumus perhitungan deduction.
6. Cara Utility PPh 21 Memakai Flag
Fungsi sum_taxable_earnings dan sum_income_tax_deductions di pph21_ter.py membaca flag secara dinamis, tanpa menyebut nama komponen:

def sum_taxable_earnings(salary_slip):
    # ...
    for row in salary_slip.get("earnings", []):
        if (
            (row.get("is_tax_applicable", 0) == 1 or
             row.get("is_income_tax_component", 0) == 1 or
             row.get("variable_based_on_taxable_salary", 0) == 1)
            and row.get("do_not_include_in_total", 0) == 0
            and row.get("statistical_component", 0) == 0
            and row.get("exempted_from_income_tax", 0) == 0
        ):
            total += flt(row.amount)

Deduction yang menjadi pengurang netto diakumulasi melalui:

def sum_income_tax_deductions(salary_slip):
    for row in salary_slip.get("deductions", []):
        if (
            (row.get("is_income_tax_component", 0) == 1 or
             row.get("variable_based_on_taxable_salary", 0) == 1)
            and row.get("do_not_include_in_total", 0) == 0
            and row.get("statistical_component", 0) == 0
        ):
            total += flt(row.amount)

Proses lengkap perhitungan PPh 21 bulanan menggunakan hasil dari kedua fungsi tersebut:

# 1. Hitung bruto
bruto = sum_taxable_earnings(salary_slip)

# 2. Pengurang
income_tax_deduction = sum_income_tax_deductions(salary_slip)

# 3. Biaya jabatan
biaya_jabatan = calculate_biaya_jabatan(bruto)

# 4. Netto dan seterusnya ...

Karena utilitas hanya melihat flag di setiap baris slip gaji, penambahan komponen baru cukup dengan mengisi field-field pada salary_component.json. Tidak ada nama komponen yang di-hardcode.

7. Kesimpulan
Field/flag pada komponen salary menentukan apakah sebuah komponen masuk penghasilan bruto, pengurang netto, atau hanya statistik.

Utility pph21_ter.py membaca flag tersebut secara dinamis agar perhitungan mengikuti konfigurasi di salary_component.json.

Contoh di atas memuat perbedaan antara komponen natura yang dikecualikan pajak, natura kena pajak, penambah bruto, pengurang netto, serta komponen statistik.

Dokumentasi ini bisa dijadikan referensi oleh developer dan admin payroll ketika menambah atau memodifikasi komponen gaji agar perhitungan PPh 21 otomatis mengikuti regulasi.