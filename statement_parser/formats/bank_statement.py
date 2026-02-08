"""
Bank account statement parser.

Handles:
1. HDFC Bank statements (fixed-width format)
2. ICICI Bank statements
3. SBI Bank statements
4. Generic bank statements with withdrawal/deposit columns

Generic credit/debit detection:
- For statements with separate withdrawal/deposit columns:
  - Withdrawal column (debit): first amount appears early after value date (gap <= 2 chars)
  - Deposit column (credit): first amount appears far after value date (gap >= 5 chars)
- For collapsed PDF text (single column):
  - Use description clues: 'CR', 'CRED', 'CREDIT', 'FT-', 'DEPOSIT', 'CREDCLUB', etc.
"""

import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from statement_parser.formats.base import BaseParser, ParseResult
from statement_parser.patterns.generic import (
    is_skip_line,
    parse_generic_line,
    DATE_PATTERN_DDMMYYYY,
    AMOUNT_PATTERN,
)
from statement_parser.utils.formatting import parse_amount, parse_date


class BankStatementParser(BaseParser):
    """
    Parser for bank account statements.

    Handles HDFC, ICICI, SBI, and generic bank statements.
    """

    statement_type = "bank"

    def __init__(self):
        """Initialize the bank statement parser."""
        super().__init__()
        self.parser_name = "BankStatementParser"

    def can_parse(self, text: str) -> bool:
        """Check if this parser can handle the given text."""
        text_lower = text.lower()

        bank_indicators = [
            'withdrawal amt', 'deposit amt', 'closing balance',
            'account branch', 'withdrawal', 'deposit',
            'statement of accounts', 'bank statement',
        ]

        for indicator in bank_indicators:
            if indicator in text_lower:
                return True

        return False

    def parse(self, text: str) -> ParseResult:
        """Parse bank statement text."""
        transactions = []
        errors = []
        warnings = []

        # Detect if this is a CSV format (comma-separated with headers)
        is_csv = ',' in text and self._has_csv_structure(text)

        if is_csv:
            result = self._parse_csv(text)
            transactions.extend(result)
        else:
            # Try to parse using the fixed-width format first (HDFC style)
            result = self._parse_hdfc_style(text)
            transactions.extend(result)

        # Deduplicate
        transactions = self._deduplicate(transactions)

        # Validate
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

    def _has_csv_structure(self, text: str) -> bool:
        """Check if text has CSV structure with headers."""
        lines = text.splitlines()
        if not lines:
            return False

        # Look for header line with comma-separated column names
        for line in lines[:5]:
            if not line.strip():
                continue
            # Check if line has comma-separated values that look like headers
            parts = line.split(',')
            if len(parts) >= 4:
                line_lower = line.lower()
                header_keywords = ['date', 'description', 'narration', 'debit', 'credit',
                                  'amount', 'balance', 'reference', 'value']
                found_keywords = sum(1 for kw in header_keywords if kw in line_lower)
                if found_keywords >= 3:
                    return True
        return False

    def _parse_csv(self, text: str) -> List[Dict[str, Any]]:
        """Parse CSV format bank statements."""
        transactions = []
        lines = text.splitlines()

        if not lines:
            return transactions

        # First, find the header line and map columns
        header_idx = -1
        column_mapping = {}
        delimiter = ','

        header_keywords = {
            'date': ['date', 'posting', 'transaction', 'dt'],
            'description': ['description', 'narration', 'merchant', 'payee'],
            'debit': ['debit', 'withdrawal', 'dr', 'amount'],
            'credit': ['credit', 'deposit', 'cr'],
            'balance': ['balance', 'closing'],
            'reference': ['reference', 'ref', 'chq', 'txn'],
        }

        for i, line in enumerate(lines):
            line_lower = line.lower()
            parts = line.split(delimiter)

            # Check if this is a header line
            found_keywords = []
            for field_name, variations in header_keywords.items():
                for var in variations:
                    if var in line_lower:
                        # Find the column index
                        for j, part in enumerate(parts):
                            if var in part.lower():
                                if field_name not in column_mapping:
                                    column_mapping[field_name] = j
                                break
                        found_keywords.append(field_name)
                        break

            if len(found_keywords) >= 3:
                header_idx = i
                break

        # Now parse data rows
        for i, line in enumerate(lines):
            if i <= header_idx or not line.strip():
                continue

            parts = line.split(delimiter)

            # Extract fields based on column mapping
            date_str = parts[column_mapping.get('date', 0)].strip() if 'date' in column_mapping and len(parts) > column_mapping['date'] else ''
            narration = parts[column_mapping.get('description', 1)].strip() if 'description' in column_mapping and len(parts) > column_mapping['description'] else ''
            debit_str = parts[column_mapping.get('debit', 3)].strip() if 'debit' in column_mapping and len(parts) > column_mapping['debit'] else ''
            credit_str = parts[column_mapping.get('credit', 4)].strip() if 'credit' in column_mapping and len(parts) > column_mapping['credit'] else ''
            balance_str = parts[column_mapping.get('balance', 6)].strip() if 'balance' in column_mapping and len(parts) > column_mapping['balance'] else ''

            # Skip if no valid data
            if not date_str or (not debit_str and not credit_str):
                continue

            # Parse values
            date_normalized = parse_date(date_str)
            if not date_normalized:
                continue

            debit = parse_amount(debit_str) if debit_str else 0.0
            credit = parse_amount(credit_str) if credit_str else 0.0
            balance = parse_amount(balance_str) if balance_str else 0.0

            # Skip zero-amount transactions
            if debit == 0 and credit == 0:
                continue

            transactions.append({
                'date': date_normalized,
                'description': narration,
                'narration': narration,
                'value_date': date_normalized,
                'debit': debit,
                'credit': credit,
                'balance': balance,
                'reference': '',
                'card_no': '',
                'type': 'credit' if credit > 0 else 'debit',
                'merchant': narration,
            })

        return transactions

    def _is_credit_transaction(self, line: str, value_date_match: re.Match,
                                 after_value_date: str) -> bool:
        """
        Determine if a transaction is credit (deposit) or debit (withdrawal).

        Uses a two-tier approach:
        1. Gap analysis: Large gap (5+ chars) between first amount and balance = deposit column
        2. Description clues: For collapsed PDF text, check for credit keywords

        Args:
            line: Original line text
            value_date_match: Regex match for the value date
            after_value_date: Text after the value date

        Returns:
            True if transaction is credit/deposit, False if debit/withdrawal
        """
        # Find all amounts in the after-value-date portion
        amounts = list(AMOUNT_PATTERN.finditer(after_value_date))

        if len(amounts) < 2:
            return False

        # Check the gap between first amount and balance
        first_amt_end = after_value_date.find(amounts[0].group(1)) + len(amounts[0].group(1))
        balance_start = after_value_date.find(amounts[-1].group(1))
        gap = after_value_date[first_amt_end:balance_start]

        # Large gap (5+ spaces) indicates deposit column (credit)
        # HDFC format: Withdrawal column is ~8 chars from value date, Deposit column is ~30+ chars
        is_credit_by_gap = len(gap) >= 5

        if is_credit_by_gap:
            return True

        # For collapsed PDF text (gap <= 2), use description clues
        if len(gap) <= 2:
            desc = line[:value_date_match.start()].strip()
            desc = re.sub(r'\s{2,}', ' ', desc)  # Normalize whitespace
            desc_upper = desc.upper()

            # Common credit keywords across bank statements
            credit_keywords = ['CR', 'CRED', 'CREDIT', 'FT-', 'DEPOSIT', 'CREDCLUB',
                             'CRED.C', 'NEFT', 'RTGS', 'IMPS', 'TRANSFER IN', 'CREDITED']
            if any(kw in desc_upper for kw in credit_keywords):
                return True

        return False

    def _extract_transaction_amounts(self, after_value_date: str, is_credit: bool) -> tuple:
        """
        Extract withdrawal and deposit amounts from the after-value-date portion.

        Args:
            after_value_date: Text after the value date containing amounts
            is_credit: Whether this is a credit transaction

        Returns:
            Tuple of (withdrawal, deposit)
        """
        amounts = list(AMOUNT_PATTERN.finditer(after_value_date))
        if len(amounts) < 2:
            return (0.0, 0.0)

        first_amount = parse_amount(amounts[0].group(1))

        if is_credit:
            deposit = first_amount
            withdrawal = 0.0
        else:
            withdrawal = first_amount
            deposit = 0.0

        return (withdrawal, deposit)

    def _parse_hdfc_style(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse fixed-width bank statements with withdrawal/deposit columns.

        This method handles bank statements in the common format:
        Date      Narration          Chq/Ref  ValueDt  Withdrawal  Deposit  Balance
        01/01/26  CC 000485498...    00000... 01/01/26 64,065.00            90,855.96

        Key observations:
        - Date is at the start
        - Description follows (variable width)
        - Value date appears after the description
        - Withdrawal and Deposit are in separate columns
        - Either withdrawal OR deposit has a value (not both)
        - Balance is at the very end

        The strategy:
        1. Find value date position
        2. Extract amounts from text after value date
        3. First amount after value date is the transaction amount
        4. Last amount is always the balance
        5. Use gap analysis and description clues to determine credit vs debit
        """
        transactions = []
        lines = text.splitlines()

        for line in lines:
            line = line.strip()

            if not line or is_skip_line(line) or len(line) < 10:
                continue

            # Try to match the line starting with a date
            date_match = DATE_PATTERN_DDMMYYYY.match(line)
            if not date_match:
                continue

            date_str = date_match.group(1)
            date_normalized = parse_date(date_str)
            if not date_normalized:
                continue

            # Find position of value date
            value_date_match = DATE_PATTERN_DDMMYYYY.search(line, date_match.end())
            if not value_date_match:
                continue

            # Extract the part after value date
            after_value_date = line[value_date_match.end():].strip()

            # Find all amounts in this part
            amounts = list(AMOUNT_PATTERN.finditer(after_value_date))

            if len(amounts) < 2:
                # Need at least 2 amounts (transaction + balance)
                continue

            # The LAST amount is always the balance
            balance = parse_amount(amounts[-1].group(1))

            # Determine if this is a credit or debit transaction
            is_credit = self._is_credit_transaction(line, value_date_match, after_value_date)

            # Extract withdrawal and deposit amounts
            withdrawal, deposit = self._extract_transaction_amounts(after_value_date, is_credit)

            # Extract description for the transaction record
            description = line[:value_date_match.start()].strip()
            description = re.sub(r'\s{2,}', ' ', description)  # Normalize whitespace

            if description and len(description) > 3:
                # Extract reference number (between description and value date)
                reference = self._extract_reference(line, value_date_match)

                transactions.append({
                    'date': date_normalized,
                    'description': description,
                    'narration': description,
                    'value_date': date_normalized,
                    'debit': withdrawal,
                    'credit': deposit,
                    'balance': balance,
                    'reference': reference,
                    'card_no': '',
                    'type': 'credit' if is_credit else 'debit',
                    'merchant': description,
                })

        return transactions

    def _extract_reference(self, line: str, value_date_match: re.Match) -> str:
        """Extract reference number from line."""
        # Reference is between description and value date
        after_desc = line[value_date_match.start():].strip()
        # Find alphanumeric reference pattern
        ref_match = re.search(r'([A-Z0-9]{8,20})', after_desc)
        if ref_match:
            return ref_match.group(1)
        return ""

    def _parse_generic(self, text: str) -> List[Dict[str, Any]]:
        """Fallback to generic parsing."""
        transactions = []
        lines = text.splitlines()

        for line in lines:
            line = line.strip()

            if is_skip_line(line) or len(line) < 10:
                continue

            # Try generic parsing
            match = parse_generic_line(line)
            if match and match.amount > 0:
                tx = {
                    'date': match.date,
                    'description': match.description,
                    'narration': match.description,
                    'value_date': match.date,
                    'debit': match.amount if not match.is_credit else 0,
                    'credit': match.amount if match.is_credit else 0,
                    'balance': 0,
                    'reference': '',
                    'card_no': '',
                    'type': 'credit' if match.is_credit else 'debit',
                    'merchant': match.description,
                }
                transactions.append(tx)

        return transactions
