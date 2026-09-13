import csv
from pathlib import Path
import sys
import zipfile

import pytest
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend' / 'shared'))
import file_parser
from file_writer import FileWriter, export_headers


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


@pytest.mark.parametrize('file_type', ['csv', 'xlsx'])
def test_generated_readback_restores_only_saved_header_mapping(tmp_path, file_type):
    target = tmp_path / f'result.{file_type}'
    headers = ['comment', '+Finding', "'literal"]
    FileWriter().write(headers, [{'comment': 'Original', '+Finding': 'Support', "'literal": 'Kept'}], str(target), file_type)
    parser = file_parser.FileParser()
    # Uploaded files retain their literal safe headers; only known generated
    # output may restore the exact schema saved with its job.
    assert parser.parse(str(target), file_type).headers == ['comment', "'+Finding", "'literal"]
    restored = parser.parse(str(target), file_type, generated=True, original_headers=headers)
    assert restored.headers == headers
    assert restored.rows[0]['+Finding'] == 'Support'
    assert restored.rows[0]["'literal"] == 'Kept'
    with pytest.raises(ValueError, match='saved job schema'):
        parser.parse(str(target), file_type, generated=True, original_headers=['different', '+Finding', "'literal"])


@pytest.mark.parametrize('file_type', ['csv', 'xlsx'])
def test_generated_limits_allow_output_overhead_but_remain_bounded(tmp_path, file_type, monkeypatch):
    target = tmp_path / f'result.{file_type}'
    headers = [f'c{i}' for i in range(file_parser.MAX_GENERATED_COLUMNS)]
    FileWriter().write(headers, [dict.fromkeys(headers, 'synthetic')], str(target), file_type)
    parser = file_parser.FileParser()
    with pytest.raises(ValueError, match='column limit'):
        parser.parse(str(target), file_type)
    assert len(parser.parse(str(target), file_type, generated=True).headers) == 1022
    monkeypatch.setattr(file_parser, 'MAX_GENERATED_COLUMNS', 1021)
    with pytest.raises(ValueError, match='column limit'):
        parser.parse(str(target), file_type, generated=True)


def test_ambiguous_formula_safe_headers_are_rejected_by_writer(tmp_path):
    with pytest.raises(ValueError, match='collide'):
        export_headers(['+Finding', "'+Finding"])
    with pytest.raises(ValueError, match='collide'):
        FileWriter().write(['+Finding', "'+Finding"], [], str(tmp_path / 'result.csv'), 'csv')


@pytest.mark.parametrize('file_type', ['csv', 'xlsx'])
def test_generated_cell_limits_do_not_widen_upload_limits(tmp_path, file_type, monkeypatch):
    target = tmp_path / f'result.{file_type}'
    FileWriter().write(['a', 'b'], [{'a': 'first', 'b': 'second'}] * 3, str(target), file_type)
    monkeypatch.setattr(file_parser, 'MAX_CELLS', 4)
    monkeypatch.setattr(file_parser, 'MAX_GENERATED_CELLS', 8)
    parser = file_parser.FileParser()
    with pytest.raises(ValueError, match='cell limit'):
        parser.parse(str(target), file_type)
    assert parser.parse(str(target), file_type, generated=True).row_count == 3
    monkeypatch.setattr(file_parser, 'MAX_GENERATED_CELLS', 4)
    with pytest.raises(ValueError, match='cell limit'):
        parser.parse(str(target), file_type, generated=True)


def test_generated_byte_limit_remains_bounded(tmp_path, monkeypatch):
    target = tmp_path / 'result.csv'
    target.write_text('comment\nsynthetic\n')
    monkeypatch.setattr(file_parser, 'MAX_FILE_BYTES', 1)
    parser = file_parser.FileParser()
    with pytest.raises(ValueError, match='100 MB'):
        parser.parse(str(target), 'csv')
    assert parser.parse(str(target), 'csv', generated=True).row_count == 1
    monkeypatch.setattr(file_parser, 'MAX_GENERATED_FILE_BYTES', 1)
    with pytest.raises(ValueError, match='generated result size'):
        parser.parse(str(target), 'csv', generated=True)


def test_generated_archive_limit_remains_bounded(tmp_path, monkeypatch):
    target = tmp_path / 'result.xlsx'
    FileWriter().write(['comment'], [{'comment': 'synthetic'}], str(target), 'xlsx')
    monkeypatch.setattr(file_parser, 'MAX_EXPANDED_BYTES', 1)
    parser = file_parser.FileParser()
    with pytest.raises(ValueError, match='expanded size'):
        parser.parse(str(target), 'xlsx')
    assert parser.parse(str(target), 'xlsx', generated=True).row_count == 1
    monkeypatch.setattr(file_parser, 'MAX_GENERATED_EXPANDED_BYTES', 1)
    with pytest.raises(ValueError, match='expanded size'):
        parser.parse(str(target), 'xlsx', generated=True)
