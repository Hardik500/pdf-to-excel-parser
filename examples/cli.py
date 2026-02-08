#!/usr/bin/env python3
"""
Command-line interface for the Statement Parser.

Usage:
    python examples/cli.py --help
    python examples/cli.py statement.pdf
    python examples/cli.py --format csv statement.pdf
    python examples/cli.py --output-dir ./output *.pdf
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from statement_parser import StatementParser, ParseOptions


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog='statement-parser',
        description='Parse financial statements (bank, credit card, UPI) to Excel/CSV/JSON'
    )

    parser.add_argument(
        'files',
        nargs='+',
        help='Statement files to parse (PDF, text, or CSV)'
    )

    parser.add_argument(
        '-f', '--format',
        choices=['excel', 'csv', 'json'],
        default='excel',
        help='Output format (default: excel)'
    )

    parser.add_argument(
        '-o', '--output-dir',
        default='.',
        help='Output directory (default: current directory)'
    )

    parser.add_argument(
        '-s', '--no-summary',
        action='store_true',
        help='Do not include summary sheet in Excel output'
    )

    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Suppress output messages'
    )

    parser.add_argument(
        '--no-dedup',
        action='store_true',
        help='Do not deduplicate transactions'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show verbose output'
    )

    return parser.parse_args()


def process_file(filepath: Path, parser: StatementParser, options: ParseOptions, verbose: bool = False) -> tuple:
    """
    Process a single file.

    Returns:
        Tuple of (success, result_or_error)
    """
    try:
        if verbose:
            print(f"Parsing: {filepath.name}")

        if filepath.suffix.lower() == '.pdf':
            result = parser.parse_file(filepath, options)
        else:
            result = parser.parse_text(filepath.read_text(), options)

        # Export based on format
        output_dir = Path(options.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / f"{filepath.stem}_parsed"

        if options.output_format == 'excel':
            output_path = output_path.with_suffix('.xlsx')
            result.to_excel(str(output_path), include_summary=not options.include_summary)
        elif options.output_format == 'csv':
            output_path = output_path.with_suffix('.csv')
            result.to_csv(str(output_path))
        elif options.output_format == 'json':
            output_path = output_path.with_suffix('.json')
            result.to_json(str(output_path))

        return True, result

    except Exception as e:
        return False, str(e)


def main():
    """Main entry point."""
    args = parse_args()

    # Create parser with options
    options = ParseOptions(
        output_format=args.format,
        output_dir=args.output_dir,
        include_summary=not args.no_summary,
        normalize=True,
        deduplicate=not args.no_dedup,
    )

    parser = StatementParser(options)

    # Process files
    success_count = 0
    error_count = 0
    results = []

    for file_pattern in args.files:
        # Expand glob patterns
        p = Path(file_pattern)
        if p.is_absolute():
            # Absolute path, just use it directly
            files = [p] if p.exists() else []
        else:
            # Relative path, try glob first
            files = list(Path('.').glob(file_pattern))
            if not files:
                files = [p]

        for filepath in files:
            if not filepath.exists():
                if not args.quiet:
                    print(f"Error: File not found: {filepath}")
                error_count += 1
                continue

            success, result = process_file(filepath, parser, options, args.verbose)

            if success:
                success_count += 1
                results.append((filepath, result))

                # Print summary
                if not args.quiet:
                    summary = result.get_summary()
                    print(f"✓ {filepath.name}: {summary['total_transactions']} transactions")
                    print(f"  Type: {summary['statement_type']}, "
                          f" Credits: ₹{summary['total_credits']:,.2f}, "
                          f" Debits: ₹{summary['total_debits']:,.2f}")
                    print(f"  Output: {args.output_dir}/{filepath.stem}_parsed.{args.format}")
            else:
                error_count += 1
                if not args.quiet:
                    print(f"✗ {filepath.name}: {result}")

    # Final summary
    if not args.quiet and results:
        print(f"\nProcessed {success_count} file(s) successfully")
        if error_count > 0:
            print(f"Encountered {error_count} error(s)")

    return 0 if error_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
