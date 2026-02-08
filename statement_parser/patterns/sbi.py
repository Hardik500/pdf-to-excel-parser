"""
SBI-specific regex patterns for parsing SBI Card statements.

SBI formats supported:
1. SBI Credit Card (DD Mon YY format with D/C suffix)
2. SBI Bank Account statements
"""

import re
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass

from statement_parser.patterns.generic import (
    is_skip_line,
    TransactionMatch,
    extract_amount,
    extract_date,
)
from statement_parser.utils.formatting import parse_amount, parse_date


# SBI Credit Card pattern
# Format: DD Mon YY DESCRIPTION AMOUNT D/C
# Example: 06 Oct 25 BISTRO GURGAON IND 148.00 D
# Example: 03 Dec 25 CARD CASHBACK CREDIT 32.00 C
SBI_CC_PATTERN = re.compile(
    r'^(\d{1,2}\s+[A-Za-z]{3}\s+\d{2})\s+'     # Date DD Mon YY
    r'(.+?)\s+'                                  # Description
    r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*'       # Amount
    r'([DC])\s*$',                               # Debit/Credit marker
    re.IGNORECASE
)

# SBI Card header pattern
SBI_CARD_HEADER = re.compile(
    r'^(Date|Transaction\s+Details|Amount|Dr|Credit)',
    re.IGNORECASE
)

# SBI Card period pattern
SBI_PERIOD_PATTERN = re.compile(
    r'for\s+Statement\s+Period[:\s]*\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{2})\s*to\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{2})',
    re.IGNORECASE
)


def is_sbi_card(text: str) -> bool:
    """Check if text appears to be an SBI Card statement."""
    text_lower = text.lower()

    # Strong indicators - must have actual SBI-specific patterns
    # Check for SBI credit card pattern first (DD Mon YY format with D/C suffix)
    if re.search(r'\d{1,2}\s+[A-Za-z]{3}\s+\d{2}\s+.*\d{1,3},?\d*\.?\d{2}\s*[DC]\s*$', text_lower, re.MULTILINE):
        return True

    # SBI Card header indicators
    if 'sbi card' in text_lower or 'sbicard' in text_lower:
        return True

    return False


def is_sbi_bank_statement(text: str) -> bool:
    """Check if text appears to be an SBI bank account statement."""
    text_lower = text.lower()

    # Check for SBI bank indicators
    if 'state bank of india' in text_lower or 'sbi' in text_lower:
        return True

    # Check for bank statement specific patterns
    bank_keywords = ['withdrawal', 'deposit', 'balance', 'narration']
    for kw in bank_keywords:
        if kw in text_lower:
            return True

    return False


def parse_sbi_credit_card_line(line: str) -> Optional[TransactionMatch]:
    """
    Parse a single line from SBI credit card statement.

    Format: DD Mon YY DESCRIPTION AMOUNT D/C
    Example: 06 Oct 25 BISTRO GURGAON IND 148.00 D
    Example: 03 Dec 25 CARD CASHBACK CREDIT 32.00 C

    Args:
        line: Line of text to parse

    Returns:
        TransactionMatch if successful, None otherwise
    """
    if is_skip_line(line):
        return None

    match = SBI_CC_PATTERN.search(line)
    if match:
        date_str = match.group(1)
        description = match.group(2).strip()
        amount_str = match.group(3)
        dc_marker = match.group(4)

        # Convert SBI date format to standard
        # "06 Oct 25" -> "06/10/2025"
        try:
            # Parse the date
            parts = date_str.split()
            day = parts[0].zfill(2)
            month = parts[1]
            year = parts[2]

            # Convert 2-digit year to 4-digit
            year_int = int(year)
            year = f"20{year_int}" if year_int < 50 else f"19{year_int}"

            # Reconstruct date string
            date_str = f"{day} {month} {year}"
            parsed = parse_date(date_str)
            if not parsed:
                from datetime import datetime
                parsed_dt = datetime.strptime(date_str, "%d %b %Y")
                parsed = parsed_dt.strftime("%d/%m/%Y")
        except Exception:
            parsed = parse_date(date_str)

        amount = parse_amount(amount_str)
        if amount <= 0:
            return None

        is_credit = dc_marker.upper() == 'C'

        # Clean up description
        if not description or len(description) < 3:
            return None

        return TransactionMatch(
            date=parsed,
            description=description,
            amount=amount,
            is_credit=is_credit,
            raw_line=line
        )

    return None


def extract_sbi_reference(line: str) -> Optional[str]:
    """
    Extract reference number from SBI transaction line.

    Args:
        line: Transaction line

    Returns:
        Reference number or None
    """
    # SBI cards often don't have explicit reference numbers
    # This is mainly a placeholder for interface consistency
    return None


def is_sbi_page_header(line: str) -> bool:
    """
    Check if a line is an SBI page header.

    Args:
        line: Line to check

    Returns:
        True if this is a page header line
    """
    page_indicators = ['page', 'continued', 'continue', 'page no', 'sbi card']
    return any(ind in line.lower() for ind in page_indicators)


def extract_sbi_statement_dates(text: str) -> Optional[Tuple[str, str]]:
    """
    Extract statement period from SBI statement.

    Args:
        text: Full statement text

    Returns:
        Tuple of (from_date, to_date) or None
    """
    match = SBI_PERIOD_PATTERN.search(text)
    if match:
        return (match.group(1), match.group(2))

    return None


def is_sbi_summary_line(line: str) -> bool:
    """
    Check if a line is an SBI summary/total line.

    Args:
        line: Line to check

    Returns:
        True if this is a summary line
    """
    summary_keywords = [
        'total', 'amount due', 'minimum amount', 'opening balance',
        'closing balance', 'payments', 'credits', 'debits'
    ]
    return any(kw in line.lower() for kw in summary_keywords)


def is_sbi_reward_line(line: str) -> bool:
    """
    Check if a line is an SBI cashback/reward line.

    Args:
        line: Line to check

    Returns:
        True if this is a reward line
    """
    reward_keywords = ['cashback', 'bonus', 'reward', 'points']
    return any(kw in line.lower() for kw in reward_keywords)
