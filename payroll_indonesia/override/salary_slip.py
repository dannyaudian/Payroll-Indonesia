# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:35:42 by dannyaudian

"""
Salary Slip override for Indonesian payroll.

Re-exports IndonesiaPayrollSalarySlip from the override.salary_slip package.
"""

from payroll_indonesia.override.salary_slip.salary_slip import IndonesiaPayrollSalarySlip

__all__ = ["IndonesiaPayrollSalarySlip"]