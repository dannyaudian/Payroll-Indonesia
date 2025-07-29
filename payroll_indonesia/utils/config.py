from payroll_indonesia.config import (
    get_bpjs_cap,
    get_bpjs_rate,
    get_ptkp_amount,
    get_ter_code,
    get_ter_rate,
)


def min_value(*values):
    """Return the minimum of the provided values."""
    return min(*values)


def max_value(*values):
    """Return the maximum of the provided values."""
    return max(*values)


def bpjs_calc(base: float, cap_key: str, rate_key: str) -> float:
    """Return BPJS calculation based on cap and rate settings."""
    return min_value(base, get_bpjs_cap(cap_key)) * get_bpjs_rate(rate_key) / 100


__all__ = [
    "min_value",
    "max_value",
    "get_bpjs_cap",
    "get_bpjs_rate",
    "bpjs_calc",
    "get_ptkp_amount",
    "get_ter_code",
    "get_ter_rate",
]
