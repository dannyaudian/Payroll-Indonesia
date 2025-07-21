"""Setup CLI utilities for Payroll Indonesia."""


def relink_accounts_cli():
    """Reapply default GL accounts to salary components.

    Usage:
        bench --site <site> execute payroll_indonesia.setup.relink_accounts_cli
    """
    try:
        from payroll_indonesia.setup.settings_migration import _load_defaults
        from payroll_indonesia.fixtures.setup import map_salary_component_to_gl
        import frappe

        defaults = _load_defaults()
        companies = frappe.get_all("Company", pluck="name")
        if not companies:
            print("No companies found")
            return

        for company in companies:
            mapped = map_salary_component_to_gl(company, defaults)
            if mapped:
                print(f"{company}: mapped {', '.join(mapped)}")
            else:
                print(f"{company}: no mappings applied")
    except Exception as e:
        print(f"Error relinking accounts: {e}")

