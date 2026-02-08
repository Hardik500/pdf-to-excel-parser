# Statement Parser - Jupyter Notebook Examples

This directory contains Jupyter notebooks demonstrating various use cases for the Statement Parser library.

## Available Notebooks

### 1. Quick Start.ipynb
A beginner-friendly introduction to the Statement Parser.

**Topics covered:**
- Installation and setup
- Basic parsing workflow
- Understanding ParseResult
- Exporting to Excel/CSV/JSON

**Run with:**
```bash
jupyter notebook Quick Start.ipynb
```

---

### 2. Bank Statement Analysis.ipynb
Deep dive into parsing bank statements.

**Topics covered:**
- Bank statement detection
- CSV vs fixed-width format handling
- Extracting transaction details
- Analyzing bank statements with pandas

**Run with:**
```bash
jupyter notebook Bank Statement Analysis.ipynb
```

---

### 3. Credit Card Statement Analysis.ipynb
Parsing and analyzing credit card statements.

**Topics covered:**
- Credit card statement detection
- Merchant name extraction
- Categorizing transactions
- Monthly expense reports

**Run with:**
```bash
jupyter notebook Credit Card Statement Analysis.ipynb
```

---

### 4. UPI Payment Analysis.ipynb
Parsing UPI and third-party payment statements.

**Topics covered:**
- UPI statement detection
- Payment app statements (PhonePe, Google Pay, etc.)
- UPI reference number extraction
- Tracking third-party payments

**Run with:**
```bash
jupyter notebook UPI Payment Analysis.ipynb
```

---

### 5. Batch Processing.ipynb
Processing multiple statements at once.

**Topics covered:**
- Batch parsing workflow
- Merging transactions from multiple files
- Creating consolidated reports
- Handling multiple statement types

**Run with:**
```bash
jupyter notebook Batch Processing.ipynb
```

---

### 6. Advanced Features.ipynb
Advanced parsing options and customization.

**Topics covered:**
- Custom ParseOptions
- Manual transaction processing
- Custom categorization logic
- Data validation and cleaning

**Run with:**
```bash
jupyter notebook Advanced Features.ipynb
```

---

## Prerequisites

Install the required packages:

```bash
pip install statement-parser pandas openpyxl
```

For some examples, you may also need:

```bash
pip install jupyter matplotlib seaborn
```

## Running the Notebooks

### Option 1: Local Jupyter

```bash
cd docs
jupyter notebook
```

### Option 2: Google Colab

1. Upload the notebook to Google Colab
2. Install the package:
```python
!pip install statement-parser pandas
```
3. Run the cells

## Example Code Snippets

### Quick Parse and Export

```python
from statement_parser import StatementParser

parser = StatementParser()
result = parser.parse_file("bank_statement.pdf")

# Get summary
summary = result.get_summary()
print(f"Transactions: {summary['total_transactions']}")
print(f"Credits: ₹{summary['total_credits']:,.2f}")
print(f"Debits: ₹{summary['total_debits']:,.2f}")

# Export
result.to_excel("output.xlsx")
```

### Analyze with Pandas

```python
import pandas as pd
from statement_parser import StatementParser

parser = StatementParser()
result = parser.parse_file("bank_statement.pdf")

# Convert to DataFrame
df = pd.DataFrame(result.transactions)

# Analyze
print(df.describe())
print(df.groupby('type')['amount'].sum())
```

### Categorize Transactions

```python
from statement_parser import StatementParser

parser = StatementParser()
result = parser.parse_file("bank_statement.pdf")

# Define categories
categories = {
    'groceries': ['grofers', 'dmart', 'tata cliq'],
    'dining': ['swiggy', 'zomato', 'food'],
    'transport': ['uber', 'ola'],
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

## Troubleshooting

### "No module named 'statement_parser'"

Make sure you're in the correct environment:
```bash
pip install statement-parser
```

### "File not found" error

Check the file path:
```python
import os
print(os.listdir("."))  # List files in current directory
```

### Parser returns 0 transactions

Check the statement type:
```python
print(f"Statement type: {result.statement_type}")
print(f"Warnings: {result.warnings}")
```
