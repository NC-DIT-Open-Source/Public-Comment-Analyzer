"""File writer module for CSV and XLSX files."""

import csv
from typing import List, Dict
from openpyxl import Workbook
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Spreadsheet apps interpret cells starting with these as formulas.
# AI-generated content is untrusted, so neutralize by prefixing with a single quote.
_FORMULA_TRIGGERS = ('=', '+', '-', '@', '\t', '\r')


def _escape_formula(value):
    """Prefix cell values that look like formulas with ' to prevent execution."""
    if isinstance(value, str) and value and value[0] in _FORMULA_TRIGGERS:
        return "'" + value
    return value


class FileWriter:
    """Writer for CSV and XLSX files."""
    
    def write(self, headers: List[str], rows: List[Dict[str, str]], 
              output_path: str, file_type: str) -> None:
        """
        Write data to CSV or XLSX file.
        
        Args:
            headers: Column headers
            rows: Data rows as dictionaries
            output_path: Path to output file
            file_type: File type ('csv' or 'xlsx')
        """
        if file_type.lower() == 'csv':
            self._write_csv(headers, rows, output_path)
        elif file_type.lower() in ['xlsx', 'xls']:
            self._write_xlsx(headers, rows, output_path)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
    
    def _write_csv(self, headers: List[str], rows: List[Dict[str, str]], 
                   output_path: str) -> None:
        """
        Write CSV file with proper escaping.
        
        Uses Python's csv.DictWriter which automatically handles:
        - Quoting fields containing commas, quotes, or newlines
        - Escaping quotes by doubling them
        - Proper line endings
        
        Raises:
            IOError: If file cannot be written
            ValueError: If headers or rows are invalid
        """
        try:
            if not headers:
                raise ValueError("Cannot write CSV with empty headers")
            
            with open(output_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=headers, quoting=csv.QUOTE_MINIMAL)
                writer.writeheader()
                
                for row_num, row in enumerate(rows, start=2):  # Start at 2 (after header)
                    try:
                        writer.writerow({k: _escape_formula(v) for k, v in row.items()})
                    except Exception as e:
                        logger.warning(f"Error writing CSV row {row_num}: {str(e)}")
                        # Continue with other rows
                        continue
        
        except IOError as e:
            logger.error(f"Failed to write CSV file: {str(e)}")
            raise IOError(f"Cannot write output file: {str(e)}") from e
        
        except Exception as e:
            logger.error(f"Unexpected error writing CSV: {str(e)}")
            raise
    
    def _write_xlsx(self, headers: List[str], rows: List[Dict[str, str]], 
                    output_path: str) -> None:
        """
        Write XLSX file using openpyxl.
        
        Creates a new workbook with a single worksheet containing
        the headers and data rows. Empty strings are preserved as empty cells.
        
        Raises:
            IOError: If file cannot be written
            ValueError: If headers or rows are invalid
        """
        try:
            if not headers:
                raise ValueError("Cannot write XLSX with empty headers")
            
            workbook = Workbook()
            worksheet = workbook.active
            
            # Write headers
            worksheet.append(headers)
            
            # Write data rows
            for row_num, row in enumerate(rows, start=2):  # Start at 2 (after header)
                try:
                    # Extract values in the same order as headers
                    # Keep empty strings as empty strings (they'll be stored as empty cells)
                    row_values = [_escape_formula(row.get(header, '')) for header in headers]
                    worksheet.append(row_values)
                except Exception as e:
                    logger.warning(f"Error writing XLSX row {row_num}: {str(e)}")
                    # Continue with other rows
                    continue
            
            # Save workbook
            workbook.save(output_path)
        
        except IOError as e:
            logger.error(f"Failed to write XLSX file: {str(e)}")
            raise IOError(f"Cannot write output file: {str(e)}") from e
        
        except Exception as e:
            logger.error(f"Unexpected error writing XLSX: {str(e)}")
            raise
