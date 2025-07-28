def validate_salary_structure_required_components(doc, method):
    bpjs_employer = [
        "BPJS Kesehatan Employer",
        "BPJS JHT Employer",
        "BPJS JP Employer",
        "BPJS JKK Employer",
        "BPJS JKM Employer",
    ]
    contra_bpjs_employer = [
        "Contra BPJS Kesehatan Employer",
        "Contra BPJS JHT Employer",
        "Contra BPJS JP Employer",
        "Contra BPJS JKK Employer",
        "Contra BPJS JKM Employer",
    ]
    bpjs_employee = [
        "BPJS Kesehatan Employee",
        "BPJS JHT Employee",
        "BPJS JP Employee",
    ]
    wajib_deduction = [
        "Biaya Jabatan",
        "PPh 21",
    ]

    earning_names = [e.salary_component for e in getattr(doc, "earnings", [])]
    deduction_names = [d.salary_component for d in getattr(doc, "deductions", [])]

    found_bpjs = (
        any(comp in earning_names for comp in bpjs_employer) or
        any(comp in deduction_names for comp in bpjs_employee)
    )

    if found_bpjs:
        missing_bpjs_employer = [comp for comp in bpjs_employer if comp not in earning_names]
        missing_bpjs_employee = [comp for comp in bpjs_employee if comp not in deduction_names]
        missing_contra = [comp for comp in contra_bpjs_employer if comp not in deduction_names]
        missing_deduction = [comp for comp in wajib_deduction if comp not in deduction_names]

        all_missing = missing_bpjs_employer + missing_bpjs_employee + missing_contra + missing_deduction
        if all_missing:
            import frappe
            frappe.throw(
                "Salary Structure tidak lengkap. Komponen berikut wajib ada jika memakai BPJS Employer/Employee:\n- "
                + "\n- ".join(all_missing)
            )