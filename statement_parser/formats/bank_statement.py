"""
Bank account statement parser.

Handles:
1. HDFC Bank statements (fixed-width format)
2. ICICI Bank statements
3. SBI Bank statements
4. Generic bank statements with withdrawal/deposit columns
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

    def _parse_hdfc_style(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse HDFC-style fixed-width bank statements.

        Format (fixed-width columns):
        Date      Narration          Chq/Ref  ValueDt  Withdrawal  Deposit  Balance
        01/01/26  CC 000485498...    00000... 01/01/26 64,065.00            90,855.96

        Key observations:
        - Date is at position 0-8
        - Description follows (variable width)
        - Value date appears after the description
        - Withdrawal and Deposit are in separate columns
        - Either withdrawal OR deposit has a value (not both)
        - Balance is at the very end (after lots of whitespace)

        The strategy:
        1. Find value date position
        2. Extract amounts from the text after value date
        3. The FIRST amount after value date is the transaction (either withdrawal or deposit)
        4. The LAST amount is always the balance
        5. To determine if it's a debit or credit, check if there's a second amount
           that appears much later in the string (deposit column)
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

            # Determine if this is a debit or credit transaction:
            # - If withdrawal column has value: first amount = withdrawal (debit)
            # - If deposit column has value: first amount = deposit (credit)
            #
            # We detect this by checking the gap between first amount and balance:
            # - Small gap (1-2 chars) = withdrawal column (debit)
            # - Large gap (many spaces) = deposit column (credit)
            # The deposit column appears much further to the right than withdrawal column

            first_amount = parse_amount(amounts[0].group(1))
            last_amount = parse_amount(amounts[-1].group(1))

            # Check the gap between first amount and balance
            first_amt_end = after_value_date.find(amounts[0].group(1)) + len(amounts[0].group(1))
            balance_start = after_value_date.find(amounts[-1].group(1))
            gap = after_value_date[first_amt_end:balance_start]

            # Gap length determines if this is debit or credit
            # HDFC format: Withdrawal column is ~8 chars from value date, Deposit column is ~30+ chars
            # A gap of 5+ spaces indicates deposit column (credit)
            # But for PDF-extracted text (collapsed columns), we use description clues
            is_credit = len(gap) >= 5

            # For PDF text where columns are collapsed (gap = 1), use description clues
            if not is_credit and len(gap) <= 2:
                # Extract description from before value date
                desc = line[:value_date_match.start()].strip()
                desc = re.sub(r'\s{2,}', ' ', desc)  # Normalize whitespace

                # Check for credit keywords in description
                desc_upper = desc.upper()
                credit_keywords = ['CR', 'CRED', 'CREDIT', 'FT-', 'DEPOSIT', 'CREDCLUB', 'CRED.C']
                is_credit = any(kw in desc_upper for kw in credit_keywords)

                # Update first_amount if this is a credit (deposit)
                if is_credit:
                    deposit = first_amount
                    withdrawal = 0.0
                else:
                    withdrawal = first_amount
                    deposit = 0.0
            else:
                # Standard logic based on column gap
                if is_credit:
                    deposit = first_amount
                    withdrawal = 0.0
                else:
                    withdrawal = first_amount
                    deposit = 0.0

            amount = deposit if is_credit else withdrawal

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
