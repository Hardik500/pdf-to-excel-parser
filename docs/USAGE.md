# Statement Parser - Usage Examples

## Basic Usage

### Parse a Single Statement

```python
from statement_parser import StatementParser

# Create parser
parser = StatementParser()

# Parse a PDF file
result = parser.parse_file("statements/bank_statement.pdf")

# Print summary
summary = result.get_summary()
print(f"Type: {summary['statement_type']}")
print(f"Transactions: {summary['total_transactions']}")
print(f"Credits: ₹{summary['total_credits']:,.2f}")
print(f"Debits: ₹{summary['total_debits']:,.2f}")
print(f"Net: ₹{summary['net_amount']:,.2f}")
```

### Parse Multiple Files

```python
import glob
from statement_parser import StatementParser

parser = StatementParser()

# Parse all PDF files in a directory
for filepath in glob.glob("statements/*.pdf"):
    result = parser.parse_file(filepath)
    print(f"{filepath}: {len(result.transactions)} transactions")
```

## Output Formats

### Export to Excel

```python
from statement_parser import StatementParser

parser = StatementParser()
result = parser.parse_file("statement.pdf")

# Export to Excel
result.to_excel("output.xlsx")

# With custom filename
result.to_excel("my_statement.xlsx")
```

### Export to CSV

```python
from statement_parser import StatementParser

parser = StatementParser()
result = parser.parse_file("statement.pdf")

# Export to CSV
result.to_csv("output.csv")
```

### Export to JSON

```python
from statement_parser import StatementParser

parser = StatementParser()
result = parser.parse_file("statement.pdf")

# Export to JSON
result.to_json("output.json")
```

## Processing Transactions

### Iterate Through Transactions

```python
from statement_parser import StatementParser

parser = StatementParser()
result = parser.parse_file("statement.pdf")

# Process each transaction
for tx in result.transactions:
    date = tx.get('date', '')
    desc = tx.get('narration') or tx.get('description', '')
    amount = tx.get('amount', tx.get('credit', tx.get('debit', 0)))

    print(f"{date}: {desc} - ₹{amount:,.2f}")
```

### Filter Transactions

```python
from statement_parser import StatementParser

parser = StatementParser()
result = parser.parse_file("statement.pdf")

# Filter by date range
for tx in result.transactions:
    if tx['date'].startswith('2024'):
        print(f"2024 transaction: {tx['description']}")

# Filter by amount
for tx in result.transactions:
    amount = tx.get('credit', 0) + tx.get('debit', 0)
    if amount > 10000:
        print(f"Large transaction: ₹{amount:,.2f}")
```

### Categorize Transactions

```python
from statement_parser import StatementParser

parser = StatementParser()
result = parser.parse_file("statement.pdf")

# Simple categorization
categories = {
    'groceries': ['grofers', 'dmart', 'tata cliq', 'amazon grocery'],
    'dining': ['swiggy', 'zomato', 'restaurant', 'food'],
    'transport': ['uber', 'ola', 'google pay', 'phonepe'],
    'utilities': ['electricity', 'water', 'gas', 'bills'],
}

for tx in result.transactions:
    desc = tx.get('description', '').lower()
    category = 'other'

    for cat, keywords in categories.items():
        if any(kw in desc for kw in keywords):
            category = cat
            break

    print(f"{tx['date']}: {tx['description']} [{category}]")
```

## Custom Options

### Configure Output Format

```python
from statement_parser import StatementParser, ParseOptions

# Configure for CSV output
options = ParseOptions(
    output_format='csv',
    output_dir='./exports',
    normalize=True,
    deduplicate=True
)

parser = StatementParser(options)
result = parser.parse_file("statement.pdf")
```

### Disable Deduplication

```python
from statement_parser import StatementParser, ParseOptions

# Disable deduplication to see all raw transactions
options = ParseOptions(
    output_format='excel',
    deduplicate=False
)

parser = StatementParser(options)
result = parser.parse_file("statement.pdf")
```

## Command Line Usage

### Basic Parsing

```bash
# Parse a single file (exports to Excel by default)
python -m statement_parser statement.pdf

# Parse with CSV output
python -m statement_parser -f csv statement.pdf

# Parse with custom output directory
python -m statement_parser -o ./output statement.pdf
```

### Parse Multiple Files

```bash
# Parse all PDFs in a directory
python -m statement_parser *.pdf

# Parse specific files
python -m statement_parser file1.pdf file2.pdf file3.pdf
```

### CLI Options

| Option | Description |
|--------|-------------|
| `-f, --format` | Output format: excel, csv, or json |
| `-o, --output-dir` | Output directory (default: current) |
| `-s, --no-summary` | Don't include summary sheet in Excel |
| `-q, --quiet` | Suppress output messages |
| `--no-dedup` | Don't deduplicate transactions |
| `-v, --verbose` | Show verbose output |

## Advanced Examples

### Batch Process with Custom Logic

```python
import os
import glob
from statement_parser import StatementParser

parser = StatementParser()

# Process all statements
for filepath in glob.glob("statements/*.pdf"):
    print(f"Processing {os.path.basename(filepath)}...")

    try:
        result = parser.parse_file(filepath)

        # Calculate totals
        total_credits = sum(tx.get('credit', 0) for tx in result.transactions)
        total_debits = sum(tx.get('debit', 0) for tx in result.transactions)

        # Check for anomalies
        large_transactions = [
            tx for tx in result.transactions
            if tx.get('debit', 0) > 50000
        ]

        print(f"  Credits: ₹{total_credits:,.2f}")
        print(f"  Debits: ₹{total_debits:,.2f}")
        print(f"  Large transactions: {len(large_transactions)}")

    except Exception as e:
        print(f"  Error: {e}")
```

### Merge Multiple Statements

```python
from statement_parser import StatementParser
from collections import defaultdict

parser = StatementParser()

# Parse multiple statements
results = []
for filepath in glob.glob("statements/*.pdf"):
    results.append(parser.parse_file(filepath))

# Merge transactions
all_transactions = []
for result in results:
    all_transactions.extend(result.transactions)

# Sort by date
all_transactions.sort(key=lambda x: x['date'])

# Group by month
by_month = defaultdict(list)
for tx in all_transactions:
    month = tx['date'][:7]  # YYYY-MM
    by_month[month].append(tx)

# Print monthly summary
for month, transactions in sorted(by_month.items()):
    credits = sum(tx.get('credit', 0) for tx in transactions)
    debits = sum(tx.get('debit', 0) for tx in transactions)
    print(f"{month}: Credits ₹{credits:,.2f}, Debits ₹{debits:,.2f}")
```

## Troubleshooting

### Empty Transaction List

If you get 0 transactions:

1. **Check the statement type detection:**
```python
print(f"Detected type: {result.statement_type}")
```

2. **Check for errors/warnings:**
```python
if result.errors:
    print("Errors:", result.errors)
if result.warnings:
    print("Warnings:", result.warnings)
```

3. **Try the generic parser:**
```python
from statement_parser.formats.generic_parser import GenericStatementParser

generic_parser = GenericStatementParser()
result = generic_parser.parse_file("statement.pdf")
```

### Parse Errors

For PDF parsing errors:

1. **Check if the PDF is valid:**
```bash
# Try opening the PDF in a viewer
```

2. **Try text-based extraction:**
```python
# If you have a text version of the statement
with open("statement.txt") as f:
    text = f.read()

result = parser.parse_text(text)
```
