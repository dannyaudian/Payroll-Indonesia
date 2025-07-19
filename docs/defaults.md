# defaults.json Reference

The `payroll_indonesia/config/defaults.json` file seeds initial data and provides fallback values for **Payroll Indonesia Settings**. The sections below outline each top‑level key and where its values are mapped inside ERPNext.

## app_info
Metadata about the module. Values populate the fields `app_version`, `app_last_updated` and `app_updated_by` of **Payroll Indonesia Settings**.

## bpjs
Default BPJS percentages and salary caps. Nested `gl_accounts` contains default account names. Values are written to the BPJS fields of **Payroll Indonesia Settings** and to JSON account mapping fields.

## tax
General tax configuration such as `umr_default`, `biaya_jabatan_percent` and method flags. Populates matching fields on **Payroll Indonesia Settings**.

## ptkp
Dictionary of PTKP codes and amounts. Seeded into the child table **PTKP Table Entry** (`ptkp_table`).

## ptkp_to_ter_mapping
Mapping from PTKP status to TER category. Seeded into child table **PTKP TER Mapping Entry** (`ptkp_ter_mapping_table`).

## tax_brackets
List of progressive tax brackets. Seeded into the **Tax Bracket Entry** table (`tax_brackets_table`).

## ter_rates
TER rate tables per category (A, B, C). The optional `metadata` object populates fields such as `ter_effective_date` and `ter_regulation_ref`. Rate rows are inserted into the **PPh 21 TER Table** (`ter_rate_table`).

## defaults
Global payroll defaults like currency, working days and payroll frequency. Values map directly to similarly named fields of **Payroll Indonesia Settings**.

## struktur_gaji
Values used when creating the default salary structure and for related fields in **Payroll Indonesia Settings** (e.g. `basic_salary_percent`, `meal_allowance`).

## gl_accounts
Chart of Accounts templates for payroll. Includes `root_account`, `expense_accounts`, `payable_accounts` and BPJS related accounts. Data is stored as JSON in the settings fields `expense_accounts_json`, `payable_accounts_json`, `parent_accounts_json` and `bpjs_account_mapping_json`.

The `bpjs_account_mapping_json` object mirrors the **BPJS Account Mapping** DocType. It stores the GL account fields used when creating the default mapping for each company. Current field names include:

```
kesehatan_employee_account
jht_employee_account
jp_employee_account
kesehatan_employer_debit_account
kesehatan_employer_credit_account
jht_employer_debit_account
jht_employer_credit_account
jp_employer_debit_account
jp_employer_credit_account
jkk_employer_debit_account
jkk_employer_credit_account
jkm_employer_debit_account
jkm_employer_credit_account
```

### Expense accounts

The `expense_accounts` object defines GL accounts for common salary components:

```
beban_gaji_pokok
beban_tunjangan_makan
beban_tunjangan_transport
beban_insentif
beban_bonus
beban_tunjangan_jabatan
beban_tunjangan_lembur
beban_natura
beban_fasilitas_kendaraan
```

### Payable accounts

Default liability accounts created during setup:

```
hutang_pph21
hutang_kasbon
```

### Root account names

The default configuration assumes your site uses the standard English root
groups created by ERPNext, such as **"Assets - {abbr}"**, **"Liabilities -
{abbr}"** and **"Expenses - {abbr}"**. The bundled defaults also include the
Indonesian group names **"Beban"** and **"Kewajiban"** so that common charts of
accounts work out of the box. If your Chart of Accounts uses other localized
names, adjust `parent_account_candidates_expense` and
`parent_account_candidates_liability` in **Payroll Indonesia Settings** to point
to your actual top‑level expense and liability accounts. You can specify more
than one name separated by commas or new lines.

Example for Indonesian account groups:

```
parent_account_candidates_expense: Beban
parent_account_candidates_liability: Kewajiban
```

With these values the module can create accounts like "Hutang PPh 21" under the
"Kewajiban" group if no matching English parent exists.

## settings
Miscellaneous behaviour flags such as `sync_to_defaults` and parent account candidates. Stored on **Payroll Indonesia Settings**.

## bpjs_settings
Extra configuration for BPJS validation. Includes percentage ranges and mappings of component names to config fields. Used internally by validation helpers.

## custom_fields
Lists of custom fields added to the `Employee` and `Salary Slip` DocTypes during setup.

## salary_components
Default salary components for earnings and deductions. During setup each
component is mapped to a GL account for the site's default company using
`gl_account_mapper.get_gl_account_for_salary_component`. If the mapped
account does not exist it will be created automatically.

## suppliers
Supplier templates seeded during setup. Currently contains a single `bpjs` supplier definition.

## tipe_karyawan
List of employee types inserted into the **Tipe Karyawan Entry** child table (`tipe_karyawan`).

## tax_component_config
Maps salary components to tax effect categories used by the tax calculator. The
`bpjs_employee_as_deduction` flag controls whether the employee portion of BPJS
reduces taxable income. The earlier `bpjs_employer_as_income` option has been
removed as employer contributions are always treated as non-taxable.
