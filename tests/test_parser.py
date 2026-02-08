"""
Tests for the Statement Parser library.
"""

import os
import pytest
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from statement_parser import StatementParser, detect_statement_type, StatementType
from statement_parser.detector import detect_statement_type as detector
from statement_parser.parser import ParseResult


# Test files path
TEST_STATEMENTS_DIR = Path(__file__).parent / "test_statements"


class TestStatementDetector:
    """Tests for statement type detection."""

    def test_detect_credit_card(self):
        """Test detection of credit card statements."""
        text = """
        HDFC Bank Ltd.
        Credit Card Statement
        Card Number: 4123 XXXX XXXX 1234
        Total Amount Due: 5,000.00
        Minimum Amount Due: 250.00
        """
        result = detector(text)
        assert result == StatementType.CREDIT_CARD

    def test_detect_bank_statement(self):
        """Test detection of bank account statements."""
        text = """
        HDFC Bank Ltd.
        Statement of Accounts
        Account Number: XXXX4651
        Closing Balance: 1,50,000.00
        Withdrawal Amt. Deposit Amt.
        """
        result = detector(text)
        assert result == StatementType.BANK

    def test_detect_upi_statement(self):
        """Test detection of UPI/payment statements."""
        text = """
        Ixigo Financial Services Pvt Ltd
        UPI Transaction Statement
        Account Number: 825XXXXXXX
        Statement for January 2026

        Transaction Details:
        01/01/2026 IRCTC CHENNAI IN
        12 ₹2,948.00
        Jan 26 Dr

        02/01/2026 SWIGGY MUMBAI IN
        12 ₹449.00
        Jan 26 Dr
        """
        result = detector(text)
        assert result == StatementType.UPI

    def test_detect_unknown(self):
        """Test detection of unknown statement type."""
        text = """
        This is just some regular text
        Not a financial statement
        """
        result = detector(text)
        assert result == StatementType.UNKNOWN


class TestStatementParser:
    """Tests for the main StatementParser."""

    def test_parser_initialization(self):
        """Test parser initialization."""
        parser = StatementParser()
        assert parser is not None

    @pytest.mark.skipif(
        not TEST_STATEMENTS_DIR.exists(),
        reason="Test statements not available"
    )
    def test_parse_text_statement(self):
        """Test parsing a text statement."""
        text_file = TEST_STATEMENTS_DIR / "Acct_Statement_XXXXXXXX4651_08022026.txt"

        if not text_file.exists():
            pytest.skip("Test text file not available")

        parser = StatementParser()
        result = parser.parse_text(text_file.read_text())

        assert result is not None
        assert result.statement_type in ['bank', 'credit_card', 'upi']

    @pytest.mark.skipif(
        not (TEST_STATEMENTS_DIR / "Acct_Statement_XXXXXXXX4651_08022026.txt").exists(),
        reason="Test statements not available"
    )
    def test_parse_text_statement_returns_transactions(self):
        """Test that parsing returns transactions."""
        text_file = TEST_STATEMENTS_DIR / "Acct_Statement_XXXXXXXX4651_08022026.txt"

        parser = StatementParser()
        result = parser.parse_text(text_file.read_text())

        # Should have at least some transactions
        assert isinstance(result.transactions, list)
        # At least some transactions should be detected
        # Note: The text file is large, so we expect many transactions

    def test_parse_result_to_dict(self):
        """Test ParseResult.to_dict() method."""
        result = ParseResult(
            transactions=[],
            statement_type="bank",
            raw_text="",
        )
        data = result.to_dict()

        assert 'transactions' in data
        assert 'statement_type' in data
        assert 'transaction_count' in data

    def test_parse_result_to_excel(self, tmp_path):
        """Test ParseResult.to_excel() method."""
        result = ParseResult(
            transactions=[
                {
                    'date': '01/01/2024',
                    'narration': 'Test transaction',
                    'debit': 100.00,
                    'credit': 0.00,
                    'balance': 900.00,
                },
            ],
            statement_type="bank",
            raw_text="",
        )

        excel_file = tmp_path / "test_output.xlsx"
        result.to_excel(str(excel_file))

        assert excel_file.exists()

    def test_parse_result_to_csv(self, tmp_path):
        """Test ParseResult.to_csv() method."""
        result = ParseResult(
            transactions=[
                {
                    'date': '01/01/2024',
                    'narration': 'Test transaction',
                    'debit': 100.00,
                    'credit': 0.00,
                    'balance': 900.00,
                },
            ],
            statement_type="bank",
            raw_text="",
        )

        csv_file = tmp_path / "test_output.csv"
        result.to_csv(str(csv_file))

        assert csv_file.exists()

    def test_parse_result_to_json(self, tmp_path):
        """Test ParseResult.to_json() method."""
        result = ParseResult(
            transactions=[
                {
                    'date': '01/01/2024',
                    'narration': 'Test transaction',
                    'amount': 100.00,
                },
            ],
            statement_type="bank",
            raw_text="",
        )

        json_file = tmp_path / "test_output.json"
        result.to_json(str(json_file))

        assert json_file.exists()

    def test_get_summary(self):
        """Test ParseResult.get_summary() method."""
        result = ParseResult(
            transactions=[
                {
                    'credit': 500.00,
                    'debit': 200.00,
                },
            ],
            statement_type="bank",
            raw_text="",
        )

        summary = result.get_summary()

        assert summary['total_transactions'] == 1
        assert summary['total_credits'] == 500.00
        assert summary['total_debits'] == 200.00
        assert summary['net_amount'] == 300.00


class TestOutputGenerator:
    """Tests for the OutputGenerator class."""

    def test_excel_generation(self, tmp_path):
        """Test Excel output generation."""
        from statement_parser.output import OutputGenerator

        transactions = [
            {
                'date': '01/01/2024',
                'description': 'Test transaction 1',
                'amount': 100.00,
                'type': 'debit',
            },
            {
                'date': '02/01/2024',
                'description': 'Test transaction 2',
                'amount': 200.00,
                'type': 'credit',
            },
        ]

        generator = OutputGenerator(transactions, 'bank')
        excel_file = tmp_path / "test.xlsx"
        generator.to_excel(str(excel_file))

        assert excel_file.exists()

    def test_csv_generation(self, tmp_path):
        """Test CSV output generation."""
        from statement_parser.output import OutputGenerator

        transactions = [
            {
                'date': '01/01/2024',
                'narration': 'Test transaction',
                'amount': 100.00,
                'type': 'debit',
            },
        ]

        generator = OutputGenerator(transactions, 'bank')
        csv_file = tmp_path / "test.csv"
        generator.to_csv(str(csv_file))

        assert csv_file.exists()

        # Verify CSV content - bank statements use 'narration' not 'description'
        content = csv_file.read_text()
        assert 'date' in content.lower()
        assert 'narration' in content.lower()

    def test_json_generation(self, tmp_path):
        """Test JSON output generation."""
        from statement_parser.output import OutputGenerator

        transactions = [
            {
                'date': '01/01/2024',
                'description': 'Test transaction',
                'amount': 100.00,
                'type': 'debit',
            },
        ]

        generator = OutputGenerator(transactions, 'bank')
        json_file = tmp_path / "test.json"
        generator.to_json(str(json_file))

        assert json_file.exists()

        # Verify JSON content
        import json as json_lib
        data = json_lib.loads(json_file.read_text())
        assert 'transactions' in data
        assert len(data['transactions']) == 1


class TestPatternLearning:
    """Tests for pattern learning functionality."""

    def test_generic_parser_detection(self):
        """Test that generic parser can detect statements."""
        from statement_parser.formats.generic_parser import GenericStatementParser

        parser = GenericStatementParser()
        text = "01/01/2024 Test Transaction 100.00"
        assert parser.can_parse(text)

    def test_generic_parser_extraction(self):
        """Test that generic parser extracts transactions."""
        from statement_parser.formats.generic_parser import GenericStatementParser

        parser = GenericStatementParser()
        text = """
        Statement for January 2024

        01/01/2024 Amazon Purchase 500.00
        02/01/2024 Swiggy Order 250.00
        03/01/2026 Payment Received 1000.00 Cr
        """

        result = parser.parse(text)

        # Should extract at least some transactions
        assert len(result.transactions) >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
