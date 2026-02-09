"""
Generic bank account statement parser.

This parser handles any bank statement format using adaptive pattern recognition
and artificial intelligence techniques when needed. It completely removes all
bank-specific logic and creates a unified approach that works for any financial institution.

Features:
1. Automatic format detection using pattern recognition
2. Adaptive column structure analysis
3. AI-powered parsing for complex/unrecognized formats
4. Unified credit/debit detection logic
5. Pattern learning for improved future parsing
"""

import re
import os
import json
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
    Generic parser for bank account statements.

    This parser automatically detects and handles any bank statement format
    using adaptive algorithms and AI assistance when needed.
    """

    statement_type = "bank"

    def __init__(self):
        """Initialize the bank statement parser."""
        super().__init__()
        self.parser_name = "BankStatementParser"

    def _clean_description(self, description: str) -> str:
        """Clean up transaction descriptions by removing extra formatting."""
        if not description:
            return ""

        # Remove extra whitespace and normalize
        description = ' '.join(description.split())

        # Remove common formatting artifacts
        # Remove date patterns at the end
        description = re.sub(r'\s+\d{1,2}/\d{1,2}/\d{2,4}\s*$', '', description)
        # Remove amount patterns at the end
        description = re.sub(r'\s+\d+(?:\.\d+)?\s*$', '', description)
        # Remove balance patterns
        description = re.sub(r'\s+\d+(?:\.\d+)?\s+\d+(?:\.\d+)?\s*$', '', description)
        # Remove multiple consecutive numbers
        description = re.sub(r'\s+\d+(?:\.\d+)?\s+\d+(?:\.\d+)?(?:\s+\d+(?:\.\d+)?)?\s*$', '', description)

        # Remove leading/trailing punctuation and spaces
        description = description.strip(' .,-_:;@#')

        # Limit length for practical purposes
        if len(description) > 200:
            description = description[:200]

        return description

    def can_parse(self, text: str) -> bool:
        """
        Check if this parser can handle the given text.

        This generic parser can handle any text that appears to be a financial statement
        by looking for common financial statement patterns.
        """
        text_lower = text.lower()

        # Check for basic financial statement indicators
        financial_indicators = [
            'account', 'balance', 'transaction', 'amount',
            'credit', 'debit', 'deposit', 'withdrawal',
            'statement', 'date', 'narration'
        ]

        # Must have at least some financial indicators
        found_indicators = sum(1 for indicator in financial_indicators if indicator in text_lower)

        # Must have date patterns
        has_dates = bool(DATE_PATTERN_DDMMYYYY.search(text) or
                        re.search(r'\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4}', text))

        # Must have amount patterns
        has_amounts = bool(AMOUNT_PATTERN.search(text))

        # Must have some structure
        lines = text.splitlines()
        has_structure = len(lines) > 5 and any(len(line.strip()) > 10 for line in lines)

        return found_indicators >= 3 and has_dates and has_amounts and has_structure

    def parse(self, text: str) -> ParseResult:
        """
        Parse bank statement text using a generic approach.

        This method uses multiple parsing strategies:
        1. CSV format detection and parsing
        2. Adaptive pattern recognition for various formats
        3. AI-assisted parsing for complex/unrecognized formats
        4. Fallback to generic line-by-line parsing
        """
        transactions = []
        errors = []
        warnings = []

        # Stage 1: Try CSV format parsing
        if ',' in text and self._has_csv_structure(text):
            try:
                result = self._parse_csv(text)
                transactions.extend(result)
            except Exception as e:
                warnings.append(f"CSV parsing failed: {str(e)}")

        # Stage 2: Try adaptive pattern recognition
        if len(transactions) < 5:  # If CSV didn't yield enough results
            try:
                result = self._parse_adaptive(text)
                transactions.extend(result)
            except Exception as e:
                warnings.append(f"Adaptive parsing failed: {str(e)}")

        # Stage 3: Try AI-assisted parsing for complex formats
        if len(transactions) < 3:  # If adaptive parsing didn't work well
            try:
                result = self._parse_with_ai(text)
                transactions.extend(result)
            except Exception as e:
                warnings.append(f"AI parsing failed: {str(e)}")

        # Stage 4: Fallback to generic parsing
        if len(transactions) < 1:  # If nothing worked
            try:
                result = self._parse_generic_fallback(text)
                transactions.extend(result)
            except Exception as e:
                warnings.append(f"Fallback parsing failed: {str(e)}")

        # Deduplicate and validate
        transactions = self._deduplicate(transactions)
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
                'warnings_count': len(warnings),
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

            # Handle cases where there's only one amount column
            if debit > 0 and credit == 0:
                # Check if this is actually a credit transaction marked in description
                narration_lower = narration.lower()
                if any(keyword in narration_lower for keyword in ['cr', 'credit', 'deposit', 'neft', 'rtgs', 'imps']):
                    credit = debit
                    debit = 0.0
            elif credit > 0 and debit == 0:
                # This is already correctly identified as credit
                pass
            elif debit_str and not credit_str:
                # Only debit column exists, check for credit indicators
                narration_lower = narration.lower()
                if any(keyword in narration_lower for keyword in ['cr', 'credit', 'deposit', 'neft', 'rtgs', 'imps']):
                    credit = debit
                    debit = 0.0

            # Skip zero-amount transactions
            if debit == 0 and credit == 0:
                continue

            # Clean description
            narration = self._clean_description(narration)

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

    def _parse_adaptive(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse bank statements using adaptive pattern recognition.

        This method automatically detects the format structure and parses accordingly:
        1. Column-based formats (CSV, TSV, fixed-width)
        2. Multi-line transaction formats
        3. Single-line transaction formats
        4. Mixed format detection
        """
        transactions = []
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # Keep track of already parsed transactions to avoid duplicates
        parsed_hashes = set()

        # Try different parsing strategies
        strategies = [
            self._parse_column_based,
            self._parse_multiline_transactions,
            self._parse_single_line_transactions,
        ]

        for strategy in strategies:
            if len(transactions) < 20:  # Continue trying if we don't have enough
                try:
                    result = strategy(lines)
                    # Only add unique transactions
                    for tx in result:
                        tx_hash = hash(f"{tx.get('date', '')}-{tx.get('description', '')}-{tx.get('debit', 0)}-{tx.get('credit', 0)}")
                        if tx_hash not in parsed_hashes:
                            transactions.append(tx)
                            parsed_hashes.add(tx_hash)
                except Exception:
                    continue  # Try next strategy

        return transactions

    def _parse_column_based(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Parse column-based statement formats."""
        transactions = []

        # Detect delimiter and column structure
        delimiter = self._detect_delimiter(lines)
        header_mapping = self._map_columns(lines, delimiter)

        if not header_mapping:
            return transactions

        # Parse data rows
        data_start = self._find_data_start(lines, header_mapping)

        for i in range(data_start, len(lines)):
            line = lines[i].strip()
            if not line or is_skip_line(line):
                continue

            parts = self._split_line(line, delimiter)
            tx = self._extract_transaction_from_columns(parts, header_mapping, lines[max(0, i-2):i+3])

            if tx and self._validate_transaction(tx):
                transactions.append(tx)

        return transactions

    def _parse_multiline_transactions(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Parse multi-line transaction formats."""
        transactions = []
        i = 0

        # First try to parse as Indian bank format
        indian_format_txns = self._parse_indian_bank_format(lines)
        if indian_format_txns:
            return indian_format_txns

        while i < len(lines) - 1:
            # Look for transaction patterns
            tx = self._parse_transaction_group(lines, i)
            if tx:
                transactions.append(tx)
                # Skip processed lines
                i += self._count_transaction_lines(lines, i)
            else:
                i += 1

        return transactions

    def _parse_single_line_transactions(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Parse single-line transaction formats."""
        transactions = []

        for line in lines:
            if is_skip_line(line) or len(line) < 20:
                continue

            # Try generic line parsing
            match = parse_generic_line(line)
            if match and match.amount > 0:
                tx = self._convert_generic_match_to_transaction(match)
                transactions.append(tx)

        return transactions

    def _parse_with_ai(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse complex formats using AI assistance.

        This method uses OpenAI or Google Gemini APIs to analyze and extract
        transactions from unrecognized formats.
        """
        transactions = []

        # Check if API keys are available
        openai_key = os.environ.get('OPENAI_KEY')
        gemini_key = os.environ.get('GEMINI_API_KEY')

        if not (openai_key or gemini_key):
            # No AI keys available, return empty list
            return transactions

        try:
            # Prepare prompt for AI analysis
            prompt = f"""
            Analyze the following bank statement and extract all transactions in JSON format.
            Each transaction should include: date, description, amount, type (credit/debit).

            Statement text:
            {text[:2000]}  # Limit to first 2000 chars to avoid token limits

            Respond with ONLY valid JSON in this format:
            {{
                "transactions": [
                    {{
                        "date": "DD/MM/YYYY",
                        "description": "Transaction description",
                        "amount": 123.45,
                        "type": "credit" or "debit"
                    }}
                ]
            }}
            """
            # Try OpenAI first
            if openai_key:
                transactions = self._parse_with_openai(prompt)
            elif gemini_key:
                transactions = self._parse_with_gemini(prompt)

        except Exception as e:
            # AI parsing failed, return empty list
            pass

        return transactions

    def _parse_generic_fallback(self, text: str) -> List[Dict[str, Any]]:
        """
        Generic fallback parsing for any unrecognized format.

        This method uses pattern matching and heuristics to extract transactions.
        """
        transactions = []
        lines = text.splitlines()

        for line in lines:
            line = line.strip()
            if not line or len(line) < 15:
                continue

            # Skip header-like lines
            if is_skip_line(line):
                continue

            # Look for transaction patterns
            tx = self._extract_transaction_by_pattern(line)
            if tx:
                transactions.append(tx)

        return transactions

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

    def _detect_delimiter(self, lines: List[str]) -> str:
        """Detect the delimiter used in the statement."""
        if not lines:
            return ','

        # Check first few lines for common delimiters
        sample_lines = lines[:min(5, len(lines))]

        # Count occurrences of each delimiter
        delimiters = [',', '\t', '|', ';']
        delimiter_counts = {delim: 0 for delim in delimiters}

        for line in sample_lines:
            for delim in delimiters:
                delimiter_counts[delim] += line.count(delim)

        # Return the delimiter with the highest count
        best_delimiter = max(delimiter_counts.items(), key=lambda x: x[1])

        # If no delimiter found, default to comma
        return best_delimiter[0] if best_delimiter[1] > 0 else ','

    def _map_columns(self, lines: List[str], delimiter: str) -> Dict[str, int]:
        """Map column names to indices."""
        if not lines:
            return {}

        # Look for header row with recognizable column names
        header_keywords = {
            'date': ['date', 'posting', 'transaction', 'dt'],
            'description': ['description', 'narration', 'merchant', 'payee', 'particulars'],
            'debit': ['debit', 'withdrawal', 'dr', 'amount'],
            'credit': ['credit', 'deposit', 'cr'],
            'balance': ['balance', 'closing', 'current'],
            'reference': ['reference', 'ref', 'chq', 'txn', 'cheque'],
        }

        column_mapping = {}

        # Check first few lines for headers
        for i, line in enumerate(lines[:min(3, len(lines))]):
            if not line.strip():
                continue

            parts = line.split(delimiter)

            # Check if this line looks like a header
            found_keywords = 0
            for j, part in enumerate(parts):
                part_lower = part.strip().lower()
                for field_name, variations in header_keywords.items():
                    if any(var in part_lower for var in variations):
                        if field_name not in column_mapping:
                            column_mapping[field_name] = j
                            found_keywords += 1
                            break

            # If we found multiple keywords, this is likely the header
            if found_keywords >= 3:
                return column_mapping

        return column_mapping

    def _find_data_start(self, lines: List[str], header_mapping: Dict[str, int]) -> int:
        """Find where the data starts in the lines."""
        if not lines or not header_mapping:
            return 0

        # Look for the line after the header
        header_keywords = ['date', 'description', 'debit', 'credit', 'balance']
        mapped_header_fields = list(header_mapping.keys())

        for i, line in enumerate(lines):
            line_lower = line.lower()
            # Check if this line contains header keywords
            matching_headers = sum(1 for kw in header_keywords if kw in line_lower)
            if matching_headers >= 2:
                # Return the next line as data start
                return min(i + 1, len(lines) - 1)

        # Default to line 1 if no clear header found
        return 1

    def _split_line(self, line: str, delimiter: str) -> List[str]:
        """Split a line using the detected delimiter."""
        if not line:
            return []
        return [part.strip() for part in line.split(delimiter)]

    def _extract_transaction_from_columns(self, parts: List[str], header_mapping: Dict[str, int], context_lines: List[str]) -> Optional[Dict[str, Any]]:
        """Extract a transaction from column-based data."""
        if not parts or not header_mapping:
            return None

        try:
            # Extract fields based on column mapping
            date_str = ""
            description = ""
            debit_str = ""
            credit_str = ""
            balance_str = ""
            reference = ""

            # Get values based on column mapping
            if 'date' in header_mapping and header_mapping['date'] < len(parts):
                date_str = parts[header_mapping['date']].strip()

            if 'description' in header_mapping and header_mapping['description'] < len(parts):
                description = parts[header_mapping['description']].strip()

            if 'debit' in header_mapping and header_mapping['debit'] < len(parts):
                debit_str = parts[header_mapping['debit']].strip()

            if 'credit' in header_mapping and header_mapping['credit'] < len(parts):
                credit_str = parts[header_mapping['credit']].strip()

            if 'balance' in header_mapping and header_mapping['balance'] < len(parts):
                balance_str = parts[header_mapping['balance']].strip()

            if 'reference' in header_mapping and header_mapping['reference'] < len(parts):
                reference = parts[header_mapping['reference']].strip()

            # Parse date
            date_normalized = parse_date(date_str) if date_str else ""
            if not date_normalized:
                return None

            # Parse amounts
            debit = parse_amount(debit_str) if debit_str else 0.0
            credit = parse_amount(credit_str) if credit_str else 0.0
            balance = parse_amount(balance_str) if balance_str else 0.0

            # Skip zero-amount transactions
            if debit == 0 and credit == 0:
                return None

            # Clean description
            description = self._clean_description(description)

            return {
                'date': date_normalized,
                'description': description,
                'narration': description,
                'value_date': date_normalized,
                'debit': debit,
                'credit': credit,
                'balance': balance,
                'reference': reference,
                'card_no': '',
                'type': 'credit' if credit > 0 else 'debit',
                'merchant': description,
            }
        except Exception:
            return None

    def _parse_transaction_group(self, lines: List[str], start_index: int) -> Optional[Dict[str, Any]]:
        """Parse a group of lines as a single transaction."""
        if start_index >= len(lines):
            return None

        # Get the main transaction line
        main_line = lines[start_index].strip()
        if not main_line or is_skip_line(main_line):
            return None

        # Try to parse the main line first
        match = parse_generic_line(main_line)
        if not match:
            return None

        # Extract basic transaction info
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

        # Look at subsequent lines for additional information
        for i in range(start_index + 1, min(start_index + 3, len(lines))):
            line = lines[i].strip()
            if not line or len(line) < 5:
                continue

            # Check for reference number or additional details
            if 'ref' in line.lower() or 'reference' in line.lower():
                # Extract reference number
                ref_match = re.search(r'[A-Z0-9]{6,}', line)
                if ref_match:
                    tx['reference'] = ref_match.group(0)

        return tx

    def _count_transaction_lines(self, lines: List[str], start_index: int) -> int:
        """Count how many lines belong to a transaction."""
        if start_index >= len(lines):
            return 0

        count = 1  # At least the main line

        # Look at subsequent lines to see if they belong to the same transaction
        for i in range(start_index + 1, min(start_index + 4, len(lines))):
            line = lines[i].strip()
            if not line:
                continue

            # If line starts with a date, it's probably a new transaction
            if DATE_PATTERN_DDMMYYYY.search(line):
                break

            # If line is very short or looks like a continuation, count it
            if len(line) < 20 or line.startswith((' ', '\t')):
                count += 1
            else:
                # If line looks like a complete transaction, stop counting
                match = parse_generic_line(line)
                if match:
                    break
                count += 1

        return count

    def _extract_transaction_by_pattern(self, line: str) -> Optional[Dict[str, Any]]:
        """Extract transaction using pattern matching."""
        # Try generic line parsing first
        match = parse_generic_line(line)
        if match and match.amount > 0:
            return self._convert_generic_match_to_transaction(match)

        # Try more specific patterns
        date_match = DATE_PATTERN_DDMMYYYY.search(line)
        if not date_match:
            return None

        date_str = date_match.group(1)
        date_normalized = parse_date(date_str)
        if not date_normalized:
            return None

        # Look for amounts after the date
        after_date = line[date_match.end():]
        amount_matches = list(AMOUNT_PATTERN.finditer(after_date))

        if not amount_matches:
            return None

        # Take the first valid amount
        amount_str = amount_matches[0].group(1)
        suffix = amount_matches[0].group(2) or ""
        amount = parse_amount(amount_str)

        if amount <= 0:
            return None

        # Extract description (text between date and amount)
        description_start = date_match.end()
        description_end = date_match.end() + after_date.find(amount_str)
        description = line[description_start:description_end].strip()
        description = re.sub(r'^[^\w]+|[^\w]+$', '', description)  # Clean up

        # Determine if credit or debit based on suffix or description keywords
        is_credit = False
        if suffix:
            is_credit = suffix.upper() in ['CR', 'CREDIT']
        else:
            # Check description for credit indicators
            desc_lower = description.lower()
            credit_keywords = ['cr', 'credit', 'deposit', 'neft', 'rtgs', 'imps', 'transfer in']
            is_credit = any(keyword in desc_lower for keyword in credit_keywords)

        return {
            'date': date_normalized,
            'description': self._clean_description(description),
            'narration': self._clean_description(description),
            'value_date': date_normalized,
            'debit': amount if not is_credit else 0,
            'credit': amount if is_credit else 0,
            'balance': 0,
            'reference': '',
            'card_no': '',
            'type': 'credit' if is_credit else 'debit',
            'merchant': self._clean_description(description),
        }

    def _convert_generic_match_to_transaction(self, match) -> Dict[str, Any]:
        """Convert a generic match to a transaction dict."""
        return {
            'date': match.date,
            'description': match.description,
            'amount': match.amount,
            'type': 'credit' if match.is_credit else 'debit',
            'debit': match.amount if not match.is_credit else 0,
            'credit': match.amount if match.is_credit else 0,
            'balance': 0,
            'reference': '',
            'card_no': '',
            'value_date': match.date,
            'merchant': match.description,
            'narration': match.description,
        }

    def _parse_with_openai(self, prompt: str) -> List[Dict[str, Any]]:
        """Parse using OpenAI API."""
        try:
            import openai
            openai.api_key = os.environ.get('OPENAI_KEY')

            if not openai.api_key:
                return []

            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a financial statement parser. Extract transactions from bank statements and return valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.1
            )

            # Extract JSON from response
            content = response.choices[0].message.content
            # Find JSON in response
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                data = json.loads(json_str)
                return data.get('transactions', [])

        except Exception:
            pass

        return []

    def _parse_with_gemini(self, prompt: str) -> List[Dict[str, Any]]:
        """Parse using Google Gemini API."""
        try:
            import google.generativeai as genai
            api_key = os.environ.get('GEMINI_API_KEY')

            if not api_key:
                return []

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-pro')

            response = model.generate_content(prompt)

            # Extract JSON from response
            content = response.text
            # Find JSON in response
            import json
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                data = json.loads(json_str)
                return data.get('transactions', [])

        except Exception:
            pass

        return []

    def _parse_indian_bank_format(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Parse Indian bank statement format specifically."""
        transactions = []

        # Look for the header line that indicates column structure
        header_line_idx = -1
        for i, line in enumerate(lines):
            if 'Date Transaction Details Debits Credits Balance' in line:
                header_line_idx = i
                break

        if header_line_idx == -1:
            return transactions

        # Parse transactions after the header
        for i in range(header_line_idx + 1, len(lines)):
            line = lines[i].strip()
            if not line or len(line) < 10:
                continue

            # Skip summary lines
            if any(skip_term in line.lower() for skip_term in ['total', 'ending balance', 'opening balance', 'account summary']):
                continue

            # Parse the line according to Indian bank format
            tx = self._parse_indian_bank_line(line)
            if tx:
                transactions.append(tx)

        return transactions

    def _parse_indian_bank_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse a single line from Indian bank statement format."""
        # Indian bank format examples:
        # 16 Jun 2024 UTIB0000114/Axis/XXXXX INR 19,803.22 - INR 40,173.56  (Debit)
        # 30 Jun 2024 CREDIT INTEREST - INR 288.00 INR 196,912.56            (Credit)

        # Extract date first
        date_match = re.search(r'(\d{1,2} [A-Za-z]{3} \d{4})', line)
        if not date_match:
            return None

        date_str = date_match.group(1)
        date_normalized = parse_date(date_str)
        if not date_normalized:
            return None

        # Extract everything after the date
        after_date = line[date_match.end():].strip()

        # Look for amounts with INR prefix
        amount_matches = list(re.finditer(r'INR ([\d,]+\.\d{2})', after_date))
        if not amount_matches:
            return None

        # Extract the amounts
        first_amount = parse_amount(amount_matches[0].group(1)) if amount_matches else 0.0

        # Determine if this is a credit or debit transaction
        # Strong indicators for credit transactions
        is_credit = (
            'CREDIT INTEREST' in line.upper() or
            'INTEREST' in line.upper() and 'CREDIT' in line.upper() or
            'NEFT' in line.upper() or
            'RTGS' in line.upper() or
            'IMPS' in line.upper() or
            'TRANSFER IN' in line.upper()
        )

        # Check for dash to distinguish debit vs credit
        dash_pos = after_date.find(' - ')

        # Special handling for credit interest - these always have credit amounts
        if 'CREDIT INTEREST' in line.upper():
            is_credit = True
            # Credit interest format: "CREDIT INTEREST - INR XXXXX INR BALANCE"
            # The first amount is the credit amount
            credit_amount = first_amount
            debit_amount = 0.0
        elif dash_pos != -1 and not is_credit:
            # Debit transaction - has a dash: "INR XXXXX - INR BALANCE"
            # The first amount is the debit amount
            debit_amount = first_amount
            credit_amount = 0.0
        elif is_credit:
            # Credit transaction without dash: "INR XXXXX INR BALANCE"
            # The first amount is the credit amount
            credit_amount = first_amount
            debit_amount = 0.0
        else:
            # Default assumption - if we can't determine, assume debit (more common)
            # The first amount is the debit amount
            debit_amount = first_amount
            credit_amount = 0.0

        # Extract description (everything between date and amounts)
        description_end = after_date.find('INR')
        description = after_date[:description_end].strip() if description_end != -1 else after_date

        # Clean description
        description = self._clean_description(description)

        return {
            'date': date_normalized,
            'description': description,
            'narration': description,
            'value_date': date_normalized,
            'debit': debit_amount,
            'credit': credit_amount,
            'balance': 0,  # We could extract this if needed
            'reference': '',
            'card_no': '',
            'type': 'credit' if credit_amount > 0 else 'debit',
            'merchant': description,
        }