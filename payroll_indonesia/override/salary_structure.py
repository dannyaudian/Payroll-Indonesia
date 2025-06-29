# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now
from hrms.payroll.doctype.salary_structure.salary_structure import SalaryStructure
from payroll_indonesia.utilities.tax_slab import get_default_tax_slab, create_income_tax_slab
from payroll_indonesia.config.config.gl_account_mapper import get_gl_account_for_salary_component


class CustomSalaryStructure(SalaryStructure):
    def validate(self):
        """Override validasi Salary Structure untuk mengizinkan company='%'"""
        try:
            # Simpan nilai company original
            original_company = self.company

            # Jika company adalah wildcard '%', gunakan company default untuk validasi saja
            if self.company == "%":
                default_company = frappe.defaults.get_global_default("company")
                if not default_company:
                    frappe.throw(
                        _("Default company tidak ditemukan. Tidak bisa menggunakan wildcard '%'."),
                        title=_("Company Not Found"),
                    )
                self.company = default_company

            # Jalankan validasi standard
            super().validate()

            # Kembalikan nilai company ke wildcard jika itu nilai aslinya
            if original_company == "%":
                self.company = original_company
        except Exception as e:
            # Handle ValidationError separately
            if isinstance(e, frappe.exceptions.ValidationError):
                raise

            # Log and re-raise other errors
            frappe.log_error(
                "Error validating Salary Structure {0}: {1}".format(
                    self.name if hasattr(self, "name") else "New", str(e)
                ),
                "Salary Structure Validation Error",
            )
            frappe.throw(_("Error validating salary structure: {0}").format(str(e)))

    def on_update(self):
        """On update yang minimal tanpa mengakses field yang mungkin tidak ada"""
        try:
            super(CustomSalaryStructure, self).on_update()

            # Cek apakah ada komponen PPh 21
            has_tax_component = False
            for d in self.deductions:
                if d.salary_component == "PPh 21":
                    has_tax_component = True
                    break

            # Periksa apakah field income_tax_slab ada dalam doctype
            field_exists = False
            try:
                # Cek apakah attribut ada atau bisa diakses dari db
                if hasattr(self, "income_tax_slab"):
                    field_exists = True
                else:
                    # Coba ambil dari database
                    tax_slab_value = frappe.db.get_value(
                        "Salary Structure", self.name, "income_tax_slab"
                    )
                    if tax_slab_value is not None:
                        field_exists = True
            except Exception as field_check_error:
                # Non-critical error during field check
                frappe.log_error(
                    "Error checking income_tax_slab field in {0}: {1}".format(
                        self.name, str(field_check_error)
                    ),
                    "Field Check Error",
                )
                field_exists = False

            # Jika ada komponen PPh 21 dan field income_tax_slab ada, tapi nilainya kosong
            if has_tax_component and field_exists:
                tax_slab_value = getattr(self, "income_tax_slab", None) or frappe.db.get_value(
                    "Salary Structure", self.name, "income_tax_slab"
                )

                if not tax_slab_value:
                    # Dapatkan tax slab default
                    tax_slab = get_default_tax_slab()

                    if tax_slab:
                        try:
                            # Update langsung ke DB untuk menghindari error
                            update_dict = {"tax_calculation_method": "Manual"}

                            # Tambahkan income_tax_slab jika field ada di DocType
                            if field_exists:
                                update_dict["income_tax_slab"] = tax_slab

                            frappe.db.set_value("Salary Structure", self.name, update_dict)
                            frappe.db.commit()
                        except Exception as update_error:
                            # Non-critical error during update - log but continue
                            frappe.log_error(
                                "Error updating income_tax_slab for {0}: {1}".format(
                                    self.name, str(update_error)
                                ),
                                "Tax Slab Update Error",
                            )
                            frappe.msgprint(
                                _("Warning: Could not set income tax slab automatically."),
                                indicator="orange",
                            )

            # Update GL accounts for all components if applicable
            self.update_gl_accounts_for_components()

        except Exception as e:
            # Non-critical error in on_update - log but continue since this is a hook
            frappe.log_error(
                "Error in on_update for Salary Structure {0}: {1}".format(self.name, str(e)),
                "Salary Structure Hook Error",
            )
            frappe.msgprint(
                _(
                    "Warning: Error during salary structure update. Some operations may not complete."
                ),
                indicator="orange",
            )

    def update_gl_accounts_for_components(self):
        """Update GL accounts for all components in the salary structure"""
        if self.company == "%":
            # Skip for wildcard company
            return

        try:
            company = self.company
            components_updated = 0

            # Process earnings
            for earning in self.earnings:
                component_name = earning.salary_component
                if update_gl_account_for_component(company, component_name):
                    components_updated += 1

            # Process deductions
            for deduction in self.deductions:
                component_name = deduction.salary_component
                if update_gl_account_for_component(company, component_name):
                    components_updated += 1

            if components_updated > 0:
                frappe.log_error(
                    f"Updated GL accounts for {components_updated} salary components in {self.name}",
                    "GL Account Update",
                )

        except Exception as e:
            frappe.log_error(
                f"Error updating GL accounts for components in {self.name}: {str(e)}",
                "GL Account Update Error",
            )


def update_gl_account_for_component(company, component_name):
    """Update GL account for a salary component using the mapping function"""
    try:
        if not frappe.db.exists("Salary Component", component_name):
            return False

        component = frappe.get_doc("Salary Component", component_name)
        if not hasattr(component, "accounts"):
            return False

        # Get the mapped GL account
        gl_account = get_gl_account_for_salary_component(company, component_name)
        if not gl_account:
            return False

        # Check if an account entry already exists for this company
        account_exists = False
        for acc in component.accounts:
            if acc.company == company:
                if acc.default_account != gl_account:
                    acc.default_account = gl_account
                    account_exists = True
                    break
                else:
                    # Account already has the correct mapping
                    return False

        # If no account exists for this company, add a new one
        if not account_exists:
            component.append("accounts", {"company": company, "default_account": gl_account})

        # Save the component with updated accounts
        component.flags.ignore_validate_update_after_submit = True
        component.flags.ignore_validate = True
        component.flags.ignore_permissions = True
        component.save()

        return True
    except Exception as e:
        frappe.log_error(
            f"Error updating GL account for component {component_name} in company {company}: {str(e)}",
            "GL Account Update Error",
        )
        return False


# Fungsi untuk membuat/memperbarui Salary Structure default
def create_default_salary_structure():
    """Buat atau update Salary Structure secara programatis"""
    try:
        # Pastikan Income Tax Slab tersedia
        create_income_tax_slab()

        # Definisi struktur gaji default
        structure_name = "Struktur Gaji Tetap G1"

        # Dapatkan company default dari site
        default_company = frappe.defaults.get_global_default("company")
        company_value = default_company or "%"

        # Dapatkan default tax slab
        default_tax_slab = get_default_tax_slab()

        # Definisi komponen earnings
        earnings = [
            {
                "salary_component": "Gaji Pokok",
                "amount_based_on_formula": 1,
                "formula": "base",
                "condition": "",
            },
            {"salary_component": "Tunjangan Makan", "amount": 500000, "condition": ""},
            {"salary_component": "Tunjangan Transport", "amount": 300000, "condition": ""},
            {
                "salary_component": "Insentif",
                "amount": 0,
                "amount_based_on_formula": 0,
                "condition": "",
                "description": "Diisi manual sesuai kinerja karyawan",
            },
            {
                "salary_component": "Bonus",
                "amount": 0,
                "amount_based_on_formula": 0,
                "condition": "",
                "description": "Diisi manual sesuai kebijakan perusahaan",
            },
        ]

        # Definisi komponen deductions
        deductions = [
            {
                "salary_component": "BPJS JHT Employee",
                "amount_based_on_formula": 0,
                "amount": 0,
                "condition": "ikut_bpjs_ketenagakerjaan",
                "do_not_include_in_total": 0,
            },
            {
                "salary_component": "BPJS JP Employee",
                "amount_based_on_formula": 0,
                "amount": 0,
                "condition": "ikut_bpjs_ketenagakerjaan",
                "do_not_include_in_total": 0,
            },
            {
                "salary_component": "BPJS Kesehatan Employee",
                "amount_based_on_formula": 0,
                "amount": 0,
                "condition": "ikut_bpjs_kesehatan",
                "do_not_include_in_total": 0,
            },
            {
                "salary_component": "PPh 21",
                "amount_based_on_formula": 0,
                "amount": 0,
                "condition": "not penghasilan_final",
                "do_not_include_in_total": 0,
            },
            {
                "salary_component": "BPJS JHT Employer",
                "amount_based_on_formula": 0,
                "amount": 0,
                "condition": "ikut_bpjs_ketenagakerjaan",
                "statistical_component": 1,
                "do_not_include_in_total": 1,
            },
            {
                "salary_component": "BPJS JP Employer",
                "amount_based_on_formula": 0,
                "amount": 0,
                "condition": "ikut_bpjs_ketenagakerjaan",
                "statistical_component": 1,
                "do_not_include_in_total": 1,
            },
            {
                "salary_component": "BPJS JKK",
                "amount_based_on_formula": 0,
                "amount": 0,
                "condition": "ikut_bpjs_ketenagakerjaan",
                "statistical_component": 1,
                "do_not_include_in_total": 1,
            },
            {
                "salary_component": "BPJS JKM",
                "amount_based_on_formula": 0,
                "amount": 0,
                "condition": "ikut_bpjs_ketenagakerjaan",
                "statistical_component": 1,
                "do_not_include_in_total": 1,
            },
            {
                "salary_component": "BPJS Kesehatan Employer",
                "amount_based_on_formula": 0,
                "amount": 0,
                "condition": "ikut_bpjs_kesehatan",
                "statistical_component": 1,
                "do_not_include_in_total": 1,
            },
        ]

        # Cek apakah struktur sudah ada
        if frappe.db.exists("Salary Structure", structure_name):
            # Update struktur yang sudah ada
            ss = frappe.get_doc("Salary Structure", structure_name)

            # Update field dasar
            ss.is_active = "Yes"
            ss.payroll_frequency = "Monthly"
            ss.company = company_value
            ss.currency = "IDR"

            # Hapus komponen lama
            ss.earnings = []
            ss.deductions = []

            # Tambahkan komponen baru
            for e in earnings:
                ss.append("earnings", e)

            for d in deductions:
                ss.append("deductions", d)

            # Note
            ss.note = "Nilai komponen BPJS dan PPh 21 dihitung otomatis berdasarkan pengaturan di BPJS Settings dan PPh 21 Settings."

            # Track modification
            ss.modified_by = frappe.session.user
            ss.modified = now()

            # Coba set tax calculation method dan tax slab jika field ada
            try:
                ss.tax_calculation_method = "Manual"
                if default_tax_slab and hasattr(ss, "income_tax_slab"):
                    ss.income_tax_slab = default_tax_slab
            except Exception as field_error:
                # Non-critical field error
                frappe.log_error(
                    "Error setting tax fields on salary structure {0}: {1}".format(
                        structure_name, str(field_error)
                    ),
                    "Tax Field Error",
                )

            # Save dengan ignore_permissions
            ss.flags.ignore_permissions = True
            ss.save()

            frappe.db.commit()
            frappe.log_error(
                "Updated Salary Structure: {0}".format(structure_name), "Salary Structure Update"
            )

        else:
            # Buat struktur baru
            ss_dict = {
                "doctype": "Salary Structure",
                "name": structure_name,
                "salary_structure_name": structure_name,
                "is_active": "Yes",
                "payroll_frequency": "Monthly",
                "company": company_value,
                "mode_of_payment": "Cash",
                "currency": "IDR",
                "earnings": earnings,
                "deductions": deductions,
                "note": "Nilai komponen BPJS dan PPh 21 dihitung otomatis berdasarkan pengaturan di BPJS Settings dan PPh 21 Settings.",
                "owner": frappe.session.user,
                "modified_by": frappe.session.user,
            }

            # Buat dokumen baru
            ss = frappe.get_doc(ss_dict)

            # Coba set tax calculation method dan tax slab jika field ada
            try:
                ss.tax_calculation_method = "Manual"
                if default_tax_slab and hasattr(ss, "income_tax_slab"):
                    ss.income_tax_slab = default_tax_slab
            except Exception as field_error:
                # Non-critical field error
                frappe.log_error(
                    "Error setting tax fields on new salary structure {0}: {1}".format(
                        structure_name, str(field_error)
                    ),
                    "Tax Field Error",
                )

            # Insert dengan ignore_permissions
            ss.insert(ignore_permissions=True)

            frappe.db.commit()
            frappe.log_error(
                "Created Salary Structure: {0}".format(structure_name), "Salary Structure Creation"
            )

        # Setelah membuat struktur, update assignment jika perlu
        if default_tax_slab:
            from payroll_indonesia.utilities.tax_slab import update_existing_assignments

            update_existing_assignments()

        # Update GL accounts for all components in the structure
        if default_company:
            update_gl_accounts_for_components(ss)

        return True

    except Exception as e:
        # Non-critical function for setup - log error and return False
        frappe.log_error(
            "Error creating/updating Salary Structure: {0}".format(str(e)),
            "Salary Structure Setup Error",
        )
        return False


def update_gl_accounts_for_components(salary_structure):
    """Update GL accounts for all components in a salary structure"""
    company = salary_structure.company
    if company == "%":
        # If wildcard company, use default company
        company = frappe.defaults.get_global_default("company")
        if not company:
            return

    try:
        # Process all components in the structure
        for earning in salary_structure.earnings:
            update_gl_account_for_component(company, earning.salary_component)

        for deduction in salary_structure.deductions:
            update_gl_account_for_component(company, deduction.salary_component)

    except Exception as e:
        frappe.log_error(
            f"Error updating GL accounts for components in structure {salary_structure.name}: {str(e)}",
            "GL Account Update Error",
        )


# Fungsi untuk memastikan komponen salary tersedia
def create_salary_components():
    """Buat komponen gaji jika belum ada"""
    try:
        # Daftar komponen earnings
        earnings = [
            {"salary_component": "Gaji Pokok", "type": "Earning", "is_tax_applicable": 1},
            {"salary_component": "Tunjangan Makan", "type": "Earning", "is_tax_applicable": 1},
            {"salary_component": "Tunjangan Transport", "type": "Earning", "is_tax_applicable": 1},
            {"salary_component": "Insentif", "type": "Earning", "is_tax_applicable": 1},
            {"salary_component": "Bonus", "type": "Earning", "is_tax_applicable": 1},
        ]

        # Daftar komponen deductions
        deductions = [
            {
                "salary_component": "PPh 21",
                "type": "Deduction",
                "variable_based_on_taxable_salary": 1,
            },
            {"salary_component": "BPJS JHT Employee", "type": "Deduction"},
            {"salary_component": "BPJS JP Employee", "type": "Deduction"},
            {"salary_component": "BPJS Kesehatan Employee", "type": "Deduction"},
            {
                "salary_component": "BPJS JHT Employer",
                "type": "Deduction",
                "statistical_component": 1,
                "do_not_include_in_total": 1,
            },
            {
                "salary_component": "BPJS JP Employer",
                "type": "Deduction",
                "statistical_component": 1,
                "do_not_include_in_total": 1,
            },
            {
                "salary_component": "BPJS JKK",
                "type": "Deduction",
                "statistical_component": 1,
                "do_not_include_in_total": 1,
            },
            {
                "salary_component": "BPJS JKM",
                "type": "Deduction",
                "statistical_component": 1,
                "do_not_include_in_total": 1,
            },
            {
                "salary_component": "BPJS Kesehatan Employer",
                "type": "Deduction",
                "statistical_component": 1,
                "do_not_include_in_total": 1,
            },
        ]

        # Get default company for GL accounts
        default_company = frappe.defaults.get_global_default("company")

        # Buat semua komponen
        for comp in earnings + deductions:
            name = comp["salary_component"]
            if not frappe.db.exists("Salary Component", name):
                doc = frappe.new_doc("Salary Component")
                doc.salary_component = name
                for key, value in comp.items():
                    if key != "salary_component":
                        doc.set(key, value)

                # Set GL account if company is available
                if default_company and hasattr(doc, "accounts"):
                    gl_account = get_gl_account_for_salary_component(default_company, name)
                    if gl_account:
                        doc.append(
                            "accounts", {"company": default_company, "default_account": gl_account}
                        )

                doc.insert(ignore_permissions=True)
                frappe.db.commit()
                frappe.log_error("Created Salary Component: {0}".format(name), "Component Creation")

        return True

    except Exception as e:
        # Non-critical function for setup - log error and return False
        frappe.log_error(
            "Error creating salary components: {0}".format(str(e)), "Component Setup Error"
        )
        return False


def update_salary_structures():
    """Task terjadwal untuk memperbarui salary structure"""
    try:
        # Pastikan Income Tax Slab sudah dibuat
        from payroll_indonesia.utilities.tax_slab import create_income_tax_slab

        create_income_tax_slab()

        # Buat komponen salary
        create_salary_components()

        # Buat atau update struktur gaji
        create_default_salary_structure()

        # Update GL accounts for existing salary components
        update_gl_accounts_for_all_components()

        return "Updated salary structures successfully"

    except Exception as e:
        # Non-critical scheduled task - log error and return error message
        frappe.log_error(
            "Failed to update salary structures: {0}".format(str(e)), "Scheduled Task Error"
        )
        return "Error: {0}".format(str(e))


def update_gl_accounts_for_all_components():
    """Update GL accounts for all existing salary components"""
    try:
        company = frappe.defaults.get_global_default("company")
        if not company:
            return False

        components = frappe.get_all("Salary Component", fields=["name"])
        updated_count = 0

        for comp in components:
            if update_gl_account_for_component(company, comp.name):
                updated_count += 1

        if updated_count > 0:
            frappe.log_error(
                f"Updated GL accounts for {updated_count} salary components", "GL Account Update"
            )

        return True
    except Exception as e:
        frappe.log_error(
            f"Error updating GL accounts for all components: {str(e)}", "GL Account Update Error"
        )
        return False
