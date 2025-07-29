__version__ = "1.0.0"

import frappe

def _patch_salary_slip_globals():
    """Resolve string hooks (e.g. 'payroll_indonesia.config.get_bpjs_cap')
    into actual callable functions, so Salary Slip safe_eval can use them."""
    hooks = frappe.get_hooks("salary_slip_globals") or {}
    globals_dict = {}
    for key, paths in hooks.items():
        for path in paths:
            try:
                globals_dict[key] = frappe.get_attr(path)
            except Exception as e:
                frappe.log_error(f"Failed loading salary_slip_globals {key}: {e}")
    return globals_dict
