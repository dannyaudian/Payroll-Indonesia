# Changelog

## [Unreleased]
### Added
- Salary slip creation now forces `tax_calculation_method` to "Manual" and clears `income_tax_slab`.
- Renamed `use_ter_method` field on Payroll Entry to `ter_method_enabled`.
- Payroll Entry submission now automatically creates and submits Salary Slips.
- Cancelling a Payroll Entry now clears tax data so a new payroll entry for the same period can be submitted.
