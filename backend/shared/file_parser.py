"""File parser module for CSV and XLSX files."""

import csv
import os
import zipfile
from typing import List, Dict
from dataclasses import dataclass
import chardet
from openpyxl import load_workbook
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_ROWS = 50_000
MAX_COLUMNS = 1_000
MAX_CELLS = 2_000_000


def _validate_headers(headers):
    if len(headers) > MAX_COLUMNS:
        raise ValueError('File exceeds the column limit')
    if len(set(headers)) != len(headers):
        raise ValueError('Column names must be unique to preserve all input data')


def _validate_archive(file_path):
    with zipfile.ZipFile(file_path) as archive:
        entries = archive.infolist()
        if len(entries) > 10_000 or sum(item.file_size for item in entries) > MAX_EXPANDED_BYTES:
            raise ValueError('Workbook exceeds the expanded size limit')
        if any(item.flag_bits & 1 for item in entries):
            raise ValueError('Encrypted workbooks are not supported')


@dataclass
class ParsedFile:
    """Represents a parsed file with headers and rows."""
    headers: List[str]
    rows: List[Dict[str, str]]
    row_count: int


class FileParser:
    """Parser for CSV and XLSX files."""
    
    def parse(self, file_path: str, file_type: str) -> ParsedFile:
        """
        Parse a CSV or XLSX file.
        
        Args:
            file_path: Path to the file
            file_type: File type ('csv' or 'xlsx')
            
        Returns:
            ParsedFile object with headers, rows, and row count
            
        Raises:
            ValueError: If file type is not supported
            FileNotFoundError: If file does not exist
        """
        if file_type.lower() not in {'csv', 'xlsx', 'xls'}:
            raise ValueError(f'Unsupported file type: {file_type}')
        if os.path.getsize(file_path) > MAX_FILE_BYTES:
            raise ValueError('File exceeds the 100 MB size limit')
        if file_type.lower() == 'csv':
            return self._parse_csv(file_path)
        elif file_type.lower() in ['xlsx', 'xls']:
            return self._parse_xlsx(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
    
    def _detect_encoding(self, file_path: str) -> str:
        """
        Detect file encoding using chardet.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Detected encoding string (e.g., 'utf-8', 'latin-1')
        """
        with open(file_path, 'rb') as f:
            raw_data = f.read(1024 * 1024)
            result = chardet.detect(raw_data)
            encoding = result['encoding']
            # Default to utf-8 if detection fails
            return encoding if encoding else 'utf-8'
    
    def _parse_csv(self, file_path: str) -> ParsedFile:
        """
        Parse CSV file with proper encoding detection.
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            ParsedFile object with headers, rows, and row count
            
        Raises:
            ValueError: If file is empty or has invalid format
            UnicodeDecodeError: If file encoding cannot be determined
        """
        # Try multiple encodings in order of preference
        encodings_to_try = []
        
        # First, try chardet detection
        detected_encoding = self._detect_encoding(file_path)
        if detected_encoding:
            encodings_to_try.append(detected_encoding)
        
        # Add common fallback encodings
        fallback_encodings = ['utf-8', 'latin-1', 'windows-1252', 'iso-8859-1', 'cp1252']
        for enc in fallback_encodings:
            if enc not in encodings_to_try:
                encodings_to_try.append(enc)
        
        last_error = None
        
        for encoding in encodings_to_try:
            try:
                headers = []
                rows = []
                
                with open(file_path, 'r', encoding=encoding, newline='') as f:
                    reader = csv.DictReader(f)
                    headers = reader.fieldnames if reader.fieldnames else []
                    
                    if not headers:
                        raise ValueError("CSV file has no headers")
                    _validate_headers(headers)
                    
                    for row_num, row in enumerate(reader, start=2):
                        if row_num > MAX_ROWS + 1 or (row_num - 1) * len(headers) > MAX_CELLS:
                            raise ValueError('File exceeds the row or cell limit')
                        if None in row:
                            raise ValueError('A data row has more cells than the header')
                        try:
                            # Convert all values to strings and handle None values
                            row_dict = {key: (str(value) if value is not None else '') 
                                       for key, value in row.items()}
                            rows.append(row_dict)
                        except Exception as e:
                            logger.warning(f"Error parsing CSV row {row_num}: {str(e)}")
                            # Continue with other rows
                            continue
                
                if not rows:
                    logger.warning("CSV file has no data rows")
                
                logger.info(f"Successfully parsed CSV with encoding: {encoding}")
                return ParsedFile(
                    headers=headers,
                    rows=rows,
                    row_count=len(rows)
                )
            
            except UnicodeDecodeError as e:
                logger.debug(f"Failed to decode CSV file with encoding {encoding}: {str(e)}")
                last_error = e
                continue  # Try next encoding
            
            except csv.Error as e:
                logger.error(f"CSV parsing error with encoding {encoding}: {str(e)}")
                raise ValueError(f"Invalid CSV format: {str(e)}") from e
            
            except Exception as e:
                logger.error(f"Unexpected error parsing CSV with encoding {encoding}: {str(e)}")
                raise
        
        # If we get here, all encodings failed
        logger.error("Failed to decode CSV file with any supported encoding")
        raise ValueError(f"File encoding not supported. Tried: {', '.join(encodings_to_try)}. Please ensure file is properly encoded.") from last_error
    
    def _parse_xlsx(self, file_path: str) -> ParsedFile:
        """
        Parse XLSX file (first worksheet only).
        
        Args:
            file_path: Path to the XLSX file
            
        Returns:
            ParsedFile object with headers, rows, and row count
            
        Raises:
            ValueError: If file is empty, corrupted, or has invalid format
        """
        try:
            # Load workbook and get first worksheet
            _validate_archive(file_path)
            workbook = load_workbook(filename=file_path, read_only=True, data_only=True)
            
            if not workbook.worksheets:
                raise ValueError("XLSX file has no worksheets")
            
            worksheet = workbook.worksheets[0]
            
            # Get all rows as a list
            all_rows = []
            try:
                for row in worksheet.iter_rows(values_only=True):
                    if len(all_rows) > MAX_ROWS or len(row) > MAX_COLUMNS:
                        raise ValueError('Workbook exceeds the row or column limit')
                    if (len(all_rows) + 1) * len(row) > MAX_CELLS:
                        raise ValueError('Workbook exceeds the cell limit')
                    all_rows.append(row)
            finally:
                workbook.close()
            
            if not all_rows:
                workbook.close()
                raise ValueError("XLSX file has no data")
            
            # First row is headers
            headers = [str(cell) if cell is not None else '' for cell in all_rows[0]]
            _validate_headers(headers)
            
            if not any(headers):  # All headers are empty
                workbook.close()
                raise ValueError("XLSX file has no headers")
            
            # Remaining rows are data
            rows = []
            for row_num, row_values in enumerate(all_rows[1:], start=2):  # Start at 2 (after header)
                try:
                    # Create dictionary mapping headers to values
                    row_dict = {}
                    for i, header in enumerate(headers):
                        # Get value at index i, or empty string if index out of range
                        value = row_values[i] if i < len(row_values) else None
                        row_dict[header] = str(value) if value is not None else ''
                    rows.append(row_dict)
                except Exception as e:
                    logger.warning(f"Error parsing XLSX row {row_num}: {str(e)}")
                    # Continue with other rows
                    continue
            
            workbook.close()
            
            if not rows:
                logger.warning("XLSX file has no data rows")
            
            return ParsedFile(
                headers=headers,
                rows=rows,
                row_count=len(rows)
            )
        
        except Exception as e:
            logger.error(f"Failed to parse XLSX file: {str(e)}")
            if 'workbook' in locals():
                try:
                    workbook.close()
                except Exception:
                    pass  # Best-effort cleanup; original error will be re-raised
            
            # Provide user-friendly error message
            if 'corrupt' in str(e).lower() or 'invalid' in str(e).lower():
                raise ValueError(f"XLSX file is corrupted or invalid: {str(e)}") from e
            else:
                raise
