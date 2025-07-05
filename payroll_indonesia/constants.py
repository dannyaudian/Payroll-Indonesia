# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 10:08:25 by dannyaudianlanjutkan

"""
Constants for Payroll Indonesia module.
This file centralizes magic numbers and other constants used throughout the codebase.
"""

# Time constants (in seconds)
THIRTY_MIN = 1800  # 30 minutes in seconds
ONE_HOUR = 3600  # 1 hour in seconds
ONE_DAY = 86400  # 1 day in seconds

# Calendar constants
MONTHS_PER_YEAR = 12  # Months in a year
DAYS_PER_MONTH = 30  # Standard calculation month
MAX_WORKING_DAYS = 22  # Maximum working days in a month
DEFAULT_WORKING_HOURS = 8  # Standard working hours per day
DECEMBER_MONTH = 12  # December's month number

# Currency and number formatting
CURRENCY_PRECISION = 2  # Decimal places for currency values
PERCENTAGE_PRECISION = 2  # Decimal places for percentage values

# Thresholds for calculations
TAX_DETECTION_THRESHOLD = 100000000  # 100 million rupiah
ANNUAL_DETECTION_FACTOR = 3  # If gross pay > 3x total earnings, likely annual
SALARY_BASIC_FACTOR = 10  # If gross pay > 10x basic salary, likely annual
MAX_DATE_DIFF = 31  # Maximum acceptable difference (in days) between dates

# Default values for salary calculation
DEFAULT_UMR = 4900000  # Jakarta UMR as default (in rupiah)
DEFAULT_MEAL_ALLOWANCE = 750000  # Default meal allowance (in rupiah)
DEFAULT_TRANSPORT_ALLOWANCE = 900000  # Default transport allowance (in rupiah)
DEFAULT_POSITION_ALLOWANCE_PERCENT = 7.5  # Default position allowance (percentage)
DEFAULT_BASIC_SALARY_PERCENT = 75  # Default basic salary percentage of total

# BPJS default rates (percentages)
BPJS_KESEHATAN_EMPLOYEE_PERCENT = 1.0  # Health insurance employee contribution
BPJS_KESEHATAN_EMPLOYER_PERCENT = 4.0  # Health insurance employer contribution
BPJS_KESEHATAN_MAX_SALARY = 12000000  # Maximum salary for health insurance calculation
BPJS_JHT_EMPLOYEE_PERCENT = 2.0  # Old age employee contribution
BPJS_JHT_EMPLOYER_PERCENT = 3.7  # Old age employer contribution
BPJS_JP_EMPLOYEE_PERCENT = 1.0  # Pension plan employee contribution
BPJS_JP_EMPLOYER_PERCENT = 2.0  # Pension plan employer contribution
BPJS_JP_MAX_SALARY = 9077600  # Maximum salary for pension calculation
BPJS_JKK_PERCENT = 0.24  # Work accident insurance employer contribution
BPJS_JKM_PERCENT = 0.3  # Death insurance employer contribution

# Tax calculation constants
BIAYA_JABATAN_PERCENT = 5.0  # Position allowance expense percentage
BIAYA_JABATAN_MAX = 500000  # Maximum monthly position allowance expense (in rupiah)
TER_MAX_RATE = 34.0  # Highest TER rate is 34% for all categories per PMK 168/2023

# Cache lifetimes (in seconds)
CACHE_BRIEF = 300  # 5 minutes - for very short-lived data
CACHE_SHORT = 1800  # 30 minutes - for frequently changing data
CACHE_MEDIUM = 3600  # 1 hour - for moderately changing data
CACHE_LONG = 86400  # 1 day - for relatively stable data
CACHE_EXTENDED = 604800  # 1 week - for very stable reference data

# Log configuration
MAX_LOG_LENGTH = 500  # Maximum length of log entries to prevent oversized logs

# Valid tax status codes in Indonesia
VALID_TAX_STATUS = [
    "TK0",  # Single, no dependents
    "TK1",  # Single, 1 dependent
    "TK2",  # Single, 2 dependents
    "TK3",  # Single, 3 dependents
    "K0",  # Married, no dependents
    "K1",  # Married, 1 dependent
    "K2",  # Married, 2 dependents
    "K3",  # Married, 3 dependents
    "HB0",  # Widow/Widower, no dependents
    "HB1",  # Widow/Widower, 1 dependent
    "HB2",  # Widow/Widower, 2 dependents
    "HB3",  # Widow/Widower, 3 dependents
]

# TER (Tax Exclusion Ratio) Categories per PMK 168/2023
TER_CATEGORY_A = "TER A"  # TER Category A - mostly for lower income
TER_CATEGORY_B = "TER B"  # TER Category B - mostly for middle income
TER_CATEGORY_C = "TER C"  # TER Category C - mostly for higher income
TER_CATEGORIES = [TER_CATEGORY_A, TER_CATEGORY_B, TER_CATEGORY_C]

# Default BPJS rates as dictionary (for backwards compatibility)
DEFAULT_BPJS_RATES = {
    "kesehatan_employee_percent": BPJS_KESEHATAN_EMPLOYEE_PERCENT,
    "kesehatan_employer_percent": BPJS_KESEHATAN_EMPLOYER_PERCENT,
    "kesehatan_max_salary": BPJS_KESEHATAN_MAX_SALARY,
    "jht_employee_percent": BPJS_JHT_EMPLOYEE_PERCENT,
    "jht_employer_percent": BPJS_JHT_EMPLOYER_PERCENT,
    "jp_employee_percent": BPJS_JP_EMPLOYEE_PERCENT,
    "jp_employer_percent": BPJS_JP_EMPLOYER_PERCENT,
    "jp_max_salary": BPJS_JP_MAX_SALARY,
    "jkk_percent": BPJS_JKK_PERCENT,
    "jkm_percent": BPJS_JKM_PERCENT,
}
