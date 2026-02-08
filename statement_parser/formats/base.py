"""
Base parser class for all statement parsers.
"""

import re
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from statement_parser.utils.formatting import normalize_description, parse_date, parse_amount
from statement_parser.utils.validation import validate_transaction, deduplicate_transactions


@dataclass
class ParseResult:
    """Result of parsing a statement."""
    transactions: List[Dict[str, Any]]
    statement_type: str
    raw_text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

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

    def to_list(self) -> List[Dict[str, Any]]:
        """Return just the transactions list."""
        return self.transactions


class BaseParser(ABC):
    """
    Abstract base class for statement parsers.

    All specific parsers should inherit from this class.
    """

    statement_type: str = "base"

    def __init__(self):
        """Initialize the base parser."""
        self.transactions: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.column_mapping: Dict[str, int] = {}

    @abstractmethod
    def can_parse(self, text: str) -> bool:
        """Check if this parser can handle the given text."""
        pass

    @abstractmethod
    def parse(self, text: str) -> ParseResult:
        """Parse the statement text."""
        pass

    def _normalize_transaction(self, tx: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a transaction to standard format."""
        normalized = {
            'date': tx.get('date', ''),
            'description': normalize_description(tx.get('description', '')),
            'amount': parse_amount(str(tx.get('amount', 0))),
            'type': tx.get('type', 'unknown'),
            'reference': tx.get('reference', ''),
            'card_no': tx.get('card_no', ''),
            'value_date': tx.get('value_date', ''),
            'narration': tx.get('narration', tx.get('description', '')),
            'debit': tx.get('debit', 0),
            'credit': tx.get('credit', 0),
            'balance': tx.get('balance', 0),
            'merchant': tx.get('merchant', tx.get('description', '')),
        }
        return normalized

    def _validate_transaction(self, tx: Dict[str, Any]) -> bool:
        """Validate a single transaction."""
        result = validate_transaction(tx)
        if not result.is_valid:
            self.errors.extend(result.errors)
            self.warnings.extend(result.warnings)
        return result.is_valid

    def _deduplicate(self, transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate transactions."""
        return deduplicate_transactions(transactions)

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
        ]

        line_lower = line.lower()
        return any(kw in line_lower for kw in header_keywords)
