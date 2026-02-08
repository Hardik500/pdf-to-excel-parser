"""
Validation utilities for parsed transactions.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ValidationResult:
    """Result of validating a transaction."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    normalized_data: Optional[Dict[str, Any]] = None


def validate_transaction(transaction: Dict[str, Any]) -> ValidationResult:
    """
    Validate a single transaction record.

    Checks:
    - Required fields are present
    - Date format and validity
    - Amount is numeric and reasonable
    - Description is not empty

    Args:
        transaction: Transaction dictionary to validate

    Returns:
        ValidationResult with validation status and messages
    """
    errors = []
    warnings = []
    normalized = {}

    # Required fields
    required_fields = ['date', 'description']
    for field in required_fields:
        if field not in transaction:
            errors.append(f"Missing required field: {field}")

    # Check amount OR (debit and credit)
    amount = transaction.get('amount')
    debit = transaction.get('debit')
    credit = transaction.get('credit')

    if amount is None and debit is None and credit is None:
        errors.append("Missing amount or debit/credit fields")

    if errors:
        return ValidationResult(False, errors, warnings, None)

    # Validate date
    date_str = str(transaction.get('date', ''))
    if not date_str:
        errors.append("Date is empty")
    else:
        # Check date format
        if not re.match(r'^\d{2}/\d{2}/\d{4}$', date_str):
            warnings.append(f"Date may not be in correct format: {date_str}")

    # Validate amount (either 'amount' field or (debit or credit))
    if amount is not None:
        try:
            amount_val = float(amount)
            if amount_val == 0:
                warnings.append("Amount is zero")
            elif abs(amount_val) > 10000000:  # 1 Crore
                warnings.append(f" unusually large amount: {amount}")
        except (ValueError, TypeError):
            errors.append(f"Invalid amount: {amount}")
    elif debit is not None or credit is not None:
        # If we have debit/credit, at least one should be non-zero
        if not (debit and float(debit) > 0) and not (credit and float(credit) > 0):
            warnings.append("Both debit and credit are zero")
    else:
        errors.append("Missing amount or debit/credit fields")

    # Validate description
    description = transaction.get('description', '')
    if not description or len(str(description).strip()) < 3:
        errors.append("Description is too short or empty")

    # Determine if transaction is valid
    is_valid = len(errors) == 0

    # Create normalized data if valid
    if is_valid:
        normalized = {
            'date': transaction['date'],
            'description': str(transaction.get('description', '')).strip(),
            'amount': float(transaction['amount']) if 'amount' in transaction else 0.0,
            'type': transaction.get('type', 'unknown'),
            'reference': transaction.get('reference', ''),
        }

    return ValidationResult(is_valid, errors, warnings, normalized)


def validate_transactions(transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validate a list of transactions.

    Args:
        transactions: List of transaction dictionaries

    Returns:
        Dict with summary stats and any invalid transactions
    """
    valid_count = 0
    invalid_count = 0
    total_warnings = 0
    invalid_transactions = []
    total_amount = 0.0

    for i, tx in enumerate(transactions):
        result = validate_transaction(tx)

        if result.is_valid:
            valid_count += 1
            if result.normalized_data:
                total_amount += result.normalized_data.get('amount', 0)
        else:
            invalid_count += 1
            result_dict = {
                'index': i,
                'transaction': tx,
                'errors': result.errors,
                'warnings': result.warnings,
            }
            invalid_transactions.append(result_dict)

        total_warnings += len(result.warnings)

    return {
        'summary': {
            'total': len(transactions),
            'valid': valid_count,
            'invalid': invalid_count,
            'total_warnings': total_warnings,
            'total_amount': round(total_amount, 2),
        },
        'invalid_transactions': invalid_transactions,
    }


def validate_output_schema(data: List[Dict[str, Any]], statement_type: str) -> ValidationResult:
    """
    Validate that output data matches expected schema for statement type.

    Args:
        data: List of transaction records
        statement_type: Type of statement ('bank', 'credit_card', 'upi')

    Returns:
        ValidationResult indicating schema compliance
    """
    # Schema definitions
    bank_schema = ['date', 'narration', 'value_date', 'debit', 'credit', 'balance', 'reference']
    credit_card_schema = ['date', 'merchant', 'amount', 'type', 'card_no', 'reference']
    upi_schema = ['date', 'narration', 'value_date', 'debit', 'credit', 'reference', 'upi_ref']

    expected = {
        'bank': bank_schema,
        'credit_card': credit_card_schema,
        'upi': upi_schema,
    }

    if statement_type not in expected:
        return ValidationResult(False, [f"Unknown statement type: {statement_type}"], [])

    required_fields = expected[statement_type]
    errors = []
    missing_fields = []

    for i, record in enumerate(data):
        for field in required_fields:
            if field not in record:
                missing_fields.append(f"Record {i}: missing {field}")

    if missing_fields:
        errors.extend(missing_fields)
        return ValidationResult(False, errors, [])

    return ValidationResult(True, [], [], None)


# Pre-compiled date pattern for deduplication
_DEDUP_DATE_PATTERN = re.compile(r'^(\d{2})/(\d{2})/(\d{4})$')


def _parse_date_for_dedup(date_str: str) -> Optional[datetime]:
    """
    Fast date parsing for deduplication (only DD/MM/YYYY format).

    This is optimized for the date format we produce, avoiding the
    expensive dateutil.parser.parse() call.

    Args:
        date_str: Date string in DD/MM/YYYY format

    Returns:
        datetime object or None if parsing fails
    """
    if not date_str or not isinstance(date_str, str):
        return None

    match = _DEDUP_DATE_PATTERN.match(date_str)
    if match:
        day, month, year = match.groups()
        try:
            return datetime(int(year), int(month), int(day))
        except ValueError:
            pass
    return None


def is_duplicate_transaction(tx1: Dict[str, Any], tx2: Dict[str, Any], threshold_days: int = 1) -> bool:
    """
    Check if two transactions are likely duplicates.

    Comparison criteria:
    - Same date (within threshold)
    - Same amount (within 0.01)
    - Similar description (within threshold)

    Args:
        tx1: First transaction
        tx2: Second transaction
        threshold_days: Date matching threshold in days

    Returns:
        True if likely duplicate
    """
    # Check amount match first (fastest check)
    amount1 = float(tx1.get('amount', 0))
    amount2 = float(tx2.get('amount', 0))
    if abs(amount1 - amount2) > 0.01:
        return False

    # Check date match (within threshold) - use fast parser
    try:
        date1 = _parse_date_for_dedup(tx1.get('date', ''))
        date2 = _parse_date_for_dedup(tx2.get('date', ''))

        if date1 is None or date2 is None:
            return False

        if abs((date1 - date2).days) > threshold_days:
            return False
    except Exception:
        # If date parsing fails, skip date check
        pass

    # Check description similarity (case-insensitive)
    desc1 = str(tx1.get('description', '')).lower().strip()
    desc2 = str(tx2.get('description', '')).lower().strip()

    # Check reference numbers - if both have references and they differ, not duplicates
    ref1 = str(tx1.get('reference', '')).strip()
    ref2 = str(tx2.get('reference', '')).strip()
    if ref1 and ref2 and ref1 != ref2:
        return False

    # Also check narration for additional uniqueness
    narr1 = str(tx1.get('narration', '')).lower().strip()
    narr2 = str(tx2.get('narration', '')).lower().strip()
    if narr1 and narr2 and narr1 != narr2:
        return False

    # Simple similarity check - only mark as duplicate if description is very similar
    # and reference numbers are the same or missing
    if desc1 == desc2:
        return True

    # Check if one description contains the other (similar transaction)
    if desc1 in desc2 or desc2 in desc1:
        return True

    return False


def _get_dedup_key(tx: Dict[str, Any]) -> Tuple[float, str]:
    """
    Generate a deduplication key for a transaction.

    Transactions with the same key are considered duplicates if they also
    pass the is_duplicate_transaction check.

    Args:
        tx: Transaction dictionary

    Returns:
        Tuple of (amount, date_str) for grouping
    """
    amount = float(tx.get('amount', 0))
    date_str = tx.get('date', '')
    return (amount, date_str)


def deduplicate_transactions(transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate transactions from a list.

    Uses a two-phase approach:
    1. Group transactions by amount and date for fast candidate selection
    2. Check each group for actual duplicates

    Args:
        transactions: List of transaction dictionaries

    Returns:
        List of unique transactions (first occurrence kept)
    """
    if not transactions:
        return []

    # Phase 1: Group by dedup key (amount + date)
    groups: Dict[Tuple[float, str], List[Dict[str, Any]]] = {}
    for tx in transactions:
        key = _get_dedup_key(tx)
        if key not in groups:
            groups[key] = []
        groups[key].append(tx)

    # Phase 2: Check each group for duplicates
    unique = []
    for group in groups.values():
        if len(group) == 1:
            # No possible duplicates
            unique.append(group[0])
        else:
            # Need to check for duplicates within the group
            for tx in group:
                is_dup = False
                for existing in unique:
                    if is_duplicate_transaction(tx, existing):
                        is_dup = True
                        break
                if not is_dup:
                    unique.append(tx)

    return unique
