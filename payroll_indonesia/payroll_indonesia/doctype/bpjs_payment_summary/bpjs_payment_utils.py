# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-02 15:54:21 by dannyaudian

"""
Utility functions for BPJS Payment Summary.

This module provides pure, unit-testable helpers for processing BPJS data
and calculations, with minimal dependencies on Frappe framework.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Protocol,
    Tuple,
    TypedDict,
    Union,
    cast,
)

logger = logging.getLogger(__name__)


# Type definitions
class DocLike(Protocol):
    """Protocol for document-like objects with attribute access."""

    def __getattr__(self, name: str) -> Any: ...


class DbLike(Protocol):
    """Protocol for database-like objects with table_exists and sql methods."""

    def table_exists(self, table_name: str) -> bool: ...

    def sql(self, query: str, *args: Any, **kwargs: Any) -> Any: ...


# Data structures for payment processing
@dataclass
class PayableLine:
    """
    Represents a payable line item for BPJS payment.

    Attributes:
        component_type: Type of BPJS component (Kesehatan, JHT, etc.)
        account: GL account for the payable
        amount: Payment amount
        description: Line item description
        reference: Optional reference number
    """

    component_type: str
    account: str
    amount: Decimal
    description: str
    reference: Optional[str] = None


@dataclass
class ExpenseLine:
    """
    Represents an expense line item for employer BPJS contributions.

    Attributes:
        expense_type: Type of expense (employer or employee contribution)
        account: GL account for the expense
        amount: Expense amount
        cost_center: Cost center to apply the expense to
        description: Line item description
    """

    expense_type: Literal["employer", "employee"]
    account: str
    amount: Decimal
    cost_center: str
    description: str


# Pure utility functions
def safe_decimal(value: Any) -> Decimal:
    """
    Safely convert a value to Decimal.

    Args:
        value: Value to convert

    Returns:
        Decimal: Converted value or 0 if conversion fails
    """
    try:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value or 0))
    except (ValueError, TypeError):
        return Decimal("0")


def format_reference(
    component_type: str, month: int, year: int, suffix: Optional[str] = None
) -> str:
    """
    Format a standardized reference number.

    Args:
        component_type: BPJS component type
        month: Month number (1-12)
        year: Year
        suffix: Optional suffix

    Returns:
        str: Formatted reference number
    """
    ref = f"BPJS-{component_type}-{month:02d}-{year}"
    if suffix:
        ref = f"{ref}-{suffix}"
    return ref


def get_month_name(month: int) -> str:
    """
    Get Indonesian month name from month number.

    Args:
        month: Month number (1-12)

    Returns:
        str: Month name in Indonesian
    """
    month_names = [
        "Januari",
        "Februari",
        "Maret",
        "April",
        "Mei",
        "Juni",
        "Juli",
        "Agustus",
        "September",
        "Oktober",
        "November",
        "Desember",
    ]

    if month < 1 or month > 12:
        return str(month)

    return month_names[month - 1]


def calculate_period_dates(month: int, year: int) -> Tuple[date, date]:
    """
    Calculate start and end dates for a given month and year.

    Args:
        month: Month (1-12)
        year: Year

    Returns:
        tuple: (start_date, end_date)

    Raises:
        ValueError: If month is invalid
    """
    import calendar
    from datetime import date

    if month < 1 or month > 12:
        raise ValueError("Month must be between 1 and 12")

    start_date = date(year, month, 1)

    # Get last day of month
    _, last_day = calendar.monthrange(year, month)
    end_date = date(year, month, last_day)

    return start_date, end_date


def safe_table_exists(db: DbLike, table_name: str) -> bool:
    """
    Safely check if a table exists in the database.

    Args:
        db: Database-like object with table_exists method
        table_name: Table name to check

    Returns:
        bool: True if table exists, False otherwise
    """
    try:
        return db.table_exists(table_name)
    except Exception:
        return False


def extract_bpjs_data_from_components(
    employee: str,
    employee_name: str,
    salary_slip: str,
    deductions: List[Dict[str, Any]],
    earnings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Extract BPJS data from salary slip components.

    Args:
        employee: Employee ID
        employee_name: Employee name
        salary_slip: Salary slip name
        deductions: List of deduction components
        earnings: List of earning components

    Returns:
        dict: Extracted BPJS data
    """
    bpjs_data = {
        "employee": employee,
        "employee_name": employee_name,
        "salary_slip": salary_slip,
        "jht_employee": Decimal("0"),
        "jp_employee": Decimal("0"),
        "kesehatan_employee": Decimal("0"),
        "jht_employer": Decimal("0"),
        "jp_employer": Decimal("0"),
        "kesehatan_employer": Decimal("0"),
        "jkk": Decimal("0"),
        "jkm": Decimal("0"),
        "last_updated": datetime.now(),
        "is_synced": 1,
    }

    # Process deductions (employee contributions)
    for deduction in deductions:
        component = deduction["salary_component"].lower()
        amount = safe_decimal(deduction.get("amount", 0))

        if "kesehatan" in component and "employee" in component:
            bpjs_data["kesehatan_employee"] += amount
        elif "jht" in component and "employee" in component:
            bpjs_data["jht_employee"] += amount
        elif "jp" in component and "employee" in component:
            bpjs_data["jp_employee"] += amount
        # Handle cases without "employee" in name
        elif "kesehatan" in component and "employer" not in component:
            bpjs_data["kesehatan_employee"] += amount
        elif "jht" in component and "employer" not in component:
            bpjs_data["jht_employee"] += amount
        elif "jp" in component and "employer" not in component:
            bpjs_data["jp_employee"] += amount

    # Process earnings (employer contributions)
    for earning in earnings:
        component = earning["salary_component"].lower()
        amount = safe_decimal(earning.get("amount", 0))

        if "kesehatan" in component and "employer" in component:
            bpjs_data["kesehatan_employer"] += amount
        elif "jht" in component and "employer" in component:
            bpjs_data["jht_employer"] += amount
        elif "jp" in component and "employer" in component:
            bpjs_data["jp_employer"] += amount
        elif "jkk" in component:
            bpjs_data["jkk"] += amount
        elif "jkm" in component:
            bpjs_data["jkm"] += amount

    # Calculate total amount
    bpjs_data["amount"] = (
        bpjs_data["kesehatan_employee"]
        + bpjs_data["jht_employee"]
        + bpjs_data["jp_employee"]
        + bpjs_data["kesehatan_employer"]
        + bpjs_data["jht_employer"]
        + bpjs_data["jp_employer"]
        + bpjs_data["jkk"]
        + bpjs_data["jkm"]
    )

    return bpjs_data


def calculate_total_amount(detail_doc: DocLike) -> Decimal:
    """
    Calculate the total amount from all BPJS components.

    Args:
        detail_doc: BPJS Payment Summary Detail document

    Returns:
        Decimal: Total amount
    """
    total = (
        safe_decimal(getattr(detail_doc, "kesehatan_employee", 0))
        + safe_decimal(getattr(detail_doc, "jht_employee", 0))
        + safe_decimal(getattr(detail_doc, "jp_employee", 0))
        + safe_decimal(getattr(detail_doc, "kesehatan_employer", 0))
        + safe_decimal(getattr(detail_doc, "jht_employer", 0))
        + safe_decimal(getattr(detail_doc, "jp_employer", 0))
        + safe_decimal(getattr(detail_doc, "jkk", 0))
        + safe_decimal(getattr(detail_doc, "jkm", 0))
    )

    return total if total > 0 else Decimal("0")


def collect_payable_lines(summary: DocLike) -> List[PayableLine]:
    """
    Collect payable lines from a BPJS Payment Summary.

    Args:
        summary: BPJS Payment Summary document

    Returns:
        List[PayableLine]: List of payable lines
    """
    payable_lines: List[PayableLine] = []

    # Check if summary has account_details
    if not hasattr(summary, "account_details") or not summary.account_details:
        return payable_lines

    # Group by account and component type
    for account_detail in summary.account_details:
        if not hasattr(account_detail, "amount") or not account_detail.amount:
            continue

        component_type = getattr(account_detail, "account_type", "BPJS")
        account = getattr(account_detail, "account", None)
        amount = safe_decimal(getattr(account_detail, "amount", 0))
        description = getattr(account_detail, "description", "")
        reference = getattr(account_detail, "reference_number", None)

        if account and amount > Decimal("0"):
            payable_lines.append(
                PayableLine(
                    component_type=component_type,
                    account=account,
                    amount=amount,
                    description=description,
                    reference=reference,
                )
            )

    return payable_lines


def get_payment_accounts(
    get_settings: Callable[[], Dict[str, Any]], company: str, component_type: Optional[str] = None
) -> Tuple[str, str]:
    """
    Get payment accounts for BPJS payments.

    Args:
        get_settings: Function to get BPJS settings
        company: Company name
        component_type: Optional component type for specific accounts

    Returns:
        Tuple[str, str]: (payment_account, expense_account)
    """
    settings = get_settings()

    # Default accounts
    default_payment = f"BPJS Payable - {company}"
    default_expense = f"BPJS Expense - {company}"

    # Get specific accounts based on component type if provided
    if component_type:
        component_type_lower = component_type.lower()
        payment_field = f"{component_type_lower}_account"
        expense_field = f"{component_type_lower}_expense_account"

        payment_account = settings.get(payment_field, default_payment)
        expense_account = settings.get(expense_field, default_expense)
    else:
        # Use general accounts
        payment_account = settings.get("payment_account", default_payment)
        expense_account = settings.get("expense_account", default_expense)

    return payment_account, expense_account


def compute_employer_expense(
    summary: DocLike, cost_center: str, account_getter: Callable[[str], Tuple[str, str]]
) -> List[ExpenseLine]:
    """
    Compute employer expense lines from a BPJS Payment Summary.

    Args:
        summary: BPJS Payment Summary document
        cost_center: Default cost center
        account_getter: Function to get accounts for a component type

    Returns:
        List[ExpenseLine]: List of expense lines
    """
    expense_lines: List[ExpenseLine] = []

    # Calculate employee and employer totals
    employee_total = Decimal("0")
    employer_total = Decimal("0")

    # Check if summary has employee_details
    if hasattr(summary, "employee_details") and summary.employee_details:
        for detail in summary.employee_details:
            # Sum employee contributions
            employee_total += (
                safe_decimal(getattr(detail, "kesehatan_employee", 0))
                + safe_decimal(getattr(detail, "jht_employee", 0))
                + safe_decimal(getattr(detail, "jp_employee", 0))
            )

            # Sum employer contributions
            employer_total += (
                safe_decimal(getattr(detail, "kesehatan_employer", 0))
                + safe_decimal(getattr(detail, "jht_employer", 0))
                + safe_decimal(getattr(detail, "jp_employer", 0))
                + safe_decimal(getattr(detail, "jkk", 0))
                + safe_decimal(getattr(detail, "jkm", 0))
            )

    # Get month and year for description
    month = int(getattr(summary, "month", 1))
    year = int(getattr(summary, "year", datetime.now().year))
    month_name = get_month_name(month)

    # Add employee contributions line if amount > 0
    if employee_total > Decimal("0"):
        _, employee_expense_account = account_getter("employee")
        expense_lines.append(
            ExpenseLine(
                expense_type="employee",
                account=employee_expense_account,
                amount=employee_total,
                cost_center=cost_center,
                description=f"Employee BPJS contributions for {month_name} {year}",
            )
        )

    # Add employer contributions line if amount > 0
    if employer_total > Decimal("0"):
        _, employer_expense_account = account_getter("employer")
        expense_lines.append(
            ExpenseLine(
                expense_type="employer",
                account=employer_expense_account,
                amount=employer_total,
                cost_center=cost_center,
                description=f"Employer BPJS contributions for {month_name} {year}",
            )
        )

    return expense_lines


def debug_log(message: str, subject: str = "BPJS Payment Utils") -> None:
    """
    Write a debug log entry.

    Args:
        message: Message to log
        subject: Log subject
    """
    logger.debug(f"{subject}: {message}")
