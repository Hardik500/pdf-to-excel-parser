"""
Generic regex patterns for financial statements.
These patterns work across multiple banks and statement types.
"""

import re
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass

# Common date patterns
DATE_PATTERN_DDMMYYYY = re.compile(r'(\d{1,2}/\d{1,2}/\d{2,4})')
DATE_PATTERN_DDMMMYYYY = re.compile(r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})', re.IGNORECASE)
DATE_PATTERN_YYYYMMDD = re.compile(r'(\d{4}-\d{1,2}-\d{1,2})')

# Amount patterns - handles both Indian (1,00,000) and standard (100,000) formats
# Match amounts with at least 1 digit before decimal, including small amounts like 5.00
# The pattern must have at least 2 digits before decimal OR contain commas
AMOUNT_PATTERN = re.compile(r'([0-9,]+(?:\.[0-9]+)?)\s*(Cr|CR|Dr|DR)?', re.IGNORECASE)
AMOUNT_INR = re.compile(r'[₹]?\s*([0-9,]+(?:\.[0-9]+)?)\s*(Cr|CR|Dr|DR)?', re.IGNORECASE)

# Skip keywords for non-transaction lines
SKIP_KEYWORDS = {
    'statement date', 'payment due', 'credit limit', 'available balance',
    'opening balance', 'closing balance', 'total amount', 'minimum amount',
    'personal details', 'address', 'email', 'phone', 'customer id',
    'account number', 'branch code', 'product code', 'ifsc',
    'micr code', 'statement from', 'statement to', 'period',
    'thank you', 'regards', 'sincerely',
    'reward points', 'summary', 'transaction details', 'transaction date',
    'description', 'amount', 'balance', 'reference', 'chq',
    'value date', 'withdrawal', 'deposit', 'narration', 'cr',
    'debit', 'credit', 'cheque', 'no.', 'serial', 'sl',
    'page', 'page no', 'page number', 'continued', 'end',
    'account summary', 'card summary', 'transaction summary',
    'fees', 'charges', 'interest', 'gst', 'tax',
    'important', 'messages', 'notes', 'terms', 'conditions',
    'reward', 'points', 'earnings', 'bonus', 'cashback',
    'emi', 'flexipay', 'encash', 'balance transfer',
    'mobile', 'mobile no', 'mobile number', 'landline',
    'website', 'www', 'http', 'email id', 'fax',
    'address:', 'branch:', 'account:', 'card:',
    'your', 'customer', 'member', 'client', 'holder',
    'beneficiary', 'payer', 'recipient', 'sender',
    'transaction type', 'transaction id', 'txn id',
    'ref no', 'reference number', 'transaction reference',
    'card holder', 'cardholder', 'card no', 'card number',
    'statement period', 'billing period', 'due date',
    'paid date', 'transaction id', 'ref no',
}

SKIP_PATTERNS = [
    r'^\s*[-_=]+\s*$',
    r'^\s*Page\s+\d+\s*[-=]*$',
    r'^\s*continued\s*$',
    r'^\s*End\s*$',
    r'^\s*[^a-zA-Z0-9@#\$%\^&\*\(\)\-_=\+\[\]\{\}\|;:\'",.<>\/?\\]+$',
]


@dataclass
class TransactionMatch:
    """Result of matching a line to a transaction pattern."""
    date: Optional[str]
    description: Optional[str]
    amount: Optional[float]
    is_credit: Optional[bool]
    raw_line: str


def is_skip_line(line: str) -> bool:
    """Check if a line should be skipped (not a transaction)."""
    if not line or not line.strip():
        return True

    line_lower = line.lower()

    # First check for patterns that indicate non-transaction lines
    for pattern in SKIP_PATTERNS:
        if re.match(pattern, line.strip()):
            return True

    # For keywords, check if they appear as whole words, not as substrings
    # This prevents false positives like "credit" in "UPI-CREDCLUB"
    for keyword in SKIP_KEYWORDS:
        # Use word boundary matching
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, line_lower):
            return True

    return False


def extract_date(line: str) -> Optional[str]:
    """Extract date from a line of text."""
    # Try DD/MM/YYYY format first
    match = DATE_PATTERN_DDMMYYYY.search(line)
    if match:
        date_str = match.group(1)
        parts = date_str.split('/')
        if len(parts) == 3:
            day, month, year = parts
            if len(year) == 2:
                year_int = int(year)
                year = f"20{year_int}" if year_int < 50 else f"19{year_int}"
            return f"{day.zfill(2)}/{month.zfill(2)}/{year}"

    # Try DD Mon YYYY format
    match = DATE_PATTERN_DDMMMYYYY.search(line)
    if match:
        from statement_parser.utils.formatting import parse_date
        return parse_date(match.group(1))

    # Try YYYY-MM-DD format
    match = DATE_PATTERN_YYYYMMDD.search(line)
    if match:
        from statement_parser.utils.formatting import parse_date
        return parse_date(match.group(1))

    return None


def extract_amount(line: str) -> Optional[Tuple[float, bool]]:
    """Extract amount and type (debit/credit) from a line."""
    match = AMOUNT_PATTERN.search(line)
    if match:
        amount_str = match.group(1)
        suffix = match.group(2)

        amount_str = amount_str.replace(',', '')
        try:
            amount = float(amount_str)
            is_credit = suffix and suffix.upper() == 'CR'
            return (amount, is_credit)
        except ValueError:
            pass

    return None


def parse_generic_line(line: str) -> Optional[TransactionMatch]:
    """
    Parse a line using generic patterns (fallback for unknown formats).

    Key insight: For bank statements, amounts appear at the END of the line
    (after value date). We look for:
    - Date at the start
    - Amount at the end (largest numbers after the value date)
    """
    if is_skip_line(line):
        return None

    date = extract_date(line)
    if not date:
        return None

    # Find all amount matches in the line
    amount_matches = list(AMOUNT_PATTERN.finditer(line))
    if not amount_matches:
        return None

    # For bank statements, the actual transaction amount is typically at the end
    # after the value date. We look for amounts that appear after a date pattern.
    # The last amount in the line is often the balance (which we skip),
    # so we look for amounts that appear after the value date.

    # Try to find amount at the END of the line (before whitespace/remaining chars)
    line_end = line.rstrip()
    end_match = None
    for match in reversed(amount_matches):
        # Check if this match is near the end of the meaningful content
        after_pos = match.end()
        remaining = line[after_pos:].strip()
        # Only match if there's little after the amount (just whitespace/balance)
        if after_pos > len(line) * 0.5:  # At least halfway through the line
            end_match = match
            break

    if not end_match:
        # Fallback: use the first valid amount after the date
        date_pos = DATE_PATTERN_DDMMYYYY.search(line).end()
        for match in amount_matches:
            if match.start() > date_pos:
                end_match = match
                break

    if not end_match:
        return None

    amount_str = end_match.group(1)
    suffix = end_match.group(2)

    amount_str = amount_str.replace(',', '')
    try:
        amount = float(amount_str)
        is_credit = suffix and suffix.upper() == 'CR'
    except ValueError:
        return None

    if amount <= 0:
        return None

    # Extract description: everything between date and amount
    date_match = DATE_PATTERN_DDMMYYYY.search(line)
    amount_match = end_match

    start_pos = date_match.end() if date_match else 0
    end_pos = amount_match.start()

    description = line[start_pos:end_pos].strip()
    description = re.sub(r'^[\d\s]+', '', description)
    description = re.sub(r'[\d\s]+$', '', description)
    description = description.strip()

    if not description or len(description) < 3:
        return None

    return TransactionMatch(
        date=date,
        description=description,
        amount=amount,
        is_credit=is_credit,
        raw_line=line
    )


def find_transactions_generic(text: str) -> List[TransactionMatch]:
    """Find all transactions in text using generic patterns."""
    transactions = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    for line in lines:
        result = parse_generic_line(line)
        if result:
            transactions.append(result)

    return transactions


def extract_table_headers(text: str, delimiter: str = '\t') -> Optional[List[str]]:
    """Try to extract table headers from statement text."""
    lines = text.splitlines()

    for line in lines:
        if not line.strip() or len(line) < 20:
            continue

        for delim in ['\t', '|', '~', ',']:
            if delim in line:
                parts = [p.strip() for p in line.split(delim)]
                header_keywords = ['date', 'description', 'amount', 'narration',
                                   'withdrawal', 'deposit', 'balance', 'credit',
                                   'debit', 'reference', 'chq', 'value']

                if any(kw in ' '.join(parts).lower() for kw in header_keywords):
                    return parts

    return None


def detect_delimiter(text: str) -> str:
    """Detect the delimiter used in a statement."""
    delimiters = ['\t', '|', '~', ',']

    for delim in delimiters:
        if delim in text:
            return delim

    return ' '


# New: Pattern extraction functions for learning new formats

def extract_date_pattern(text: str) -> str:
    """Extract common date patterns from text for learning."""
    dates = []
    matches = DATE_PATTERN_DDMMYYYY.findall(text)
    for m in matches:
        dates.append(m)
    return '|'.join(dates[:5]) if dates else ''


def extract_amount_pattern(text: str) -> str:
    """Extract common amount patterns from text for learning."""
    amounts = []
    matches = AMOUNT_PATTERN.findall(text)
    for m in matches:
        amounts.append(m[0])
    return '|'.join(amounts[:5]) if amounts else ''


def extract_merchant_pattern(text: str) -> List[str]:
    """Extract merchant name patterns from transactions."""
    merchants = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    for line in lines:
        if is_skip_line(line):
            continue
        match = parse_generic_line(line)
        if match and match.description:
            merchants.append(match.description)
    return merchants[:10]
