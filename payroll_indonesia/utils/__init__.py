"""Utility helpers for payroll indonesia."""

from decimal import Decimal, ROUND_HALF_UP

__all__ = ["round_half_up"]


def round_half_up(value: float) -> int:
    """Round value to nearest integer using the HALF_UP rule."""
    return int(Decimal(str(value)).quantize(0, rounding=ROUND_HALF_UP))

