# Statement Parser

A standalone library for parsing financial statements (bank, credit card, UPI) and converting them to normalized Excel/CSV formats.

## Features

- **Pattern-based parsing** - Uses regex patterns, not AI (AI can be added as fallback)
- **Multiple statement types** - Supports bank statements, credit cards, and UPI payments
- **Adaptive learning** - Learns patterns from statements for better parsing
- **Normalized output** - Standardizes dates, amounts, and descriptions
- **Multiple export formats** - Excel (XLSX), CSV, and JSON

## Installation

```bash
pip install statement-parser
```

Or from source:

```bash
git clone https://github.com/your-org/statement-parser.git
cd statement-parser
pip install -e .
```

## Usage

### Basic Usage

```python
from statement_parser import StatementParser

parser = StatementParser()

# Parse a PDF file
result = parser.parse_file("statement.pdf")

# Access transactions
for tx in result.transactions:
    print(f"{tx['date']}: {tx['description']} - ₹{tx['amount']}")

# Export to Excel
result.to_excel("output.xlsx")

# Get summary
summary = result.get_summary()
print(f"Total transactions: {summary['total_transactions']}")
print(f"Total credits: ₹{summary['total_credits']}")
print(f"Total debits: ₹{summary['total_debits']}")
```

### Command Line Interface

```bash
# Parse a single file (outputs Excel by default)
python -m statement_parser examples statement.pdf

# Parse multiple files
python -m statement_parser examples *.pdf

# Output to CSV instead of Excel
python -m statement_parser examples -f csv statement.pdf

# Specify output directory
python -m statement_parser examples -o ./output *.pdf

# Show help
python -m statement_parser --help
```

### Programmatic Usage

```python
from statement_parser import StatementParser, ParseOptions

# Customize options
options = ParseOptions(
    output_format='csv',
    output_dir='./output',
    normalize=True,
    deduplicate=True
)

parser = StatementParser(options)
result = parser.parse_file("statement.pdf")
```

## Supported Statement Types

### Bank Statements
- HDFC Bank (fixed-width and CSV formats)
- ICICI Bank
- SBI
- Other banks with standard formats

### Credit Card Statements
- HDFC Credit Card
- ICICI Credit Card (including Amazon ICICI)
- SBI Credit Card
- AU Bank Credit Card
- Other credit cards

### UPI/Third-party Statements
- Ixigo
- AU Bank (via UPI)
- PhonePe
- Google Pay
- Other UPI-based platforms

## Output Schema

### Bank Statements
| Column | Description |
|--------|-------------|
| Date | Transaction date (DD/MM/YYYY) |
| Narration | Transaction description |
| Value Date | Value date |
| Debit | Debit amount |
| Credit | Credit amount |
| Balance | Running balance |
| Reference | Reference number |

### Credit Card Statements
| Column | Description |
|--------|-------------|
| Date | Transaction date |
| Merchant | Merchant name |
| Amount | Transaction amount |
| Type | Debit/Credit |
| Card No | Card number |
| Reference | Reference number |

### UPI Statements
| Column | Description |
|--------|-------------|
| Date | Transaction date |
| Merchant | Merchant/Payee name |
| Amount | Transaction amount |
| Type | Debit/Credit |
| Reference | Reference number |
| UPI Ref | UPI transaction ID |

## Directory Structure

```
statement-parser/
├── statement_parser/
│   ├── __init__.py          # Package initialization
│   ├── parser.py            # Main entry point
│   ├── detector.py          # Statement type detection
│   ├── formats/
│   │   ├── __init__.py
│   │   ├── base.py          # Base parser class
│   │   ├── generic_parser.py  # Generic parser (no AI)
│   │   ├── bank_statement.py  # Bank statements
│   │   ├── credit_card.py     # Credit card statements
│   │   └── upi_statement.py   # UPI statements
│   ├── patterns/
│   │   ├── generic.py       # Generic patterns
│   │   ├── hdfc.py          # HDFC patterns
│   │   ├── icici.py         # ICICI patterns
│   │   └── sbi.py           # SBI patterns
│   └── utils/
│       ├── formatting.py    # Number/date normalization
│       └── validation.py    # Output validation
├── tests/
│   ├── test_parser.py
│   └── test_statements/
├── examples/
│   └── cli.py               # CLI tool
├── docs/
│   ├── README.md            # Jupyter examples overview
│   ├── API.md               # API documentation
│   ├── USAGE.md             # Usage examples
│   └── examples/            # Jupyter notebooks
├── pyproject.toml
└── README.md
```

## Development

```bash
# Run tests
pytest tests/

# Run tests with coverage
pytest --cov=statement_parser tests/

# Run linter
ruff check .
```

## Documentation

- **[API Documentation](docs/API.md)** - Complete API reference
- **[Usage Guide](docs/USAGE.md)** - Detailed usage examples
- **[Jupyter Notebooks](docs/examples/)** - Interactive examples

## License

MIT License
