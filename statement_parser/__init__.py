"""
Statement Parser Library

A standalone library for parsing financial statements (bank, credit card, UPI)
and converting them to normalized Excel/CSV formats.

Usage:
    from statement_parser import StatementParser

    parser = StatementParser()
    result = parser.parse_file("statement.pdf")
    result.to_excel("output.xlsx")
"""

from .parser import StatementParser, ParseOptions
from .detector import StatementType, detect_statement_type
from .formats.base import BaseParser

__version__ = "0.1.0"
__all__ = [
    "StatementParser",
    "ParseOptions",
    "StatementType",
    "detect_statement_type",
    "BaseParser",
]
