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
