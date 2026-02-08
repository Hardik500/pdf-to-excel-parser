"""
PDF extraction utilities for handling scanned and image-based PDFs.

This module provides enhanced PDF text extraction with:
1. Standard text extraction using pdfplumber
2. Image-based extraction fallback for scanned documents
3. OCR support for non-selectable text
"""

import os
import tempfile
from typing import Optional, List, Dict, Any


def extract_text_from_pdf(filepath: str) -> str:
    """
    Extract text from a PDF file using multiple strategies.

    This function tries multiple extraction methods:
    1. Standard pdfplumber text extraction
    2. Image-based extraction with OCR for scanned PDFs

    Args:
        filepath: Path to the PDF file

    Returns:
        Extracted text from the PDF
    """
    try:
        # Try standard extraction first (fastest)
        text = _extract_with_pdfplumber(filepath)
        if text and len(text.strip()) > 100:
            return text

        # Fallback: Try image-based extraction
        text = _extract_with_images(filepath)
        if text and len(text.strip()) > 100:
            return text

        return text or ""

    except Exception as e:
        return f"Error extracting text: {str(e)}"


def _extract_with_pdfplumber(filepath: str) -> str:
    """Extract text using pdfplumber's standard method."""
    try:
        import pdfplumber

        text_parts = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)

        return "\n\n".join(text_parts)

    except ImportError:
        return ""
    except Exception:
        return ""


def _extract_with_images(filepath: str) -> str:
    """
    Extract text from PDF images using OCR.

    This is a fallback for scanned PDFs where text isn't selectable.
    Requires: pdf2image, pytesseract
    """
    try:
        import pdf2image
        import pytesseract
        from PIL import Image

        # Convert PDF to images
        images = pdf2image.convert_from_path(filepath, dpi=200)

        text_parts = []
        for i, image in enumerate(images):
            # Perform OCR
            text = pytesseract.image_to_string(image)
            text_parts.append(f"--- Page {i + 1} ---\n{text}")

        return "\n\n".join(text_parts)

    except ImportError:
        # Required packages not installed
        return ""
    except Exception:
        return ""


def extract_text_with_tables(filepath: str) -> Dict[str, Any]:
    """
    Extract both text and tables from a PDF.

    Args:
        filepath: Path to the PDF file

    Returns:
        Dictionary with 'text' and 'tables' keys
    """
    result = {
        'text': '',
        'tables': [],
        'method': 'standard'
    }

    try:
        import pdfplumber

        text_parts = []
        all_tables = []

        with pdfplumber.open(filepath) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                # Extract text
                page_text = page.extract_text() or ""
                if page_text:
                    text_parts.append(f"--- Page {page_num} ---\n{page_text}")

                # Extract tables
                tables = page.extract_tables()
                for table in tables:
                    all_tables.append({
                        'page': page_num,
                        'rows': len(table),
                        'data': table
                    })

        result['text'] = "\n\n".join(text_parts)
        result['tables'] = all_tables
        result['method'] = 'pdfplumber'

    except ImportError:
        result['text'] = "pdfplumber not installed"
    except Exception as e:
        result['text'] = f"Error: {str(e)}"

    return result


def is_scanned_pdf(filepath: str, threshold: float = 0.5) -> bool:
    """
    Detect if a PDF is scanned (image-based) or native text.

    Args:
        filepath: Path to the PDF file
        threshold: Text length ratio threshold (default 0.5)

    Returns:
        True if likely scanned, False if likely native text
    """
    try:
        import pdfplumber

        total_chars = 0
        total_pages = 0

        with pdfplumber.open(filepath) as pdf:
            total_pages = len(pdf.pages)

            for page in pdf.pages:
                page_text = page.extract_text() or ""
                total_chars += len(page_text.strip())

        # If less than 50 characters per page on average, likely scanned
        avg_chars_per_page = total_chars / total_pages if total_pages > 0 else 0

        return avg_chars_per_page < threshold * 100

    except Exception:
        return False


def clean_extracted_text(text: str) -> str:
    """
    Clean and normalize extracted text.

    - Remove excessive whitespace
    - Fix common OCR errors
    - Normalize line breaks

    Args:
        text: Raw extracted text

    Returns:
        Cleaned text
    """
    if not text:
        return ""

    import re

    # Fix common OCR errors
    replacements = {
        r'\s+': ' ',  # Multiple spaces to single
        r'(\d)\s+(\d)': r'\1\2',  # Remove spaces between digits
        r'(\d)\s+(\.\d)': r'\1\2',  # Remove spaces before decimal
    }

    cleaned = text

    for pattern, replacement in replacements.items():
        cleaned = re.sub(pattern, replacement, cleaned)

    # Normalize line breaks
    cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)
    cleaned = cleaned.strip()

    return cleaned


def validate_pdf(filepath: str) -> Dict[str, Any]:
    """
    Validate a PDF file before extraction.

    Args:
        filepath: Path to the PDF file

    Returns:
        Dictionary with validation results
    """
    result = {
        'valid': False,
        'error': None,
        'pages': 0,
        'file_size': 0,
        'is_encrypted': False,
    }

    try:
        import PyPDF2

        with open(filepath, 'rb') as f:
            # Get file size
            result['file_size'] = os.path.getsize(filepath)

            # Try to read with PyPDF2
            reader = PyPDF2.PdfReader(f)

            result['pages'] = len(reader.pages)
            result['is_encrypted'] = reader.is_encrypted

            if reader.is_encrypted:
                result['error'] = "PDF is encrypted"
            elif len(reader.pages) == 0:
                result['error'] = "PDF has no pages"
            else:
                result['valid'] = True

    except ImportError:
        result['error'] = "PyPDF2 not installed"
    except Exception as e:
        result['error'] = str(e)

    return result
