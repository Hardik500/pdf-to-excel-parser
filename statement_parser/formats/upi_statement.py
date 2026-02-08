"""
UPI/Third-party statement parser.

Handles:
1. Ixigo/AU Bank statements
2. PhonePe statements
3. Google Pay statements
4. Other UPI-based transaction statements
"""

import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from statement_parser.formats.base import BaseParser, ParseResult
from statement_parser.patterns.generic import (
    is_skip_line,
    parse_generic_line,
)
from statement_parser.utils.formatting import parse_amount, parse_date


@dataclass
class UPITransaction:
    """Internal representation of a UPI transaction."""
    date: str
    description: str
    amount: float
    is_credit: bool
    upi_ref: str
    merchant: str


class UPIStatementParser(BaseParser):
    """
    Parser for UPI and third-party payment platform statements.

    Handles Ixigo, AU Bank, PhonePe, Google Pay, and similar platforms.
    """

    statement_type = "upi"

    def __init__(self):
        """Initialize the UPI statement parser."""
        super().__init__()
        self.parser_name = "UPIStatementParser"
        self.upi_ref_pattern = re.compile(r'[A-Z0-9]{8,20}', re.IGNORECASE)

    def can_parse(self, text: str) -> bool:
        """
        Check if this parser can handle the given text.

        Args:
            text: Statement text to check

        Returns:
            True if this parser can handle the text
        """
        text_lower = text.lower()

        # Check for UPI-specific indicators
        upi_indicators = [
            'upi', 'phonepe', 'google pay', 'gpay', 'phone pe',
            'ixigo', 'au bank', 'aubl', 'au credit',
            'payment received', 'payment sent',
            'wallet', 'payment app',
        ]

        for indicator in upi_indicators:
            if indicator in text_lower:
                return True

        # Check for merchant payment patterns
        if self._has_merchant_pattern(text):
            return True

        return False

    def _has_merchant_pattern(self, text: str) -> bool:
        """
        Check if text has merchant payment patterns typical of UPI statements.

        Args:
            text: Statement text

        Returns:
            True if merchant pattern detected
        """
        # Look for common patterns:
        # - Merchant name on one line
        # - Amount on next line
        # - Date/Dr or Cr on third line

        lines = [l.strip() for l in text.splitlines() if l.strip()]
        merchant_pattern_count = 0

        for i in range(len(lines) - 2):
            line1 = lines[i]      # Description
            line2 = lines[i + 1]  # Day + Amount
            line3 = lines[i + 2]  # Month Year + Dr/Cr

            # Check for Ixigo-style 3-line pattern
            day_match = re.match(r'^\d{1,2}\s*₹?\s*[0-9,]+\.\d{2}$', line2, re.IGNORECASE)
            date_match = re.match(r'^[A-Za-z]{3}\s+\d{1,2}\s*(Dr|Cr)?$', line3, re.IGNORECASE)

            if day_match and date_match:
                merchant_pattern_count += 1

        return merchant_pattern_count >= 1

    def parse(self, text: str) -> ParseResult:
        """
        Parse UPI statement text.

        Args:
            text: Full statement text

        Returns:
            ParseResult with parsed transactions
        """
        transactions = []
        errors = []
        warnings = []

        # Try Ixigo/AU specific parsing first
        if 'ixigo' in text.lower() or 'au bank' in text.lower() or 'aubl' in text.lower():
            result = self._parse_ixigo_statement(text)
            transactions.extend(result)
        else:
            # Use generic UPI parsing
            result = self._parse_generic_upi(text)
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

    def _parse_ixigo_statement(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse Ixigo/AU Bank statement format.

        Format (3-line pattern):
        Merchant Name
        12 ₹2,948.00
        Jan 26 Dr 1015 RP

        Or single-line pattern:
        12 Jan 26 DESCRIPTION AMOUNT Dr/Cr
        """
        transactions = []
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        # Pattern 1: 3-line format
        i = 0
        while i < len(lines) - 2:
            line1 = lines[i]      # Description/merchant
            line2 = lines[i + 1]  # Day + Amount
            line3 = lines[i + 2]  # Month Year + Dr/Cr

            # Skip headers and non-transaction lines
            if is_skip_line(line1) or self._is_skip_line(line1):
                i += 1
                continue

            # Line 2 should match day + amount (with optional ₹)
            line2_match = re.match(
                r"^(\d{1,2})\s*(?:₹|Rs\.?)?\s*([0-9,]+\.\d{2})\s*(?:Dr|Cr)?\s*$",
                line2,
                re.IGNORECASE
            )

            # Line 3 should match "Mon YY Dr/Cr"
            line3_match = re.match(
                r"^[A-Za-z]{3}\s+\d{1,2}\s*(Dr|Cr|DR|CR)?.*$",
                line3,
                re.IGNORECASE
            )

            if line2_match and line3_match:
                day = line2_match.group(1)
                amount_str = line2_match.group(2)

                # Get Dr/Cr from line 3
                drcr_match = re.search(r'(Dr|Cr|DR|CR)', line3, re.IGNORECASE)
                if not drcr_match:
                    drcr_match = re.search(r'(Dr|Cr|DR|CR)', line2, re.IGNORECASE)

                drcr = drcr_match.group(1).lower() if drcr_match else "dr"

                # Extract "Mon YY" from line3
                mon_year_match = re.match(r'^([A-Za-z]{3}\s+\d{1,2})', line3)
                mon_year = mon_year_match.group(1) if mon_year_match else line3[:7].strip()

                # Reconstruct date
                full_date_str = f"{day} {mon_year}"

                description = line1
                amount = parse_amount(amount_str)
                is_credit = drcr == "cr"

                # Convert date
                try:
                    parsed_date = parse_date(full_date_str)
                    if not parsed_date:
                        from datetime import datetime
                        parsed_dt = datetime.strptime(full_date_str, "%d %b %y")
                        parsed_date = parsed_dt.strftime("%d/%m/%Y")

                    if description and len(description) > 2:
                        tx = {
                            'date': parsed_date,
                            'description': description,
                            'amount': amount,
                            'type': 'credit' if is_credit else 'debit',
                            'card_no': '',
                            'reference': '',
                            'value_date': parsed_date,
                            'merchant': description,
                            'upi_ref': '',
                        }
                        transactions.append(tx)
                except Exception:
                    pass

                i += 3
                continue

            i += 1

        # Pattern 2: Single-line format (fallback)
        if len(transactions) < 3:
            single_line_pattern = re.compile(
                r'^(\d{1,2})\s+'           # Day
                r'([A-Za-z]{3})\s+'        # Month
                r'(\d{2,4})\s+'            # Year
                r'(.+?)\s+'                # Description
                r'([0-9,]+\.\d{2})\s*'     # Amount
                r'(Dr|Cr|DR|CR|D|C)?$',    # Debit/Credit
                re.IGNORECASE
            )

            for line in lines:
                line = line.strip()
                if is_skip_line(line) or self._is_skip_line(line):
                    continue

                match = single_line_pattern.match(line)
                if match:
                    day = match.group(1)
                    month = match.group(2)
                    year = match.group(3)
                    description = match.group(4).strip()
                    amount_str = match.group(5)
                    drcr = match.group(6) or 'dr'

                    if len(year) == 2:
                        year_int = int(year)
                        year = f"20{year_int}" if year_int < 50 else f"19{year_int}"

                    full_date_str = f"{day} {month} {year}"
                    amount = parse_amount(amount_str)
                    is_credit = drcr.lower() == 'cr'

                    try:
                        parsed_date = parse_date(full_date_str)
                        if not parsed_date:
                            from datetime import datetime
                            parsed_dt = datetime.strptime(full_date_str, "%d %b %Y")
                            parsed_date = parsed_dt.strftime("%d/%m/%Y")

                        if description and len(description) > 2:
                            tx = {
                                'date': parsed_date,
                                'description': description,
                                'amount': amount,
                                'type': 'credit' if is_credit else 'debit',
                                'card_no': '',
                                'reference': '',
                                'value_date': parsed_date,
                                'merchant': description,
                                'upi_ref': '',
                            }
                            transactions.append(tx)
                    except Exception:
                        pass

        return transactions

    def _parse_generic_upi(self, text: str) -> List[Dict[str, Any]]:
        """Parse generic UPI/payment app statement format."""
        transactions = []
        lines = text.splitlines()

        for line in lines:
            line = line.strip()

            if is_skip_line(line) or self._is_skip_line(line):
                continue

            # Try generic parsing
            match = parse_generic_line(line)
            if match and match.amount > 0:
                # Extract UPI reference
                upi_ref = ''
                upi_match = self.upi_ref_pattern.search(line)
                if upi_match:
                    upi_ref = upi_match.group(0)

                tx = {
                    'date': match.date,
                    'description': match.description,
                    'amount': match.amount,
                    'type': 'credit' if match.is_credit else 'debit',
                    'card_no': '',
                    'reference': upi_ref,
                    'value_date': match.date,
                    'merchant': match.description,
                    'upi_ref': upi_ref,
                }
                transactions.append(tx)

        return transactions

    def _normalize_transaction(self, tx: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a UPI transaction to standard format."""
        normalized = super()._normalize_transaction(tx)
        normalized.update({
            'merchant': tx.get('merchant', tx.get('description', '')),
            'upi_ref': tx.get('upi_ref', ''),
            'type': tx.get('type', 'unknown'),
        })
        return normalized

    def _is_skip_line(self, line: str) -> bool:
        """Check if a line should be skipped entirely."""
        if not line or not line.strip():
            return True

        if len(line) < 5:
            return True

        header_keywords = [
            'statement', 'page', 'page no', 'continued', 'end',
            'summary', 'total', 'balance', 'credit limit',
            'payment due', 'account summary', 'card summary',
            'reward points', 'earnings', 'bonus', 'cashback',
            'important', 'messages', 'notes', 'terms',
            'transaction type', 'transaction date',
            'description', 'amount', 'reference',
            'opening balance', 'closing balance',
            'thank you', 'regards', 'sincerely',
            'hello', 'your', 'yourself', 'regarding',
        ]

        line_lower = line.lower()
        return any(kw in line_lower for kw in header_keywords)
