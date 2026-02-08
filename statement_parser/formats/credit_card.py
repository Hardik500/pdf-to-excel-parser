"""
Credit card statement parser.

Handles:
1. HDFC Credit Card statements
2. ICICI Credit Card statements (including Amazon ICICI)
3. SBI Credit Card statements
4. Generic credit card statements
"""

import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from statement_parser.formats.base import BaseParser, ParseResult
from statement_parser.patterns.hdfc import (
    is_hdfc_credit_card,
    parse_hdfc_credit_card_line,
)
from statement_parser.patterns.icici import (
    is_icici_credit_card,
    parse_icici_credit_card_line,
)
from statement_parser.patterns.sbi import (
    is_sbi_card,
    parse_sbi_credit_card_line,
)
from statement_parser.patterns.generic import (
    is_skip_line,
    parse_generic_line,
)
from statement_parser.utils.formatting import parse_amount, parse_date, normalize_description


class CreditCardParser(BaseParser):
    """
    Parser for credit card statements.

    Handles HDFC, ICICI, SBI, and generic credit card statements.
    """

    statement_type = "credit_card"

    def __init__(self):
        """Initialize the credit card parser."""
        super().__init__()
        self.parser_name = "CreditCardParser"

    def can_parse(self, text: str) -> bool:
        """
        Check if this parser can handle the given text.

        Args:
            text: Statement text to check

        Returns:
            True if this parser can handle the text
        """
        text_lower = text.lower()

        # Check for credit card indicators
        cc_indicators = [
            'credit card', 'card statement', 'card number',
            'total amount due', 'minimum amount due',
            'card summary', 'transaction details',
        ]

        for indicator in cc_indicators:
            if indicator in text_lower:
                return True

        # Check for bank-specific credit card patterns
        if is_hdfc_credit_card(text) or is_icici_credit_card(text) or is_sbi_card(text):
            return True

        return False

    def parse(self, text: str) -> ParseResult:
        """
        Parse credit card statement text.

        Args:
            text: Full statement text

        Returns:
            ParseResult with parsed transactions
        """
        transactions = []
        errors = []
        warnings = []

        # Try bank-specific parsers first
        if is_hdfc_credit_card(text):
            result = self._parse_hdfc_cc(text)
            transactions.extend(result)
        elif is_icici_credit_card(text):
            result = self._parse_icici_cc(text)
            transactions.extend(result)
        elif is_sbi_card(text):
            result = self._parse_sbi_cc(text)
            transactions.extend(result)
        else:
            # Use generic parser for unknown credit card statements
            result = self._parse_generic_cc(text)
            transactions.extend(result)

        # Deduplicate
        transactions = self._deduplicate(transactions)

        # Validate transactions
        valid_transactions = []
        for tx in transactions:
            if self._validate_transaction(tx):
                valid_transactions.append(tx)
            else:
                warnings.append(f"Invalid transaction: {tx.get('description', 'unknown')}")

        return ParseResult(
            transactions=valid_transactions,
            statement_type=self.statement_type,
            raw_text=text,
            metadata={
                'parser': self.parser_name,
                'transaction_count': len(valid_transactions),
            },
            errors=errors,
            warnings=warnings,
        )

    def _parse_hdfc_cc(self, text: str) -> List[Dict[str, Any]]:
        """Parse HDFC credit card statement."""
        transactions = []
        lines = text.splitlines()

        for line in lines:
            line = line.strip()

            if is_skip_line(line):
                continue

            match = parse_hdfc_credit_card_line(line)
            if match and match.amount > 0:
                tx = {
                    'date': match.date,
                    'description': match.description,
                    'amount': match.amount,
                    'type': 'debit' if not match.is_credit else 'credit',
                    'card_no': '',
                    'reference': '',
                    'value_date': match.date,
                    'merchant': match.description,
                }
                transactions.append(tx)

        return transactions

    def _parse_icici_cc(self, text: str) -> List[Dict[str, Any]]:
        """Parse ICICI credit card statement."""
        transactions = []
        lines = text.splitlines()

        for line in lines:
            line = line.strip()

            if is_skip_line(line):
                continue

            match = parse_icici_credit_card_line(line)
            if match and match.amount > 0:
                tx = {
                    'date': match.date,
                    'description': match.description,
                    'amount': match.amount,
                    'type': 'debit' if not match.is_credit else 'credit',
                    'card_no': '',
                    'reference': '',
                    'value_date': match.date,
                    'merchant': match.description,
                }
                transactions.append(tx)

        return transactions

    def _parse_sbi_cc(self, text: str) -> List[Dict[str, Any]]:
        """Parse SBI credit card statement."""
        transactions = []
        lines = text.splitlines()

        for line in lines:
            line = line.strip()

            if is_skip_line(line):
                continue

            match = parse_sbi_credit_card_line(line)
            if match and match.amount > 0:
                tx = {
                    'date': match.date,
                    'description': match.description,
                    'amount': match.amount,
                    'type': 'debit' if not match.is_credit else 'credit',
                    'card_no': '',
                    'reference': '',
                    'value_date': match.date,
                    'merchant': match.description,
                }
                transactions.append(tx)

        return transactions

    def _parse_generic_cc(self, text: str) -> List[Dict[str, Any]]:
        """Parse generic credit card statement format."""
        transactions = []
        lines = text.splitlines()

        # First pass: Try single-line parsing
        for line in lines:
            line = line.strip()

            if is_skip_line(line) or self._is_skip_line(line):
                continue

            # Try generic parsing
            match = parse_generic_line(line)
            if match and match.amount > 0:
                tx = {
                    'date': match.date,
                    'description': match.description,
                    'amount': match.amount,
                    'type': 'debit' if not match.is_credit else 'credit',
                    'card_no': '',
                    'reference': '',
                    'value_date': match.date,
                    'merchant': match.description,
                }
                transactions.append(tx)

        # Second pass: Try multi-line pattern (3-line format)
        if len(transactions) < 3:
            transactions.extend(self._parse_multiline_cc(text))

        return transactions

    def _parse_multiline_cc(self, text: str) -> List[Dict[str, Any]]:
        """Parse multi-line credit card transactions."""
        import re
        from statement_parser.utils.formatting import parse_date, parse_amount

        transactions = []
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        i = 0
        while i < len(lines) - 2:
            line1 = lines[i]      # Merchant/description
            line2 = lines[i + 1]  # Day + Amount
            line3 = lines[i + 2]  # Date (Mon DD) + Dr/Cr

            # Check for 3-line pattern: Description, Day Amount, Date Dr/Cr
            # Example: "MC DONALDS BENGALURU IN\n12 ₹798.48\nJan 26 Dr 1015 RP"
            day_match = re.match(r'^(\d{1,2})\s*₹?\s*([0-9,]+\.\d{2})$', line2, re.IGNORECASE)

            if day_match:
                day = day_match.group(1)
                amount_str = day_match.group(2)

                drcr_match = re.search(r'(Dr|Cr|DR|CR)', line3, re.IGNORECASE)
                drcr = drcr_match.group(1).lower() if drcr_match else 'dr'

                # Extract month and day from line3
                date_match = re.match(r'^([A-Za-z]{3})\s+(\d{1,2})', line3, re.IGNORECASE)
                if date_match:
                    month = date_match.group(1)
                    day_num = date_match.group(2)

                    # Use 2025 as default year
                    year = '2025'
                    full_date = f"{day_num.zfill(2)} {month} {year}"
                    parsed_date = parse_date(full_date)

                    if parsed_date:
                        tx = {
                            'date': parsed_date,
                            'description': line1,
                            'amount': parse_amount(amount_str),
                            'type': 'credit' if drcr == 'cr' else 'debit',
                            'card_no': '',
                            'reference': '',
                            'value_date': parsed_date,
                            'merchant': line1,
                        }
                        transactions.append(tx)
                        i += 3
                        continue

            i += 1

        return transactions

    def _is_skip_line(self, line: str) -> bool:
        """Check if a line should be skipped entirely."""
        if not line or not line.strip():
            return True

        if len(line) < 10:
            return True

        # Don't skip if line has a date followed by amount (transaction line)
        import re
        from statement_parser.patterns.generic import DATE_PATTERN_DDMMYYYY, AMOUNT_PATTERN
        if DATE_PATTERN_DDMMYYYY.search(line) and AMOUNT_PATTERN.search(line):
            return False  # This is a transaction line, don't skip

        header_keywords = [
            'statement', 'page', 'page no', 'continued', 'end',
            'summary', 'total', 'balance', 'credit limit',
            'account summary', 'card summary',
            'reward points', 'earnings', 'bonus', 'cashback',
            'important', 'messages', 'notes', 'terms',
            'transaction type', 'transaction date',
            'description', 'reference',
            'opening balance', 'closing balance',
            'thank you', 'regards', 'sincerely',
            'address :', 'email :', 'card no', 'gst',
            'in case you wish', 'manager, hdfc bank',
            'credit limit available', 'cash limit',
        ]

        line_lower = line.lower()
        return any(kw in line_lower for kw in header_keywords)

    def _normalize_transaction(self, tx: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a credit card transaction to standard format."""
        normalized = super()._normalize_transaction(tx)
        normalized.update({
            'merchant': tx.get('merchant', tx.get('description', '')),
            'type': tx.get('type', 'unknown'),
            'card_no': tx.get('card_no', ''),
        })
        return normalized
