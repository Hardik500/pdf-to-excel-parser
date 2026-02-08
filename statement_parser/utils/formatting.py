"""
Formatting utilities for number and date normalization.
"""

import re
from datetime import datetime
from dateutil import parser as date_parser
from functools import lru_cache
from typing import Optional, Tuple


# Pre-compiled regex patterns (compiled once at module load)
_DATE_PATTERN_DDMMYYYY = re.compile(r'^(\d{1,2})/(\d{1,2})/(\d{2,4})$')
_DATE_PATTERN_DDMMMYYYY = re.compile(r'^(\d{1,2})\s+([A-Za-z]{3})\s+(\d{2,4})$', re.IGNORECASE)
_DATE_PATTERN_YYYYMMDD = re.compile(r'^(\d{4})-(\d{1,2})-(\d{1,2})$')
_DATE_PATTERN_DDMMYYYY_WITH_YEAR = re.compile(r'^(\d{1,2})/(\d{1,2})/(\d{4})$')

# Month name to number mapping (compiled once)
_MONTH_NAMES = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
}


def parse_date(date_str: str, day_first: bool = True) -> Optional[str]:
    """
    Parse various date formats and return standardized DD/MM/YYYY.

    Supports formats:
    - DD/MM/YYYY
    - DD/MM/YY
    - DD Mon YYYY
    - DD Mon YY
    - YYYY-MM-DD
    - MM/DD/YYYY

    Args:
        date_str: Date string to parse
        day_first: Whether day comes before month in ambiguous formats

    Returns:
        Standardized date string in DD/MM/YYYY format, or None if parsing fails
    """
    if not date_str or not isinstance(date_str, str):
        return None

    date_str = date_str.strip()

    # Already in DD/MM/YYYY format (most common for bank statements)
    match = _DATE_PATTERN_DDMMYYYY.match(date_str)
    if match:
        day, month, year = match.groups()
        # Handle 2-digit year
        if len(year) == 2:
            year_int = int(year)
            year = f"20{year_int}" if year_int < 50 else f"19{year_int}"
        return f"{day.zfill(2)}/{month.zfill(2)}/{year}"

    # Handle DD Mon YYYY format (e.g., "06 Oct 2025", "6 Oct 25")
    match = _DATE_PATTERN_DDMMMYYYY.match(date_str)
    if match:
        day = match.group(1).zfill(2)
        month_str = match.group(2).lower()
        year = match.group(3)

        # Convert 2-digit year to 4-digit
        if len(year) == 2:
            year_int = int(year)
            year = f"20{year_int}" if year_int < 50 else f"19{year_int}"

        # Convert month name to number
        month_num = _MONTH_NAMES.get(month_str)
        if month_num:
            return f"{day}/{str(month_num).zfill(2)}/{year}"

    # Handle YYYY-MM-DD format
    match = _DATE_PATTERN_YYYYMMDD.match(date_str)
    if match:
        year, month, day = match.groups()
        return f"{day.zfill(2)}/{month.zfill(2)}/{year}"

    # Fallback: Try dateutil parser only for complex formats
    # This should rarely be hit for standard financial statements
    try:
        parsed = date_parser.parse(date_str, dayfirst=day_first)
        return parsed.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        pass

    return None


@lru_cache(maxsize=1024)
def parse_date_cached(date_str: str, day_first: bool = True) -> Optional[str]:
    """
    Cached version of parse_date for repeated calls with the same input.

    This is used by the deduplication logic to avoid redundant date parsing.

    Args:
        date_str: Date string to parse
        day_first: Whether day comes before month in ambiguous formats

    Returns:
        Standardized date string in DD/MM/YYYY format, or None if parsing fails
    """
    return parse_date(date_str, day_first)


def parse_amount(amount_str: str) -> float:
    """
    Parse various amount formats and return float.

    Handles formats:
    - 1,234.56 (standard)
    - 1,00,000.50 (Indian lakh format)
    - 1234.56 (no commas)
    - ₹1,234.56 (with Rupee symbol)
    - 1,234.56 Cr (with Cr suffix)
    - 1,234.56CR

    Args:
        amount_str: Amount string to parse

    Returns:
        Float value of the amount, or 0.0 if parsing fails
    """
    if amount_str is None:
        return 0.0

    if not isinstance(amount_str, str):
        return float(amount_str) if amount_str else 0.0

    amount_str = amount_str.strip()

    # Remove currency symbols (without matching the decimal point)
    amount_str = re.sub(r'[\u20b9$Rs?\s]', '', amount_str, flags=re.IGNORECASE)

    # Remove Cr/CR/Dr/DR suffixes (but remember for sign)
    has_cr = bool(re.search(r'\b(Cr|CR)\b', amount_str, re.IGNORECASE))
    has_dr = bool(re.search(r'\b(Dr|DR)\b', amount_str, re.IGNORECASE))

    amount_str = re.sub(r'\s*(Cr|CR|Dr|DR)\b', '', amount_str, flags=re.IGNORECASE).strip()

    # Remove thousand separators (both commas and dots depending on locale)
    # For Indian format: 1,00,000.50 -> 100000.50
    # For standard format: 1,000.50 -> 1000.50
    # We need to handle both cases

    # If there's a decimal point, everything before it is the integer part
    # Remove commas from integer part
    if '.' in amount_str:
        parts = amount_str.split('.')
        integer_part = parts[0].replace(',', '')
        amount_str = f"{integer_part}.{parts[1]}"
    else:
        amount_str = amount_str.replace(',', '')

    try:
        result = float(amount_str)
        # If has Dr/DR suffix, make negative
        if has_dr and not has_cr:
            result = -result
        return result
    except ValueError:
        return 0.0


def format_amount(amount: float, currency: str = "INR") -> str:
    """
    Format amount with currency symbol and proper separators.

    Args:
        amount: Float amount
        currency: Currency code (default: INR)

    Returns:
        Formatted amount string
    """
    if currency == "INR":
        # Indian lakh format: 1,00,000.50
        sign = "-" if amount < 0 else ""
        amount = abs(amount)

        # Split into integer and decimal parts
        integer_part = int(amount)
        decimal_part = round((amount - integer_part) * 100)

        # Format integer part in Indian system
        integer_str = f"{integer_part:,}"

        return f"{sign}₹{integer_str}.{decimal_part:02d}"
    else:
        # Standard format
        return f"${amount:,.2f}"


def normalize_description(description: str) -> str:
    """
    Normalize transaction description for consistent categorization.

    - Remove extra whitespace
    - Convert to title case
    - Remove special characters that might interfere with matching
    - Standardize common patterns

    Args:
        description: Raw transaction description

    Returns:
        Normalized description
    """
    if not description:
        return ""

    # Remove extra whitespace
    description = ' '.join(description.split())

    # Remove leading/trailing punctuation
    description = description.strip(' .,-_:;@#')

    # Limit length for practical purposes
    if len(description) > 200:
        description = description[:200]

    return description


def normalize_merchant(merchant: str) -> Tuple[str, str]:
    """
    Extract merchant name and location from combined string.

    Examples:
        "AMZN *PRIME MEMBERSHIP" -> ("Amazon Prime Membership", "")
        "SWIGGY MUMBAI IN" -> ("Swiggy", "Mumbai")
        "ZOMATO NEW DELHI" -> ("Zomato", "New Delhi")

    Args:
        merchant: Raw merchant string

    Returns:
        Tuple of (merchant_name, location)
    """
    if not merchant:
        return ("", "")

    # Common payment processor patterns
    processor_patterns = {
        r'AMZN|AMAZON': 'Amazon',
        r'SWIGGY': 'Swiggy',
        r'ZOMATO': 'Zomato',
        r'PAYTM': 'Paytm',
        r'PHONEPE': 'PhonePe',
        r'GPAY|GOOGLEPAY': 'Google Pay',
        r'UPI': 'UPI',
        r'IRCTC': 'IRCTC',
        r'ICICI': 'ICICI Bank',
        r'HDFC': 'HDFC Bank',
        r'SBI': 'SBI',
        r'AXIS': 'Axis Bank',
        r'KOTAK': 'Kotak Mahindra',
        r'YES BANK': 'Yes Bank',
        r'TATA 1MG': '1mg',
        r'NEFT': 'NEFT Transfer',
        r'RTGS': 'RTGS Transfer',
        r'FT-': 'Fund Transfer',
        r'EMI': 'EMI Payment',
        r'AUTOPAY': 'Auto Pay',
    }

    # Try to match known merchants
    normalized = merchant.upper()
    for pattern, name in processor_patterns.items():
        if re.search(pattern, normalized):
            return (name, extract_location(merchant))

    # If no match, try to split by spaces and take first part as merchant
    parts = merchant.split()
    if parts:
        merchant_name = ' '.join(parts[:2])  # First 2 words
        location = ' '.join(parts[2:]) if len(parts) > 2 else ""
        return (merchant_name.title(), location)

    return (merchant.title(), "")


def extract_location(description: str) -> str:
    """
    Extract location from transaction description.

    Common patterns:
    - "CITY IN" at the end
    - "CITY, STATE" format
    - "CITY STATE" format

    Args:
        description: Transaction description

    Returns:
        Extracted location or empty string
    """
    # Pattern: City IN (common in Indian transactions)
    match = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+IN$', description)
    if match:
        return match.group(1)

    # Pattern: City, State
    match = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),\s*([A-Z]{2,})$', description)
    if match:
        return f"{match.group(1)}, {match.group(2)}"

    # Just return the description as-is if no pattern matched
    return ""


def get_amount_sign(amount_str: str) -> float:
    """
    Determine if amount is debit or credit based on string suffix.

    Args:
        amount_str: Amount string that may have Cr/DR suffix

    Returns:
        1.0 for credit, -1.0 for debit
    """
    if not amount_str:
        return 1.0

    amount_str = str(amount_str).upper()

    if 'CR' in amount_str:
        return 1.0
    elif 'DR' in amount_str:
        return -1.0

    return 1.0


def validate_transaction_date(date_str: str) -> bool:
    """
    Validate that a date string represents a valid date.

    Args:
        date_str: Date string to validate

    Returns:
        True if valid, False otherwise
    """
    try:
        parsed = parse_date(date_str)
        if not parsed:
            return False

        # Check if date is reasonable (not in future, not too old)
        parsed_dt = datetime.strptime(parsed, "%d/%m/%Y")
        now = datetime.now()

        # Allow up to 10 years back and 1 day forward
        return now.replace(year=now.year - 10) <= parsed_dt <= now.replace(day=now.day + 1)
    except Exception:
        return False
