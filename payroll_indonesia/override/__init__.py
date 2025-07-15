# This file marks the override directory as a Python package

# Import salary_slip module to make it available through override
from . import salary_slip
from . import payroll_entry

# Export the PayrollEntry class
from .payroll_entry import CustomPayrollEntry, PayrollEntryIndonesia