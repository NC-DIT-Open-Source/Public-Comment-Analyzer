"""Dashboard summaries retain the user's selected source-column boundary."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def test_dashboard_does_not_send_unselected_source_metadata():
    path = Path(__file__).parents[1] / 'backend/dashboard_generator/handler.py'
    spec = importlib.util.spec_from_file_location('dashboard_privacy_test', path)
    handler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(handler)
    parsed = SimpleNamespace(row_count=1, headers=['comment', 'private_metadata', 'Summary'], rows=[
        {'comment': 'Selected comment', 'private_metadata': 'never send this value', 'Summary': 'Draft summary'}])
    result = handler._build_data_summary(parsed, [{'name': 'Summary'}], 'comment')
    assert 'Selected comment' in result and 'Draft summary' in result
    assert 'private_metadata' not in result and 'never send this value' not in result
    assert parsed.rows[0]['private_metadata'] == 'never send this value'
