"""File writer module for CSV and XLSX files."""

import csv
from typing import List, Dict
from openpyxl import Workbook


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
        """
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=headers, quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()
            writer.writerows(rows)
    
    def _write_xlsx(self, headers: List[str], rows: List[Dict[str, str]], 
                    output_path: str) -> None:
        """
        Write XLSX file using openpyxl.
        
        Creates a new workbook with a single worksheet containing
        the headers and data rows. Empty strings are preserved as empty cells.
        """
        workbook = Workbook()
        worksheet = workbook.active
        
        # Write headers
        worksheet.append(headers)
        
        # Write data rows
        for row in rows:
            # Extract values in the same order as headers
            # Keep empty strings as empty strings (they'll be stored as empty cells)
            row_values = [row.get(header, '') for header in headers]
            worksheet.append(row_values)
        
        # Save workbook
        workbook.save(output_path)
