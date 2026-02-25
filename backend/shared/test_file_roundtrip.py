"""Integration tests for FileParser and FileWriter roundtrip."""

import os
import tempfile
import pytest

from file_parser import FileParser
from file_writer import FileWriter


class TestFileRoundtrip:
    """Test that data can be parsed and written back correctly."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = FileParser()
        self.writer = FileWriter()
        self.temp_dir = tempfile.mkdtemp()
    
    def test_csv_roundtrip(self):
        """Test parsing CSV and writing it back preserves data."""
        # Create original CSV
        original_path = os.path.join(self.temp_dir, 'original.csv')
        import csv
        with open(original_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Name', 'Age', 'City'])
            writer.writerow(['Alice', '30', 'New York'])
            writer.writerow(['Bob', '25', 'Los Angeles'])
        
        # Parse the file
        parsed = self.parser.parse(original_path, 'csv')
        
        # Write it back
        output_path = os.path.join(self.temp_dir, 'output.csv')
        self.writer.write(parsed.headers, parsed.rows, output_path, 'csv')
        
        # Parse the output
        reparsed = self.parser.parse(output_path, 'csv')
        
        # Verify data is identical
        assert reparsed.headers == parsed.headers
        assert reparsed.row_count == parsed.row_count
        assert reparsed.rows == parsed.rows
    
    def test_xlsx_roundtrip(self):
        """Test parsing XLSX and writing it back preserves data."""
        # Create original XLSX
        from openpyxl import Workbook
        original_path = os.path.join(self.temp_dir, 'original.xlsx')
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(['Name', 'Age', 'City'])
        worksheet.append(['Alice', 30, 'New York'])
        worksheet.append(['Bob', 25, 'Los Angeles'])
        workbook.save(original_path)
        
        # Parse the file
        parsed = self.parser.parse(original_path, 'xlsx')
        
        # Write it back
        output_path = os.path.join(self.temp_dir, 'output.xlsx')
        self.writer.write(parsed.headers, parsed.rows, output_path, 'xlsx')
        
        # Parse the output
        reparsed = self.parser.parse(output_path, 'xlsx')
        
        # Verify data is identical
        assert reparsed.headers == parsed.headers
        assert reparsed.row_count == parsed.row_count
        assert reparsed.rows == parsed.rows
    
    def test_csv_with_special_characters_roundtrip(self):
        """Test CSV with special characters survives roundtrip."""
        import csv
        original_path = os.path.join(self.temp_dir, 'special.csv')
        with open(original_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Comment', 'Rating'])
            writer.writerow(['This has "quotes" in it', '5'])
            writer.writerow(['This has, commas', '4'])
            writer.writerow(['This has\nnewlines', '3'])
        
        # Parse, write, and reparse
        parsed = self.parser.parse(original_path, 'csv')
        output_path = os.path.join(self.temp_dir, 'special_output.csv')
        self.writer.write(parsed.headers, parsed.rows, output_path, 'csv')
        reparsed = self.parser.parse(output_path, 'csv')
        
        # Verify special characters preserved
        assert reparsed.rows[0]['Comment'] == 'This has "quotes" in it'
        assert reparsed.rows[1]['Comment'] == 'This has, commas'
        assert reparsed.rows[2]['Comment'] == 'This has\nnewlines'
    
    def test_format_preservation(self):
        """Test that input format is preserved in output (Requirement 5.1)."""
        import csv
        from openpyxl import Workbook
        
        # Test CSV -> CSV
        csv_path = os.path.join(self.temp_dir, 'test.csv')
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Name'])
            writer.writerow(['Test'])
        
        parsed_csv = self.parser.parse(csv_path, 'csv')
        output_csv = os.path.join(self.temp_dir, 'output.csv')
        self.writer.write(parsed_csv.headers, parsed_csv.rows, output_csv, 'csv')
        
        # Verify CSV can be parsed
        reparsed_csv = self.parser.parse(output_csv, 'csv')
        assert reparsed_csv.headers == ['Name']
        
        # Test XLSX -> XLSX
        xlsx_path = os.path.join(self.temp_dir, 'test.xlsx')
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(['Name'])
        worksheet.append(['Test'])
        workbook.save(xlsx_path)
        
        parsed_xlsx = self.parser.parse(xlsx_path, 'xlsx')
        output_xlsx = os.path.join(self.temp_dir, 'output.xlsx')
        self.writer.write(parsed_xlsx.headers, parsed_xlsx.rows, output_xlsx, 'xlsx')
        
        # Verify XLSX can be parsed
        reparsed_xlsx = self.parser.parse(output_xlsx, 'xlsx')
        assert reparsed_xlsx.headers == ['Name']
    
    def test_augmented_data_roundtrip(self):
        """Test that original data plus new columns can be written (Requirement 5.2)."""
        import csv
        
        # Create original CSV
        original_path = os.path.join(self.temp_dir, 'original.csv')
        with open(original_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Comment'])
            writer.writerow(['This is a comment'])
        
        # Parse the file
        parsed = self.parser.parse(original_path, 'csv')
        
        # Add analysis columns
        augmented_headers = parsed.headers + ['Sentiment', 'Category']
        augmented_rows = []
        for row in parsed.rows:
            augmented_row = row.copy()
            augmented_row['Sentiment'] = 'positive'
            augmented_row['Category'] = 'support'
            augmented_rows.append(augmented_row)
        
        # Write augmented data
        output_path = os.path.join(self.temp_dir, 'augmented.csv')
        self.writer.write(augmented_headers, augmented_rows, output_path, 'csv')
        
        # Parse and verify
        reparsed = self.parser.parse(output_path, 'csv')
        assert reparsed.headers == ['Comment', 'Sentiment', 'Category']
        assert reparsed.rows[0]['Comment'] == 'This is a comment'
        assert reparsed.rows[0]['Sentiment'] == 'positive'
        assert reparsed.rows[0]['Category'] == 'support'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
