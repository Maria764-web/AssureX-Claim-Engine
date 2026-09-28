"""
AssureX Input Validators
Provides validation functions for emails, phone numbers, serial numbers, purchase dates, prices, and IDs.
"""

import re
from datetime import date, datetime
from typing import Optional, Tuple
from email_validator import validate_email as check_email, EmailNotValidError


def validate_email(email: str) -> bool:
    """Validate email format using RFC-compliant email-validator."""
    if not email or not isinstance(email, str):
        return False
    try:
        check_email(email, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


def validate_phone(phone: str) -> bool:
    """Validate phone number format (international/standard formats accepted)."""
    if not phone or not isinstance(phone, str):
        return False
    pattern = r"^\+?[0-9\s\-\(\)]{7,20}$"
    return bool(re.match(pattern, phone.strip()))


def validate_serial_number(serial: str) -> bool:
    """Validate product serial number format (alphanumeric, hyphens, underscores, 3-60 chars)."""
    if not serial or not isinstance(serial, str):
        return False
    cleaned = serial.strip()
    return 3 <= len(cleaned) <= 60 and bool(re.match(r"^[A-Za-z0-9\-_]+$", cleaned))


def validate_purchase_date(date_input) -> Tuple[bool, Optional[date], Optional[str]]:
    """
    Validate purchase date:
    - Must be valid date format (YYYY-MM-DD or date object)
    - Must NOT be in the future
    - Must not be unreasonably old (> 30 years ago)
    """
    if not date_input:
        return False, None, "Purchase date is required."

    if isinstance(date_input, date):
        parsed_date = date_input
    elif isinstance(date_input, str):
        try:
            parsed_date = datetime.strptime(date_input.strip(), "%Y-%m-%d").date()
        except ValueError:
            return False, None, "Invalid date format. Expected YYYY-MM-DD."
    else:
        return False, None, "Invalid date value."

    today = date.today()
    if parsed_date > today:
        return False, None, "Purchase date cannot be in the future."

    min_date = date(today.year - 30, today.month, today.day)
    if parsed_date < min_date:
        return False, None, "Purchase date is too far in the past."

    return True, parsed_date, None


def validate_price(price_input) -> Tuple[bool, Optional[float], Optional[str]]:
    """Validate purchase price (positive float or decimal)."""
    if price_input is None or price_input == "":
        return False, None, "Purchase price is required."
    try:
        val = float(price_input)
        if val < 0:
            return False, None, "Purchase price must be a positive number."
        if val > 1_000_000:
            return False, None, "Purchase price exceeds maximum allowable threshold."
        return True, round(val, 2), None
    except (ValueError, TypeError):
        return False, None, "Purchase price must be a valid number."


def validate_warranty_length(months_input) -> Tuple[bool, Optional[int], Optional[str]]:
    """Validate warranty length in months (integer from 1 to 120 months)."""
    if months_input is None or months_input == "":
        return True, 12, None  # Default to 12 months if omitted
    try:
        months = int(months_input)
        if months <= 0:
            return False, None, "Warranty length must be at least 1 month."
        if months > 120:
            return False, None, "Warranty length cannot exceed 120 months (10 years)."
        return True, months, None
    except (ValueError, TypeError):
        return False, None, "Warranty length must be an integer number of months."


def validate_uid_format(uid: str, prefix: str) -> bool:
    """Validate unique identifier format (e.g. USR-XXXXXXXX, PRD-XXXXXXXX)."""
    if not uid or not isinstance(uid, str):
        return False
    pattern = rf"^{prefix.upper()}-[A-Z0-9]{{6,16}}$"
    return bool(re.match(pattern, uid.strip()))
