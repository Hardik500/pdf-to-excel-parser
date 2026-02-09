"""
Statement type detection module.

Uses a hierarchy of detection strategies:
1. Header-based detection (look for keywords in first few lines)
2. Column-based detection (analyze header row patterns)
3. Pattern-based detection (match known patterns)
4. Heuristic-based detection (table structure analysis)
"""

import re
from typing import Optional, List, Dict, Any
from enum import Enum


class StatementType(Enum):
    """Types of financial statements."""
    BANK = "bank"              # Bank account statements
    CREDIT_CARD = "credit_card"  # Credit card statements
    UPI = "upi"                # UPI/PhonePe/GooglePay statements
    UNKNOWN = "unknown"        # Cannot determine type
    COMBINED = "combined"      # Multiple statements in one file


# Detection keywords per statement type
BANK_KEYWORDS = {
    'header': ['statement of accounts', 'bank statement', 'account statement',
               'account branch', 'account no', 'account number'],
    'columns': ['withdrawal amt', 'deposit amt', 'withdrawal', 'deposit',
                'closing balance', 'balance', 'narration'],
    'text': ['hdfc bank', 'icici bank', 'sbi', 'axis bank', 'kotak bank',
             'yes bank', 'state bank', 'bank ltd'],
}

CREDIT_CARD_KEYWORDS = {
    'header': ['credit card', 'card statement', 'card no', 'card number',
               'card summary', 'total amount due', 'minimum amount due'],
    'columns': ['transaction details', 'amount', 'dr', 'cr', 'debit', 'credit'],
    'text': ['credit card', 'card holder', 'cardsummary'],
}

UPI_KEYWORDS = {
    'header': ['upi', 'phonepe', 'google pay', 'gpay', 'payment app',
               'wallet statement', 'transaction history'],
    'columns': ['merchant', 'transaction', 'amount', 'reference'],
    'text': ['ixigo', 'au bank', 'aubl', 'phonepe', 'googlepay', 'upi'],
}

# Combined statement indicators
COMBINED_INDICATORS = [
    'combined', 'multiple', 'merged', 'merged statement',
    'statement 1', 'statement 2', 'part 1', 'part 2',
]


def detect_statement_type(text: str) -> StatementType:
    """
    Detect the type of financial statement from text content.

    For a generic parser approach, always return BANK type to use the
    unified BankStatementParser for all statement formats.

    Args:
        text: Statement text to analyze

    Returns:
        StatementType.BANK for all inputs
    """
    return StatementType.BANK


def _score_bank_statement(text: str) -> int:
    """Score how likely text is a bank statement."""
    score = 0

    # Header keywords (high weight)
    for kw in BANK_KEYWORDS['header']:
        if kw in text:
            score += 3

    # Column keywords (medium weight)
    for kw in BANK_KEYWORDS['columns']:
        if kw in text:
            score += 2

    # Text indicators (medium weight)
    for kw in BANK_KEYWORDS['text']:
        if kw in text:
            score += 1

    # Bank account patterns
    if re.search(r'account\s*(no\.?|number)\s*[:\s]*\d{10,}', text):
        score += 2

    # Withdrawal/Deposit pattern (very strong for bank statements)
    if 'withdrawal' in text and 'deposit' in text:
        score += 3

    # INR prefix pattern (very strong indicator for Indian bank statements)
    # Look for "INR X,XXX.XX" pattern
    if re.search(r'INR\s*[0-9,]+\.\d{2}', text):
        score += 3

    # Separate Debits/Credits columns (strong indicator for bank statements)
    if 'debits' in text and 'credits' in text:
        score += 3

    return score


def _score_credit_card(text: str) -> int:
    """Score how likely text is a credit card statement."""
    score = 0

    # Header keywords (high weight)
    for kw in CREDIT_CARD_KEYWORDS['header']:
        if kw in text:
            score += 3

    # Column keywords (medium weight)
    for kw in CREDIT_CARD_KEYWORDS['columns']:
        if kw in text:
            score += 2

    # Text indicators (medium weight)
    for kw in CREDIT_CARD_KEYWORDS['text']:
        if kw in text:
            score += 1

    # Total amount due / Minimum amount due (strong indicator for credit cards)
    if 'total amount due' in text or 'minimum amount due' in text:
        score += 3

    # Card number pattern (strong indicator)
    if re.search(r'card\s*(no\.?|number)\s*[:\s]*\d{4}[\s*]*\d{4}[\s*]*\d{4}', text):
        score += 3

    # Credit/Debit column pattern (weaker indicator - also appears in bank statements)
    # Reduce weight because bank statements also have debit/credit columns
    if 'debit' in text and 'credit' in text:
        score += 1

    return score


def _score_upi_statement(text: str) -> int:
    """Score how likely text is a UPI/payment app statement."""
    score = 0

    # Header keywords (high weight)
    for kw in UPI_KEYWORDS['header']:
        if kw in text:
            score += 3

    # Column keywords (medium weight)
    for kw in UPI_KEYWORDS['columns']:
        if kw in text:
            score += 2

    # Text indicators - reduce weight for "upi" in transaction descriptions
    for kw in UPI_KEYWORDS['text']:
        # Count occurrences - if it's just in transaction descriptions (not header/columns),
        # don't give full weight
        if kw in text:
            score += 1

    # Stronger check: look for UPI-specific patterns (not just "UPI" appearing anywhere)
    # UPI statements typically have:
    # 1. "UPI" in header/column headers
    # 2. Merchant -> Amount -> Date pattern (not "UPI-SOMETHING" in narrations)
    upi_in_headers = any(
        kw in text.lower()
        for kw in ['upi ref', 'upi reference', 'upi id', 'upi transaction']
    )
    if upi_in_headers:
        score += 3

    # Merchant + Amount + Date pattern (strong for UPI)
    # Look for patterns like "Merchant Name\n12 ₹2,948.00\nJan 26 Dr"
    if re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+.*\n.*\d{1,2}\s*₹?.*\n.*[A-Z][a-z]{2}\s+\d{1,2}', text, re.DOTALL):
        score += 3

    return score


def _is_combined_statement(text: str) -> bool:
    """Check if text appears to be a combined/multi-statement file."""
    indicator_count = 0

    for indicator in COMBINED_INDICATORS:
        if indicator in text:
            indicator_count += 1

    # If multiple indicators found, likely combined
    return indicator_count >= 2


def detect_header_structure(text: str) -> Dict[str, Any]:
    """
    Analyze the header/column structure of a statement.

    Args:
        text: Statement text

    Returns:
        Dict with structure analysis
    """
    lines = text.splitlines()
    result = {
        'delimiter': None,
        'column_names': [],
        'has_table_structure': False,
        'header_line_index': -1,
    }

    # Find potential header line
    for i, line in enumerate(lines):
        if _looks_like_header(line):
            result['header_line_index'] = i
            result['column_names'] = _extract_column_names(line)
            result['delimiter'] = _detect_delimiter(line)
            result['has_table_structure'] = True
            break

    return result


def _looks_like_header(line: str) -> bool:
    """Check if a line looks like a table header."""
    header_keywords = {
        'date', 'description', 'amount', 'narration', 'withdrawal',
        'deposit', 'balance', 'credit', 'debit', 'reference', 'merchant',
        'transaction', 'value', 'chq', 'ref', 'no'
    }

    line_lower = line.lower()
    words = set(re.findall(r'\b\w+\b', line_lower))

    # Header should have at least 3 header keywords
    matching_keywords = words.intersection(header_keywords)
    return len(matching_keywords) >= 3


def _extract_column_names(line: str) -> List[str]:
    """Extract column names from a header line."""
    delimiter = _detect_delimiter(line)

    if delimiter == ' ':
        # For space-delimited, look for uppercase words (common in headers)
        words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', line)
        return [w.lower() for w in words[:10]]

    parts = [p.strip().lower() for p in line.split(delimiter)]
    return [p for p in parts if p][:10]


def _detect_delimiter(line: str) -> str:
    """Detect the delimiter used in a line."""
    delimiters = ['\t', '|', '~', ',']

    for delim in delimiters:
        if delim in line:
            return delim

    return ' '


def get_column_mapping(structure: Dict[str, Any]) -> Dict[str, int]:
    """
    Create a mapping of standard field names to column indices.

    Args:
        structure: Header structure analysis from detect_header_structure

    Returns:
        Dict mapping standard names to column indices
    """
    column_names = structure.get('column_names', [])
    mapping = {}

    standard_fields = {
        'date': ['date', 'posting date', 'transaction date', 'dt'],
        'description': ['description', 'narration', 'merchant', 'payee',
                        'transaction details', 'particulars'],
        'amount': ['amount', 'value', 'dr', 'cr', 'debit', 'credit'],
        'debit': ['debit', 'withdrawal', 'dr', 'amount'],
        'credit': ['credit', 'deposit', 'cr', 'amount'],
        'balance': ['balance', 'closing balance', 'balance'],
        'reference': ['reference', 'ref no', 'chq no', 'txn id', 'ref'],
    }

    for field_name, variations in standard_fields.items():
        for i, col_name in enumerate(column_names):
            if any(var in col_name for var in variations):
                mapping[field_name] = i
                break

    return mapping
