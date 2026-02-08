"""
ICICI-specific regex patterns for parsing ICICI Bank and Amazon ICICI statements.

ICICI formats supported:
1. ICICI Credit Card (DD/MM/YYYY format)
2. Amazon ICICI Credit Card
3. Standard ICICI bank account statements
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


# ICICI Credit Card patterns
# Format: DD/MM/YYYY REF_NUM DESCRIPTION AMOUNT [CR]
ICICI_CC_PATTERN = re.compile(
    r'^(\d{2}/\d{2}/\d{4})\s+'            # Date DD/MM/YYYY
    r'(\d{10,12})\s+'                      # Reference number (11-12 digits)
    r'(.+?)\s+'                            # Description (non-greedy)
    r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*'  # Amount
    r'(CR)?$',                             # Credit marker (optional)
    re.IGNORECASE
)

# Amazon ICICI pattern - with reward points
AMAZON_ICICI_PATTERN = re.compile(
    r'^(\d{2}/\d{2}/\d{4})\s+'             # Date
    r'(\d{11})\s+'                         # Serial number
    r'(.+?)\s+'                             # Description
    r'(\d+)\s+'                             # Reward points
    r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*'  # Amount
    r'(CR)?$',                             # Credit marker
    re.IGNORECASE
)

# ICICI Bank Account - header pattern
ICICI_BANK_HEADER = re.compile(
    r'^(Date|Narration|Chq\.?/Ref\.?No\.?|Value\s+Dt|Withdrawal|Deposit|Balance|Amount)',
    re.IGNORECASE
)


def is_icici_credit_card(text: str) -> bool:
    """Check if text appears to be an ICICI credit card statement."""
    text_lower = text.lower()

    # Strong indicators
    if 'icici' in text_lower and 'credit card' in text_lower:
        return True
    if 'icici bank' in text_lower and 'card' in text_lower:
        return True
    if 'amazon' in text_lower and 'icici' in text_lower:
        return True

    # Look for ICICI-specific patterns
    if re.search(r'icici.*card.*\d{4}', text_lower):
        return True

    return False


def is_icici_bank_statement(text: str) -> bool:
    """Check if text appears to be an ICICI bank account statement."""
    text_lower = text.lower()

    # Check for ICICI bank indicators
    if 'icici bank' in text_lower or 'icici' in text_lower:
        return True

    # Check for bank statement specific patterns
    bank_keywords = ['withdrawal', 'deposit', 'balance', 'account no']
    for kw in bank_keywords:
        if kw in text_lower.replace(' ', ''):
            return True

    return False


def parse_icici_credit_card_line(line: str) -> Optional[TransactionMatch]:
    """
    Parse a single line from ICICI credit card statement.

    Format: DD/MM/YYYY REF_NUM DESCRIPTION AMOUNT [CR]
    Example: 06/04/2025 11049594561 IND*AMAZON HTTP://WWW.AM IN 29 599.00
    Example: 13/04/2025 11082771581 BBPS Payment received 0 9,720.00 CR

    Args:
        line: Line of text to parse

    Returns:
        TransactionMatch if successful, None otherwise
    """
    if is_skip_line(line):
        return None

    # Try standard ICICI pattern
    match = ICICI_CC_PATTERN.search(line)
    if match:
        date_str = match.group(1)
        ref_no = match.group(2)
        description = match.group(3).strip()
        amount_str = match.group(4)
        is_credit = match.group(5) is not None

        amount = parse_amount(amount_str)
        if amount <= 0:
            return None

        # Clean up description
        # Remove trailing points/percentage
        description = re.sub(r'\s+[-\d]+%?\s*$', '', description).strip()
        # Remove trailing reference-like patterns
        description = re.sub(r'\s+\d{1,3}$', '', description).strip()

        if not description or len(description) < 3:
            return None

        return TransactionMatch(
            date=date_str,
            description=description,
            amount=amount,
            is_credit=is_credit,
            raw_line=line
        )

    # Try Amazon ICICI pattern
    match = AMAZON_ICICI_PATTERN.search(line)
    if match:
        date_str = match.group(1)
        ref_no = match.group(2)
        description = match.group(3).strip()
        points = match.group(4)
        amount_str = match.group(5)
        is_credit = match.group(6) is not None

        amount = parse_amount(amount_str)
        if amount <= 0:
            return None

        # Clean up description
        description = re.sub(r'\s+\d{1,3}$', '', description).strip()

        if not description or len(description) < 3:
            return None

        return TransactionMatch(
            date=date_str,
            description=description,
            amount=amount,
            is_credit=is_credit,
            raw_line=line
        )

    return None


def extract_icici_reference(line: str) -> Optional[str]:
    """
    Extract reference number from ICICI transaction line.

    Args:
        line: Transaction line

    Returns:
        Reference number or None
    """
    # Look for 11-12 digit reference number
    match = re.search(r'\b(\d{11,12})\b', line)
    if match:
        return match.group(1)

    # Try other reference patterns
    patterns = [
        r'Ref#?\s*:?(\w+)',  # Ref# ABC123
        r'(?:Ref|Reference)\s*(?:No\.?)?\s*:?(\d{10,20})',  # Reference No: 1234567890
    ]

    for pattern in patterns:
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def is_icici_page_header(line: str) -> bool:
    """
    Check if a line is an ICICI page header.

    Args:
        line: Line to check

    Returns:
        True if this is a page header line
    """
    page_indicators = ['page', 'continued', 'continue', 'page no']
    return any(ind in line.lower() for ind in page_indicators)


def extract_icici_statement_dates(text: str) -> Optional[Tuple[str, str]]:
    """
    Extract statement period from ICICI statement.

    Args:
        text: Full statement text

    Returns:
        Tuple of (from_date, to_date) or None
    """
    # Pattern: "Statement period : DD Mon YYYY to DD Mon YYYY"
    match = re.search(
        r'Statement\s+period\s*[:\s]*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s*[Tt]o\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})',
        text,
        re.IGNORECASE
    )
    if match:
        return (match.group(1), match.group(2))

    # Alternative pattern with DD/MM/YYYY
    match = re.search(
        r'Statement\s+period\s*[:\s]*(\d{2}/\d{2}/\d{4})\s*[Tt]o\s*(\d{2}/\d{2}/\d{4})',
        text,
        re.IGNORECASE
    )
    if match:
        return (match.group(1), match.group(2))

    return None


def is_icici_reward_line(line: str) -> bool:
    """
    Check if a line is a reward points summary line.

    Args:
        line: Line to check

    Returns:
        True if this is a reward line
    """
    reward_keywords = ['earnings', 'points', 'reward', 'bonus', 'cashback']
    return any(kw in line.lower() for kw in reward_keywords)
