# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:32:01 by dannyaudian

"""
Utility functions for salary slip processing - util ringan YTD/YTM.
"""

import logging
from typing import Any, Dict, Optional

import payroll_indonesia.override.salary_slip_functions as slip_fn

# Optional logger
logger = logging.getLogger(__name__)


def calculate_ytd_and_ytm(slip: Any, date: Optional[str] = None) -> Dict[str, float]:
    """
    Calculate Year-to-Date (YTD) and Year-to-Month (YTM) values for salary slip.
    Delegates to the detailed implementation in salary_slip_functions.py.
    
    Args:
        slip: Salary slip document
        date: Optional date to use instead of slip's end_date
        
    Returns:
        Dict with YTD and YTM values for earnings, deductions, gross pay, and BPJS
    """
    try:
        # Delegate to the actual implementation
        return slip_fn.calculate_ytd_and_ytm(slip, date)
    except Exception as e:
        # Log the error but don't break the application
        logger.exception(
            f"Error calculating YTD/YTM values for "
            f"{getattr(slip, 'name', 'unknown')}: {e}"
        )
        
        # Return default values on error
        return {
            "ytd_gross": 0.0,
            "ytd_earnings": 0.0,
            "ytd_deductions": 0.0,
            "ytm_gross": 0.0,
            "ytm_earnings": 0.0,
            "ytm_deductions": 0.0,
            "ytd_bpjs": 0.0,
            "ytm_bpjs": 0.0,
        }
