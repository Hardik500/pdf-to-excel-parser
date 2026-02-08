"""
HDFC-specific regex patterns for parsing HDFC Bank statements.

HDFC formats supported:
1. HDFC Credit Card (DD/MM/YYYY format)
2. HDFC Bank Account Statement (withdrawal/deposit format)
3. HDFC Combined statements
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


# HDFC Credit Card patterns
# Format: DD/MM/YYYY HH:MM:SS DESCRIPTION AMOUNT [Cr]
HDFC_CC_SINGLE_LINE = re.compile(
    r'^(\d{2}/\d{2}/\d{4})\s+'           # Date DD/MM/YYYY
    r'\d{2}:\d{2}:\d{2}\s+'              # Time HH:MM:SS
    r'(.+?)\s+'                           # Description (non-greedy)
    r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*'  # Amount
    r'(Cr|CR)?$',                         # Credit marker (optional)
    re.IGNORECASE
)

# HDFC Credit Card - alternative format with reference number
HDFC_CC_WITH_REF = re.compile(
    r'^(\d{2}/\d{2}/\d{4})\s+'            # Date DD/MM/YYYY
    r'\d{2}:\d{2}:\d{2}\s+'               # Time HH:MM:SS
    r'(.+?)\s+'                            # Description
    r'\d{10,20}\s+'                        # Reference number
    r'\d{2}/\d{2}/\d{4}\s+'               # Value date
    r'[-]?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s*'  # Amount (may be negative/empty)
    r'(Cr|CR)?$',                          # Credit marker
    re.IGNORECASE
)

# HDFC Bank Account - header pattern
HDFC_BANK_HEADER = re.compile(
    r'^(Date|Narration|Chq\.?/Ref\.?No\.?|Value\s+Dt|Withdrawal\s+Amt\.?|Deposit\s+Amt\.?|Closing\s+Balance)\s*',
    re.IGNORECASE
)

# HDFC Bank Account - transaction line (fixed width-like)
# Format: DD/MM/YY NARRATION REFERENCE DD/MM/YY AMOUNT (empty or AMOUNT) BALANCE
HDFC_BANK_TX_PATTERN = re.compile(
    r'^(\d{2}/\d{2}/\d{2})\s+'              # Date
    r'(.+?)\s+'                              # Narration
    r'(\d{12,20})\s+'                        # Chq/Ref No
    r'(\d{2}/\d{2}/\d{2})\s+'                # Value Dt
    r'([0-9,]+\.\d{2})?\s*'                  # Withdrawal Amt (optional)
    r'([0-9,]+\.\d{2})?\s*'                  # Deposit Amt (optional)
    r'([0-9,]+\.\d{2})\s*$',                 # Closing Balance
    re.IGNORECASE
)

# HDFC Bank - multi-line narration pattern
HDFC_BANK_NARRATION_CONT = re.compile(
    r'^(\s{2,}|\t{2,}|\s*\*\*|\s+continue|\s+continued)\s*$',
    re.IGNORECASE
)


def is_hdfc_credit_card(text: str) -> bool:
    """Check if text appears to be an HDFC credit card statement."""
    text_lower = text.lower()

    # Look for HDFC-specific patterns - must have actual transaction format
    # (date followed by time and amount) - this is the most reliable indicator
    if re.search(r'\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\s+.*\d{1,3},?\d*\.?\d{2}\s*(cr)?', text_lower):
        return True

    # HDFC Billed Statements format
    if 'hdfc bank ltd' in text_lower and 'billed statements' in text_lower:
        return True

    return False


def is_hdfc_bank_statement(text: str) -> bool:
    """Check if text appears to be an HDFC bank account statement."""
    text_lower = text.lower()

    # Check for HDFC bank indicators
    if 'hdfc bank' in text_lower or 'hdfc bank ltd' in text_lower:
        return True

    # Check for bank statement specific patterns
    bank_keywords = ['withdrawalamt', 'depositamt', 'closing balance', 'account branch']
    for kw in bank_keywords:
        if kw in text_lower.replace(' ', ''):
            return True

    return False


def parse_hdfc_credit_card_line(line: str) -> Optional[TransactionMatch]:
    """
    Parse a single line from HDFC credit card statement.

    Format: DD/MM/YYYY HH:MM:SS DESCRIPTION AMOUNT [Cr]
    Example: 12/03/2025 20:58:42 CALIFORNIA BURRITO BANGALORE 4 293.00
    Example: 19/03/2025 10:34:29 TELE TRANSFER CREDIT (Ref# ...) 1,02,613.00Cr

    Args:
        line: Line of text to parse

    Returns:
        TransactionMatch if successful, None otherwise
    """
    if is_skip_line(line):
        return None

    # Try single line pattern
    match = HDFC_CC_SINGLE_LINE.search(line)
    if match:
        date_str = match.group(1)
        description = match.group(2).strip()
        amount_str = match.group(3)
        is_credit = match.group(4) is not None

        amount = parse_amount(amount_str)
        if amount <= 0:
            return None

        # Clean up description
        # Remove trailing points number (single digit at end)
        description = re.sub(r'\s+\d{1,3}$', '', description).strip()

        # Remove amount from end
        description = re.sub(r'[0-9,]+\.\d{2}\s*(Cr|CR)?$', '', description).strip()

        if not description or len(description) < 3:
            return None

        return TransactionMatch(
            date=date_str,
            description=description,
            amount=amount,
            is_credit=is_credit,
            raw_line=line
        )

    # Try alternative pattern
    match = HDFC_CC_WITH_REF.search(line)
    if match:
        date_str = match.group(1)
        description = match.group(2).strip()
        amount_str = match.group(3)
        is_credit = match.group(4) is not None

        amount = parse_amount(amount_str)
        if amount <= 0:
            return None

        # Clean up reference number and points
        description = re.sub(r'\d{10,20}\s*\d{2}/\d{2}/\d{4}\s*[0-9,]+\.\d{2}\s*$', '', description).strip()

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


def parse_hdfc_bank_statement(text: str) -> List[TransactionMatch]:
    """
    Parse HDFC bank account statement.

    Format:
    Date      Narration          Chq./Ref.No.  Value Dt  Withdrawal  Deposit  Closing Balance
    01/01/26  POS 512967XXXXXX.. 00006001067.. 01/01/26  11,986.30            154,920.96

    Also handles multi-line narrations.

    Args:
        text: Full statement text

    Returns:
        List of TransactionMatch objects
    """
    transactions = []
    lines = text.splitlines()

    i = 0
    current_tx = None
    narration_buffer = []

    while i < len(lines):
        line = lines[i].strip()

        # Skip headers and empty lines
        if not line or HDFC_BANK_HEADER.match(line) or 'page' in line.lower():
            i += 1
            continue

        # Try to match transaction line
        match = HDFC_BANK_TX_PATTERN.match(line)
        if match:
            # Save previous transaction if any
            if current_tx:
                current_tx.description = ' '.join(narration_buffer).strip()
                if current_tx.description:
                    transactions.append(current_tx)
                narration_buffer = []

            # Parse new transaction
            date_str = match.group(1)
            narration = match.group(2).strip()
            ref_no = match.group(3)
            value_dt = match.group(4)
            withdrawal = match.group(5)
            deposit = match.group(6)
            balance = match.group(7)

            # Determine debit/credit
            is_credit = deposit is not None and withdrawal is None

            if is_credit:
                amount = parse_amount(deposit)
            else:
                amount = parse_amount(withdrawal) if withdrawal else 0

            if amount > 0:
                current_tx = TransactionMatch(
                    date=date_str,
                    description=narration,
                    amount=amount,
                    is_credit=is_credit,
                    raw_line=line
                )
        else:
            # This might be a continuation of narration
            if current_tx and line and not HDFC_BANK_NARRATION_CONT.match(line):
                narration_buffer.append(line.strip())

        i += 1

    # Don't forget the last transaction
    if current_tx:
        current_tx.description = ' '.join(narration_buffer).strip()
        if current_tx.description:
            transactions.append(current_tx)

    return transactions


def extract_hdfc_reference(line: str) -> Optional[str]:
    """
    Extract reference number from HDFC transaction line.

    Args:
        line: Transaction line

    Returns:
        Reference number or None
    """
    # Look for reference patterns
    patterns = [
        r'Ref#?\s*:?(\w+)',  # Ref# ABC123
        r'(?:Ref|Reference)\s*(?:No\.?)?\s*:?(\d{10,20})',  # Reference No: 1234567890
        r'(\d{12,20})',  # 12+ digit number
    ]

    for pattern in patterns:
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def is_hdfc_page_header(line: str) -> bool:
    """
    Check if a line is an HDFC page header.

    Args:
        line: Line to check

    Returns:
        True if this is a page header line
    """
    page_indicators = ['page no', 'page no.', 'page:', 'continued', 'continue']
    return any(ind in line.lower() for ind in page_indicators)


def extract_hdfc_statement_dates(text: str) -> Optional[Tuple[str, str]]:
    """
    Extract statement period from HDFC statement.

    Args:
        text: Full statement text

    Returns:
        Tuple of (from_date, to_date) or None
    """
    # Pattern: "Statement From: DD/MM/YYYY To: DD/MM/YYYY"
    match = re.search(
        r'(?:Statement From|Statement\s+Period)[^\d]*(\d{2}/\d{2}/\d{4})\s*[Tt]o[:\s]*(\d{2}/\d{2}/\d{4})',
        text,
        re.IGNORECASE
    )
    if match:
        return (match.group(1), match.group(2))

    # Alternative pattern
    match = re.search(
        r'(\d{2}/\d{2}/\d{4})\s*[-–]\s*(\d{2}/\d{2}/\d{4})',
        text
    )
    if match:
        return (match.group(1), match.group(2))

    return None
