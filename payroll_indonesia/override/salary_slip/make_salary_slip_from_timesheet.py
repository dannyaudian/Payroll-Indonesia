# -*- coding: utf-8 -*-
"""Wrapper for make_salary_slip_from_timesheet."""

from hrms.payroll.doctype.salary_slip.salary_slip import (
    make_salary_slip_from_timesheet as _make_salary_slip_from_timesheet,
)


def make_salary_slip_from_timesheet(*args, **kwargs):
    """Proxy to HRMS `make_salary_slip_from_timesheet`."""
    return _make_salary_slip_from_timesheet(*args, **kwargs)
