# Salary Components & Account Mapping

Dokumen ini menjelaskan daftar **Salary Component** yang disediakan modul Payroll Indonesia beserta akun GL bawaan yang dipetakan ke setiap komponen. Definisi komponen berada pada file `fixtures/salary_component.json`. Akun GL default dibuat menggunakan `payroll_indonesia/setup/default_gl_accounts.json` dan dipetakan ke komponen pada `payroll_indonesia/setup/gl_account_mapping.json`.

## Daftar Komponen

| Component | Abbr | Type | Default GL Account | Description |
|-----------|------|------|-------------------|-------------|
| Basic Salary | BS | Earning | Salary Expense | Basic salary component |
| Gaji Pokok | GP | Earning | Salary Expense | Komponen gaji pokok |
| Tunjangan Transport | TT | Earning | Transport Allowance | Tunjangan transportasi |
| Tunjangan Makan | TM | Earning | Meal Allowance | Tunjangan makan |
| THR | THR | Earning | THR Expense | Tunjangan Hari Raya |
| Bonus | BON | Earning | Bonus Expense | Bonus karyawan |
| Makan di Kantor | MK | Earning | Office Meals Expense | Makanan/minuman di tempat kerja (dikecualikan dari PPh 21 sesuai PMK 66/2023) |
| Seragam Kerja | SK | Earning | Work Uniform Expense | Fasilitas kerja (dikecualikan dari PPh 21 sesuai PMK 66/2023) |
| Bingkisan Hari Raya | BHR | Earning | Holiday Gift Expense | Bingkisan hari besar keagamaan (dikecualikan dari PPh 21 sesuai PMK 66/2023) |
| Asuransi Tambahan | AT | Earning | Additional Insurance Expense | Asuransi tambahan non-BPJS (natura yang dikenakan PPh 21) |
| Kendaraan Dinas | KD | Earning | Company Vehicle Expense | Mobil dinas pribadi (natura yang dikenakan PPh 21) |
| Insentif Penjualan | IP | Earning | Sales Incentive Expense | Insentif variabel berdasarkan pencapaian penjualan. |
| Tunjangan Pajak atas Insentif | TPI | Earning | Tax Allowance Expense | Tunjangan pajak untuk menutupi PPh atas insentif penjualan. |
| BPJS Kesehatan Employer | BPJS KES-E | Earning | BPJS Kesehatan Expense | Tanggungan BPJS Kesehatan 4% dari perusahaan |
| BPJS JHT Employer | BPJS JHT-E | Earning | BPJS JHT Expense | Tanggungan BPJS JHT 3.7% dari perusahaan |
| BPJS JP Employer | BPJS JP-E | Earning | BPJS JP Expense | Tanggungan BPJS JP 2% dari perusahaan |
| BPJS JKK Employer | BPJS JKK-E | Earning | BPJS JKK Expense | Tanggungan BPJS JKK 0.24% dari perusahaan (persentase bisa berbeda sesuai kelas risiko) |
| BPJS JKM Employer | BPJS JKM-E | Earning | BPJS JKM Expense | Tanggungan BPJS JKM 0.3% dari perusahaan |
| BPJS Kesehatan Employee | BPJS KES-EE | Deduction | BPJS Kesehatan Payable | Potongan BPJS Kesehatan 1% dari karyawan |
| BPJS JHT Employee | BPJS JHT-EE | Deduction | BPJS JHT Payable | Potongan BPJS JHT 2% dari karyawan |
| BPJS JP Employee | BPJS JP-EE | Deduction | BPJS JP Payable | Potongan BPJS JP 1% dari karyawan |
| PPh 21 | PPh21 | Deduction | PPh 21 Payable | Potongan PPh 21 yang dibebankan kepada karyawan |
| Biaya Jabatan | BJ | Deduction | Salary Expense | Biaya Jabatan 5% (maksimal Rp500.000 per bulan atau Rp6.000.000 per tahun) |
| Contra BPJS Kesehatan Employer | C-BPJS KES-E | Deduction | BPJS Kesehatan Payable | Contra entry untuk BPJS Kesehatan Employer |
| Contra BPJS JHT Employer | C-BPJS JHT-E | Deduction | BPJS JHT Payable | Contra entry untuk BPJS JHT Employer |
| Contra BPJS JP Employer | C-BPJS JP-E | Deduction | BPJS JP Payable | Contra entry untuk BPJS JP Employer |
| Contra BPJS JKK Employer | C-BPJS JKK-E | Deduction | BPJS JKK Payable | Contra entry untuk BPJS JKK Employer |
| Contra BPJS JKM Employer | C-BPJS JKM-E | Deduction | BPJS JKM Payable | Contra entry untuk BPJS JKM Employer |

Akun di atas merupakan nama akun **tanpa** akhiran kode perusahaan. Saat proses *setup* berjalan, modul akan membuat akun tersebut berdasarkan `default_gl_accounts.json`, menambahkan akronim perusahaan (contoh `- IND`), dan memetakan setiap komponen ke akun sesuai `gl_account_mapping.json`.
