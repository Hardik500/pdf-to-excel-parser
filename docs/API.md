# Statement Parser API Documentation

## Overview

The Statement Parser library allows you to parse financial statements (bank, credit card, UPI) and convert them to normalized Excel/CSV formats.

## Installation

```bash
pip install statement-parser
```

## Quick Start

```python
from statement_parser import StatementParser

parser = StatementParser()

# Parse a PDF file
result = parser.parse_file("statement.pdf")

# Access transactions
for tx in result.transactions:
    print(f"{tx['date']}: {tx['description']} - {tx.get('amount', 0)}")

# Export to Excel
result.to_excel("output.xlsx")
```

## Main Classes

### StatementParser

The main entry point for parsing statements.

```python
from statement_parser import StatementParser

parser = StatementParser(options=None)
```

**Parameters:**
- `options` (ParseOptions, optional): Configuration options for parsing

**Methods:**

| Method | Description |
|--------|-------------|
| `parse_file(filepath, options=None)` | Parse a PDF/text file and return ParseResult |
| `parse_text(text, options=None)` | Parse text content and return ParseResult |

### ParseOptions

Configuration options for parsing.

```python
from statement_parser import ParseOptions

options = ParseOptions(
    output_format='excel',  # 'excel', 'csv', or 'json'
    output_dir='.',         # Output directory
    normalize=True,         # Normalize transaction data
    deduplicate=True        # Remove duplicate transactions
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `output_format` | str | 'excel' | Output format: 'excel', 'csv', or 'json' |
| `output_dir` | str | '.' | Directory to save output files |
| `normalize` | bool | True | Normalize transaction data (dates, descriptions) |
| `deduplicate` | bool | True | Remove duplicate transactions |

### ParseResult

Contains the result of parsing a statement.

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `transactions` | List[Dict] | List of parsed transactions |
| `statement_type` | str | Type of statement ('bank', 'credit_card', 'upi') |
| `raw_text` | str | Original text from the statement |
| `errors` | List[str] | List of parsing errors |
| `warnings` | List[str] | List of warnings |
| `metadata` | Dict | Parser metadata |

**Methods:**

| Method | Description |
|--------|-------------|
| `to_excel(filepath, include_summary=True)` | Export to Excel file |
| `to_csv(filepath)` | Export to CSV file |
| `to_json(filepath)` | Export to JSON file |
| `get_summary()` | Get summary statistics |
| `to_dict()` | Convert to dictionary |

## Statement Types

### Bank Statements

Format: HDFC, ICICI, SBI, and generic bank statements

**Output columns:**
- `date`: Transaction date (DD/MM/YYYY)
- `narration`: Transaction description
- `value_date`: Value date
- `debit`: Debit amount
- `credit`: Credit amount
- `balance`: Running balance
- `reference`: Reference number

### Credit Card Statements

Format: HDFC, ICICI, SBI, and generic credit cards

**Output columns:**
- `date`: Transaction date (DD/MM/YYYY)
- `merchant`: Merchant name
- `amount`: Transaction amount
- `type`: Transaction type (debit/credit)
- `card_no`: Card number (last 4 digits)
- `reference`: Reference number

### UPI Statements

Format: Ixigo, AU Bank, PhonePe, Google Pay

**Output columns:**
- `date`: Transaction date (DD/MM/YYYY)
- `merchant`: Merchant/Payee name
- `amount`: Transaction amount
- `type`: Transaction type (debit/credit)
- `reference`: Reference number
- `upi_ref`: UPI transaction ID

## Examples

### Parse and Export

```python
from statement_parser import StatementParser

parser = StatementParser()

# Parse a file
result = parser.parse_file("bank_statement.pdf")

# Export to different formats
result.to_excel("output.xlsx")
result.to_csv("output.csv")
result.to_json("output.json")
```

### Programmatic Control

```python
from statement_parser import StatementParser, ParseOptions

# Configure options
options = ParseOptions(
    output_format='csv',
    output_dir='./exports',
    normalize=True,
    deduplicate=True
)

parser = StatementParser(options)
result = parser.parse_file("statement.pdf")

# Get summary
summary = result.get_summary()
print(f"Transactions: {summary['total_transactions']}")
print(f"Credits: {summary['total_credits']}")
print(f"Debits: {summary['total_debits']}")
```

### Parse Text Directly

```python
from statement_parser import StatementParser

parser = StatementParser()

# Read text from file
with open("statement.txt") as f:
    text = f.read()

# Parse text
result = parser.parse_text(text)
print(f"Found {len(result.transactions)} transactions")
```

## Error Handling

```python
from statement_parser import StatementParser

parser = StatementParser()

try:
    result = parser.parse_file("statement.pdf")

    # Check for errors
    if result.errors:
        print("Errors:", result.errors)

    # Check for warnings
    if result.warnings:
        print("Warnings:", result.warnings)

    # Process transactions
    for tx in result.transactions:
        print(f"{tx['date']}: {tx['description']}")

except FileNotFoundError:
    print("File not found!")
except Exception as e:
    print(f"Error: {e}")
```

## Advanced Usage

### Access Raw Metadata

```python
result = parser.parse_file("statement.pdf")

# Get parser metadata
print(f"Parser: {result.metadata['parser']}")
print(f"Transaction count: {result.metadata['transaction_count']}")

# Get parsed columns (from generic parser)
if 'columns_detected' in result.metadata:
    print(f"Columns: {result.metadata['columns_detected']}")
```

### Custom Processing

```python
result = parser.parse_file("statement.pdf")

# Process transactions with custom logic
for tx in result.transactions:
    # Categorize by amount
    if tx.get('credit', 0) > 10000:
        print(f"Large credit: {tx['description']}")

    # Filter by date
    if tx['date'].startswith('01/'):
        print(f"January transaction: {tx['description']}")
```
