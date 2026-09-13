import csv
from pathlib import Path
import sys
import zipfile

import pytest
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend' / 'shared'))
import file_parser
from file_writer import FileWriter


@pytest.mark.parametrize('file_type', ['csv', 'xlsx'])
def test_headers_and_values_never_become_formulas(tmp_path, file_type):
    target = tmp_path / f'output.{file_type}'
    FileWriter().write(['=header', 'comment'], [{'=header': '+data', 'comment': 'original'}], str(target), file_type)
    if file_type == 'csv':
        with target.open(newline='') as source:
            rows = list(csv.reader(source))
    else:
        book = load_workbook(target, data_only=False)
        rows = list(book.active.values)
        assert all(cell.data_type != 'f' for row in book.active for cell in row)
        book.close()
    assert list(rows[0]) == ["'=header", 'comment']
    assert list(rows[1]) == ["'+data", 'original']


def test_duplicate_headers_reject_silent_data_loss(tmp_path):
    source = tmp_path / 'comments.csv'
    source.write_text('comment,comment\none,two\n')
    with pytest.raises(ValueError, match='unique'):
        file_parser.FileParser().parse(str(source), 'csv')


def test_expanded_workbook_limit_checked_before_openpyxl(tmp_path, monkeypatch):
    source = tmp_path / 'comments.xlsx'
    with zipfile.ZipFile(source, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('oversized.xml', 'a' * 1024)
    monkeypatch.setattr(file_parser, 'MAX_EXPANDED_BYTES', 100)
    with pytest.raises(ValueError, match='expanded size'):
        file_parser.FileParser().parse(str(source), 'xlsx')


def test_csv_row_limit_checked_during_parsing(tmp_path, monkeypatch):
    source = tmp_path / 'comments.csv'
    source.write_text('comment\none\ntwo\n')
    monkeypatch.setattr(file_parser, 'MAX_ROWS', 1)
    with pytest.raises(ValueError, match='row or cell'):
        file_parser.FileParser().parse(str(source), 'csv')
