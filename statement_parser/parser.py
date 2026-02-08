"""
Main StatementParser class - the primary entry point for parsing financial statements.

This class orchestrates the parsing pipeline:
1. Detects statement type from file content
2. Selects appropriate parser
3. Extracts and normalizes transactions
4. Returns results in various formats
"""

import io
import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from pathlib import Path

from statement_parser.detector import detect_statement_type, StatementType
from statement_parser.formats.generic_parser import GenericStatementParser
from statement_parser.formats.bank_statement import BankStatementParser
from statement_parser.formats.credit_card import CreditCardParser
from statement_parser.formats.upi_statement import UPIStatementParser
from statement_parser.output import OutputGenerator
from statement_parser.utils.formatting import parse_date


@dataclass
class ParseOptions:
    """Options for parsing a statement."""
    output_format: str = "excel"      # excel, csv, json
    output_dir: str = "."             # Output directory
    include_summary: bool = True      # Include summary sheet in Excel
    normalize: bool = True            # Normalize transaction descriptions
    deduplicate: bool = True          # Remove duplicate transactions


class StatementParser:
    """
    Main parser class for financial statements.

    Usage:
        from statement_parser import StatementParser

        parser = StatementParser()
        result = parser.parse_file("statement.pdf")

        # Export to Excel
        result.to_excel("output.xlsx")

        # Or access transactions directly
        for tx in result.transactions:
            print(tx['date'], tx['description'], tx['amount'])
    """

    def __init__(self, options: Optional[ParseOptions] = None):
        """
        Initialize the parser.

        Args:
            options: ParseOptions for customizing parsing behavior
        """
        self.options = options or ParseOptions()
        self.parsers = [
            ('generic', GenericStatementParser()),
            ('bank', BankStatementParser()),
            ('credit_card', CreditCardParser()),
            ('upi', UPIStatementParser()),
        ]
        self.last_parser_used: Optional[str] = None
        self.last_statement_type: Optional[str] = None

    def parse_file(self, filepath: str, options: Optional[ParseOptions] = None) -> 'ParseResult':
        """
        Parse a statement file (PDF, text, CSV).

        Args:
            filepath: Path to the statement file
            options: Override options for this parse

        Returns:
            ParseResult with parsed transactions
        """
        filepath = Path(filepath)
        ext = filepath.suffix.lower()

        # Read file content
        if ext == '.pdf':
            text = self._extract_text_from_pdf(filepath, password=getattr(self, '_pdf_password', None))
        else:
            text = self._read_text_file(filepath)

        return self.parse_text(text, options)

    def parse_text(self, text: str, options: Optional[ParseOptions] = None) -> 'ParseResult':
        """
        Parse statement from text content.

        Args:
            text: Statement text content
            options: Override options for this parse

        Returns:
            ParseResult with parsed transactions
        """
        options = options or self.options

        # Detect statement type
        statement_type = detect_statement_type(text)

        # Select appropriate parser
        parser = self._select_parser(statement_type)
        self.last_parser_used = parser.__class__.__name__
        self.last_statement_type = statement_type.value

        # Parse
        result = parser.parse(text)

        # Apply normalization if requested
        if options.normalize:
            result.transactions = self._normalize_all(result.transactions)

        # Deduplicate if requested
        if options.deduplicate:
            result.transactions = self._deduplicate_all(result.transactions)

        return ParseResult(
            transactions=result.transactions,
            statement_type=statement_type.value,
            raw_text=result.raw_text,
            metadata=result.metadata,
            errors=result.errors,
            warnings=result.warnings,
        )

    def _select_parser(self, statement_type: StatementType) -> 'BaseParser':
        """Select the appropriate parser for the statement type."""
        for name, parser in self.parsers:
            if parser.statement_type == statement_type.value:
                return parser
        # Default to generic parser
        return self.parsers[0][1]

    def _extract_text_from_pdf(self, filepath: Path, password: Optional[str] = None) -> str:
        """Extract text from a PDF file.

        Args:
            filepath: Path to the PDF file
            password: Optional password for encrypted PDFs

        Returns:
            Extracted text from the PDF
        """
        try:
            import pdfplumber
            import PyPDF2

            # Check if PDF is encrypted and try to decrypt
            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                if reader.is_encrypted:
                    # Try empty password first
                    if password is None:
                        password = ""
                    # Try to decrypt
                    try:
                        result = reader.decrypt(password)
                        if result == 0:
                            # Decryption failed
                            raise ValueError("Invalid password for encrypted PDF")
                    except Exception:
                        raise ValueError("Could not decrypt PDF - check password")

            # Now open with pdfplumber (it will use the decrypted version)
            with pdfplumber.open(filepath, password=password) as pdf:
                text_parts = []
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    text_parts.append(text)
                return "\n".join(text_parts)
        except ImportError:
            raise ImportError(
                "pdfplumber and PyPDF2 are required for PDF parsing. "
                "Install with: pip install pdfplumber PyPDF2"
            )

    def _read_text_file(self, filepath: Path) -> str:
        """Read text from a text or CSV file."""
        # Try UTF-8 first, then latin-1
        encodings = ['utf-8', 'latin-1', 'cp1252']

        for encoding in encodings:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue

        raise ValueError(f"Could not decode file {filepath} with any known encoding")

    def _normalize_all(self, transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize all transactions."""
        from statement_parser.utils.formatting import normalize_description, parse_amount

        normalized = []
        for tx in transactions:
            normalized_tx = {
                'date': tx.get('date', ''),
                'description': normalize_description(tx.get('description', '')),
                'amount': parse_amount(str(tx.get('amount', 0))),
                'type': tx.get('type', 'unknown'),
                'debit': tx.get('debit', 0),
                'credit': tx.get('credit', 0),
                'balance': tx.get('balance', 0),
                'reference': tx.get('reference', ''),
                'card_no': tx.get('card_no', ''),
                'value_date': tx.get('value_date', tx.get('date', '')),
                'merchant': tx.get('merchant', tx.get('description', '')),
                'narration': tx.get('narration', tx.get('description', '')),
            }
            normalized.append(normalized_tx)

        return normalized

    def _deduplicate_all(self, transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate all transactions."""
        from statement_parser.utils.validation import deduplicate_transactions
        return deduplicate_transactions(transactions)


class ParseResult:
    """Result of parsing a statement."""

    def __init__(self, transactions: List[Dict[str, Any]], statement_type: str,
                 raw_text: str, metadata: Dict[str, Any] = None,
                 errors: List[str] = None, warnings: List[str] = None):
        """Initialize the parse result."""
        self.transactions = transactions
        self.statement_type = statement_type
        self.raw_text = raw_text
        self.metadata = metadata or {}
        self.errors = errors or []
        self.warnings = warnings or []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'transactions': self.transactions,
            'statement_type': self.statement_type,
            'metadata': self.metadata,
            'errors': self.errors,
            'warnings': self.warnings,
            'transaction_count': len(self.transactions),
        }

    def to_excel(self, filepath: str, include_summary: bool = True) -> bool:
        """
        Export to Excel format.

        Args:
            filepath: Output file path
            include_summary: Include summary sheet

        Returns:
            True if successful
        """
        generator = OutputGenerator(self.transactions, self.statement_type)
        return generator.to_excel(filepath, include_summary)

    def to_csv(self, filepath: str, delimiter: str = ',') -> bool:
        """
        Export to CSV format.

        Args:
            filepath: Output file path
            delimiter: CSV delimiter

        Returns:
            True if successful
        """
        generator = OutputGenerator(self.transactions, self.statement_type)
        return generator.to_csv(filepath, delimiter)

    def to_json(self, filepath: str, indent: int = 2) -> bool:
        """
        Export to JSON format.

        Args:
            filepath: Output file path
            indent: JSON indentation

        Returns:
            True if successful
        """
        generator = OutputGenerator(self.transactions, self.statement_type)
        return generator.to_json(filepath, indent)

    def to_list(self) -> List[Dict[str, Any]]:
        """Return transactions list."""
        return self.transactions

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of parsed transactions."""
        total_credit = 0.0
        total_debit = 0.0

        for tx in self.transactions:
            credit = float(tx.get('credit', 0) or 0)
            debit = float(tx.get('debit', 0) or 0)

            # If credit/debit are not set but amount is, use amount
            if credit == 0 and debit == 0 and 'amount' in tx:
                amount = float(tx.get('amount', 0) or 0)
                # Assume debit if type is 'debit' or not specified
                tx_type = tx.get('type', 'debit').lower()
                if tx_type == 'credit':
                    credit = amount
                else:
                    debit = amount
            else:
                credit = credit
                debit = debit

            total_credit += credit
            total_debit += debit

        return {
            'total_transactions': len(self.transactions),
            'total_credits': total_credit,
            'total_debits': total_debit,
            'net_amount': total_credit - total_debit,
            'statement_type': self.statement_type,
            'errors': len(self.errors),
            'warnings': len(self.warnings),
        }
