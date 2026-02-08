"""
Generic Statement Parser - The core parsing engine.

This parser uses pattern learning to adapt to any statement format.
Instead of bank-specific logic, it:
1. Detects the statement type (bank/credit card/upi)
2. Extracts column structure from headers
3. Learns patterns from successful parses
4. Applies patterns consistently to extract transactions

Key features:
- No AI by default
- Pattern-based parsing that adapts to new formats
- Can handle any bank's statement format
- Saves learned patterns for future use
"""

import re
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

from statement_parser.formats.base import BaseParser, ParseResult
from statement_parser.patterns.generic import (
    is_skip_line,
    parse_generic_line,
    find_transactions_generic,
    extract_table_headers,
    detect_delimiter,
    DATE_PATTERN_DDMMYYYY,
    DATE_PATTERN_DDMMMYYYY,
    AMOUNT_PATTERN,
)
from statement_parser.utils.formatting import parse_amount, parse_date, normalize_description


@dataclass
class ParsedStatement:
    """Result of parsing a statement."""
    transactions: List[Dict[str, Any]]
    statement_type: str
    columns_detected: Dict[str, int]
    patterns_learned: Dict[str, Any]


class GenericStatementParser(BaseParser):
    """
    A generic parser that adapts to any statement format.

    This is the main parser that should handle any bank statement.
    It uses:
    1. Column detection to understand the structure
    2. Pattern extraction to learn the format
    3. Adaptive parsing that works for any format
    """

    statement_type = "generic"

    def __init__(self):
        """Initialize the generic parser."""
        super().__init__()
        self.parser_name = "GenericStatementParser"
        self.patterns: Dict[str, Any] = {}
        self.columns_detected: Dict[str, int] = {}

    def can_parse(self, text: str) -> bool:
        """
        Check if this parser can handle the given text.

        This parser can handle any text that looks like a financial statement.
        """
        # Must have some transaction-like content
        lines = text.splitlines()

        # Look for date patterns
        has_dates = bool(DATE_PATTERN_DDMMYYYY.search(text) or DATE_PATTERN_DDMMMYYYY.search(text))

        # Look for amount patterns
        has_amounts = bool(AMOUNT_PATTERN.search(text))

        # Must have some structure
        has_non_empty = any(l.strip() for l in lines)

        return has_dates and has_amounts and has_non_empty

    def parse(self, text: str) -> ParseResult:
        """
        Parse a statement using the generic approach.

        The parsing happens in stages:
        1. Detect column structure from headers
        2. Learn patterns from the statement
        3. Parse transactions using learned patterns
        4. Normalize and validate results
        """
        transactions = []
        errors = []
        warnings = []

        # Stage 1: Detect column structure
        structure = self._detect_column_structure(text)
        self.columns_detected = structure['columns']

        # Stage 2: Learn patterns
        self.patterns = self._learn_patterns(text)

        # Stage 3: Parse transactions
        transactions = self._parse_transactions(text)

        # Stage 4: Normalize and validate
        transactions = self._normalize_transactions(transactions)
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
            statement_type=self._guess_statement_type(text),
            raw_text=text,
            metadata={
                'parser': self.parser_name,
                'transaction_count': len(valid_transactions),
                'columns_detected': self.columns_detected,
                'patterns_learned': self.patterns,
            },
            errors=errors,
            warnings=warnings,
        )

    def _detect_column_structure(self, text: str) -> Dict[str, Any]:
        """Detect the column structure from the statement headers."""
        lines = text.splitlines()
        result = {
            'columns': {},
            'delimiter': None,
            'header_line': -1,
        }

        # Find header line
        header_keywords = {
            'date': ['date', 'posting', 'transaction', 'dt'],
            'description': ['description', 'narration', 'merchant', 'payee',
                           'transaction details', 'particulars'],
            'amount': ['amount', 'value'],
            'debit': ['debit', 'withdrawal', 'dr'],
            'credit': ['credit', 'deposit', 'cr'],
            'balance': ['balance', 'closing'],
            'reference': ['reference', 'ref', 'chq', 'txn'],
        }

        for i, line in enumerate(lines):
            if len(line) < 20:
                continue

            # Detect delimiter
            if not result['delimiter']:
                result['delimiter'] = self._detect_delimiter(line)

            # Check if this is a header line
            line_lower = line.lower()
            found_keywords = []

            for field_name, variations in header_keywords.items():
                for var in variations:
                    if var in line_lower:
                        found_keywords.append(field_name)
                        break

            # If we found enough keywords, this is likely a header
            if len(found_keywords) >= 3:
                result['header_line'] = i
                result['columns'] = self._map_columns(line, header_keywords, result['delimiter'])
                break

        return result

    def _map_columns(self, header_line: str, field_keywords: Dict[str, List[str]], delimiter: str) -> Dict[str, int]:
        """Map column indices to field names."""
        if delimiter == ' ':
            # For space-separated, use position-based detection
            return self._map_columns_by_position(header_line)

        parts = header_line.split(delimiter)
        mapping = {}

        for i, part in enumerate(parts):
            part_lower = part.lower().strip()

            for field_name, variations in field_keywords.items():
                for var in variations:
                    if var in part_lower:
                        if field_name not in mapping:  # Keep first match
                            mapping[field_name] = i
                        break

        return mapping

    def _map_columns_by_position(self, header_line: str) -> Dict[str, int]:
        """
        Map columns by position when delimiter is space.
        This uses a heuristic approach based on common column ordering.
        """
        # Common order: Date, Narration/Description, Reference, Value Date,
        #               Debit, Credit, Balance
        words = header_line.split()

        mapping = {}

        # Look for keywords at various positions
        for i, word in enumerate(words):
            word_lower = word.lower().strip('.,:-_')

            if word_lower in ['date', 'dt', 'posting', 'transaction']:
                mapping['date'] = i
            elif word_lower in ['description', 'narration', 'particulars', 'merchant']:
                mapping['description'] = i
            elif word_lower in ['withdrawal', 'debit', 'dr', 'amount', 'val']:
                mapping['debit'] = i
            elif word_lower in ['deposit', 'credit', 'cr']:
                mapping['credit'] = i
            elif word_lower in ['balance', 'closing']:
                mapping['balance'] = i
            elif word_lower in ['reference', 'ref', 'chq', 'txn']:
                mapping['reference'] = i

        return mapping

    def _learn_patterns(self, text: str) -> Dict[str, Any]:
        """Learn patterns from the statement for future use."""
        patterns = {}

        # Learn date pattern
        date_matches = DATE_PATTERN_DDMMYYYY.findall(text)
        if date_matches:
            patterns['date_pattern'] = 'DD/MM/YYYY'
            patterns['date_sample'] = date_matches[:3]

        # Learn amount pattern
        amount_matches = AMOUNT_PATTERN.findall(text)
        if amount_matches:
            patterns['amount_pattern'] = 'number with optional Cr/Dr suffix'
            patterns['amount_sample'] = [a[0] for a in amount_matches[:3]]

        # Learn skip patterns
        skip_lines = []
        for line in text.splitlines():
            if is_skip_line(line):
                skip_lines.append(line.strip()[:50])

        if skip_lines:
            patterns['skip_lines'] = list(set(skip_lines))[:10]

        # Learn transaction pattern (line structure)
        lines = text.splitlines()
        transaction_lines = []

        for line in lines:
            if not is_skip_line(line) and len(line) > 20:
                # Check if this line has date + amount (typical transaction)
                if DATE_PATTERN_DDMMYYYY.search(line) and AMOUNT_PATTERN.search(line):
                    transaction_lines.append(line)

        if transaction_lines:
            patterns['transaction_sample'] = transaction_lines[:5]

        return patterns

    def _parse_transactions(self, text: str) -> List[Dict[str, Any]]:
        """Parse transactions from the statement text."""
        transactions = []
        lines = text.splitlines()

        # First pass: Use generic line parser
        for line in lines:
            line = line.strip()

            if is_skip_line(line):
                continue

            # Try generic parsing
            match = parse_generic_line(line)
            if match and match.amount > 0:
                tx = self._create_transaction(
                    match.date,
                    match.description,
                    match.amount,
                    match.is_credit,
                    line
                )
                transactions.append(tx)

        # Second pass: Look for multi-line patterns
        if len(transactions) < 3:
            transactions.extend(self._parse_multi_line_transactions(text))

        # Third pass: Use regex-based extraction as fallback
        if len(transactions) < 5:
            transactions.extend(self._parse_regex_fallback(text))

        return transactions

    def _create_transaction(self, date: str, description: str, amount: float,
                           is_credit: bool, raw: str) -> Dict[str, Any]:
        """Create a normalized transaction dict."""
        return {
            'date': date,
            'description': description,
            'amount': amount,
            'type': 'credit' if is_credit else 'debit',
            'debit': 0,
            'credit': amount if is_credit else 0,
            'balance': 0,
            'reference': '',
            'card_no': '',
            'value_date': date,
            'merchant': description,
            'narration': description,
            'raw_line': raw,
        }

    def _parse_multi_line_transactions(self, text: str) -> List[Dict[str, Any]]:
        """Parse transactions that span multiple lines."""
        transactions = []
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        i = 0
        while i < len(lines) - 2:
            line1 = lines[i]      # Likely merchant/description
            line2 = lines[i + 1]  # Likely day + amount
            line3 = lines[i + 2]  # Likely month + year + Dr/Cr

            # Check for UPI-style 3-line pattern
            # Pattern: Day + Amount (optionally followed by Cr/Dr)
            # Example: "12 ₹798.48" or "12 ₹798.48 Dr"
            day_match = re.match(r'^(\d{1,2})\s*₹?\s*([0-9,]+\.\d{2})\s*(?:Dr|Cr)?$', line2, re.IGNORECASE)

            if day_match:
                # This looks like a multi-line transaction
                day = day_match.group(1)
                amount_str = day_match.group(2)

                drcr_match = re.search(r'(Dr|Cr|DR|CR)', line3, re.IGNORECASE)
                drcr = drcr_match.group(1).lower() if drcr_match else 'dr'

                # Extract date from line3
                # Line format: Mon DD Dr/Cr [optional reference] [optional suffix]
                # Try to extract date components from the beginning of line3
                date_match = re.match(r'^([A-Za-z]{3})\s+(\d{1,2})\s+(?:Dr|Cr)', line3, re.IGNORECASE)
                if date_match:
                    month = date_match.group(1)
                    day = date_match.group(2).zfill(2)
                    # Default year
                    year = '2025'

                    full_date = f"{day} {month} {year}"
                    parsed_date = parse_date(full_date)

                    if parsed_date:
                        tx = {
                            'date': parsed_date,
                            'description': line1,
                            'amount': parse_amount(amount_str),
                            'type': 'credit' if drcr == 'cr' else 'debit',
                            'debit': 0,
                            'credit': parse_amount(amount_str) if drcr == 'cr' else 0,
                            'balance': 0,
                            'reference': '',
                            'card_no': '',
                            'value_date': parsed_date,
                            'merchant': line1,
                            'narration': line1,
                        }
                        transactions.append(tx)
                        i += 3
                        continue

            i += 1

        return transactions

    def _parse_regex_fallback(self, text: str) -> List[Dict[str, Any]]:
        """Fallback regex-based transaction extraction."""
        transactions = []

        # Pattern for lines with date followed by amount
        complex_pattern = re.compile(
            r'(\d{1,2}[/\s]\d{1,2}[/\s]\d{2,4})'  # Date
            r'.*?'                                   # Anything in between
            r'([0-9,]+\.\d{2})'                      # Amount
            r'\s*(Cr|CR|Dr|DR)?',                    # Credit/Debit marker
            re.IGNORECASE
        )

        for match in complex_pattern.finditer(text):
            date_str = parse_date(match.group(1))
            if not date_str:
                continue

            amount = parse_amount(match.group(2))
            if amount <= 0:
                continue

            is_credit = match.group(3) is not None and match.group(3).upper() == 'CR'

            # Extract description (context around the match)
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            context = text[start:end]

            # Try to find description near the date
            desc_match = re.search(r'(\d{1,2}[/\s]\d{1,2}[/\s]\d{2,4})\s*(.+?)\s*[0-9,]', context)
            if desc_match:
                description = desc_match.group(2).strip()
            else:
                description = 'Transaction'

            tx = {
                'date': date_str,
                'description': description,
                'amount': amount,
                'type': 'credit' if is_credit else 'debit',
                'debit': 0,
                'credit': amount if is_credit else 0,
                'balance': 0,
                'reference': '',
                'card_no': '',
                'value_date': date_str,
                'merchant': description,
                'narration': description,
            }
            transactions.append(tx)

        return transactions

    def _normalize_transactions(self, transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize all transactions to standard format."""
        normalized = []
        for tx in transactions:
            normalized.append(self._normalize_transaction(tx))
        return normalized

    def _guess_statement_type(self, text: str) -> str:
        """Guess the statement type based on content."""
        text_lower = text.lower()

        # UPI indicators
        if any(kw in text_lower for kw in ['upi', 'phonepe', 'google pay', 'ixigo', 'au bank']):
            return 'upi'

        # Credit card indicators
        if any(kw in text_lower for kw in ['credit card', 'total amount due', 'minimum amount due']):
            return 'credit_card'

        # Default to bank statement
        return 'bank'

    def _detect_delimiter(self, line: str) -> str:
        """Detect the delimiter used in a line."""
        delimiters = ['\t', '|', '~', ',']

        for delim in delimiters:
            if delim in line:
                return delim

        return ' '

    def _validate_transaction(self, tx: Dict[str, Any]) -> bool:
        """Validate a transaction with enhanced checks."""
        # Must have date
        if not tx.get('date'):
            return False

        # Amount must be numeric
        try:
            amount = float(tx.get('amount', 0))
            if amount <= 0:
                return False
        except (ValueError, TypeError):
            return False

        # Description must exist and be reasonable length
        desc = tx.get('description', '')
        if not desc or len(str(desc)) < 2:
            return False

        # Description shouldn't be just numbers
        if re.match(r'^[\d\s.,]+$', desc):
            return False

        return True
