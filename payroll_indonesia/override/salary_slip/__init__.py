# File: payroll_indonesia/override/salary_slip/__init__.py

from __future__ import unicode_literals

# Import functions that need to be accessible from outside
from payroll_indonesia.override.salary_slip import calculate_ytd_and_ytm
from payroll_indonesia.override.salary_slip.bpjs_calculator import calculate_bpjs_components
from payroll_indonesia.override.salary_slip.tax_calculator import calculate_tax_components

# Define what should be accessible when importing from this module
__all__ = [
    'calculate_ytd_and_ytm',
    'calculate_bpjs_components',
    'calculate_tax_components'
]
