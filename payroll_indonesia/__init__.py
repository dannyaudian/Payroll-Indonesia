__version__ = "1.0.0"

# Ensure Python built-ins ``min`` and ``max`` are available during formula
# evaluation in Salary Structure and Salary Slip.  ERPNext's safe execution
# environment does not expose these by default which causes evaluation errors
# for formulas like ``min(base, cap)``.  If frappe is not installed the import
# will fail (for example when running static analysis), therefore wrap the
# update in ``try/except``.
try:  # pragma: no cover - frappe might not be available during tests
    from frappe.utils.safe_exec import get_safe_globals

    safe_globals = get_safe_globals()
    safe_globals.setdefault("min", min)
    safe_globals.setdefault("max", max)
except Exception:
    pass
