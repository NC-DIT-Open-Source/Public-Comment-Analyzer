"""Large generated results must be summarized without oversized or lost evidence."""
import html
import re

import pytest

import handler
from file_parser import ParsedFile
from inference import InferenceLimitError


def make_file(rows, columns):
    return ParsedFile(headers=[column['name'] for column in columns], rows=rows, row_count=len(rows))


def capture_model(monkeypatch, result='Draft themes across the supplied evidence.'):
    calls = []
    def summarize(prompt):
        assert len(prompt) <= handler.prompt_character_limit()
        calls.append(prompt)
        return result
    monkeypatch.setattr(handler, '_call_chunk_model', summarize)
    return calls


def test_150_long_responses_use_size_aware_chunks_and_include_every_response(monkeypatch):
    monkeypatch.setenv('LLM_MAX_PROMPT_CHARS', '200000')
    columns = [{'name': 'Summary', 'instructions': 'Summarize all viewpoints.'}]
    rows = [{'Summary': f'UNIQUE_RESPONSE_{index:04d} ' + ('Evidence <&> ' * 200)} for index in range(150)]
    calls = capture_model(monkeypatch)
    formatted = handler._format_data_for_analysis(make_file(rows, columns), columns)
    prompt = handler._construct_aggregate_prompt(formatted, columns)
    assert len(prompt) <= 200000
    assert len(calls) >= 2
    source_calls = '\n'.join(html.unescape(call) for call in calls)
    for index in range(150):
        assert source_calls.count(f'UNIQUE_RESPONSE_{index:04d}') == 1
    assert '150 total responses' in formatted
    assert 'Sample rows omitted for prompt size:' in formatted


def test_twenty_columns_share_one_global_prompt_allocation(monkeypatch):
    monkeypatch.setenv('LLM_MAX_PROMPT_CHARS', '12000')
    columns = [{'name': f'Topic {i}', 'instructions': 'Summarize.'} for i in range(20)]
    rows = [{col['name']: f"{col['name']} response {row} " + 'Long text <&> ' * 60 for col in columns}
            for row in range(150)]
    calls = capture_model(monkeypatch, 'Draft: majority and minority views need source verification.')
    # A valid small configured prompt can be too small for 20 column allocations;
    # rejecting before any model call is preferable to truncating entire columns.
    with pytest.raises(InferenceLimitError, match='exact distributions'):
        handler._format_data_for_analysis(make_file(rows, columns), columns)
    assert calls == []
    monkeypatch.setenv('LLM_MAX_PROMPT_CHARS', '20000')
    formatted = handler._format_data_for_analysis(make_file(rows, columns), columns)
    assert len(handler._construct_aggregate_prompt(formatted, columns)) <= 20000
    for column in columns:
        assert column['name'] + ' — 150 total responses' in formatted
    assert len(calls) >= 20
    assert 'Sample rows omitted for prompt size: 10.' in formatted


def test_oversized_single_response_is_fragmented_without_dropping_characters(monkeypatch):
    monkeypatch.setenv('LLM_MAX_PROMPT_CHARS', '4000')
    value = 'START_MARKER' + '<&>' * 3000 + 'END_MARKER'
    calls = capture_model(monkeypatch, 'Draft summary.')
    output = handler._summarize_open_text_chunks('Summary', [value], 'Summarize.', max_encoded_chars=700)
    bodies = [html.unescape(re.search(r'<comment_data>\n(.*?)\n</comment_data>', prompt, re.S).group(1))
              for prompt in calls]
    fragments = [re.sub(r'^Evidence item 1, fragment \d+:\n', '', body) for body in bodies]
    assert ''.join(fragments) == 'Response 1: ' + value
    assert len(calls) > 1 and '1 total responses' in output


def test_large_map_outputs_get_bounded_reduction_and_every_draft_reaches_reduce(monkeypatch):
    monkeypatch.setenv('LLM_MAX_PROMPT_CHARS', '6000')
    calls = []
    map_outputs = []
    def summarize(prompt):
        assert len(prompt) <= 6000
        calls.append(prompt)
        if 'following source responses' in prompt:
            value = f'MAP_OUTPUT_{len(map_outputs)} ' + 'Evidence. ' * 50
            map_outputs.append(value)
            return value
        return 'Draft compressed themes.'
    monkeypatch.setattr(handler, '_call_chunk_model', summarize)
    result = handler._summarize_open_text_chunks('Summary', ['Original. ' * 100] * 25,
                                                 'Summarize.', max_encoded_chars=800)
    reductions = '\n'.join(prompt for prompt in calls if 'following unverified draft summaries' in prompt)
    assert reductions
    for index in range(len(map_outputs)):
        assert f'MAP_OUTPUT_{index} ' in reductions
    assert len(html.escape(result)) <= 800


def test_noncompressing_provider_fails_after_four_rounds_without_silent_cutoff(monkeypatch):
    monkeypatch.setenv('LLM_MAX_PROMPT_CHARS', '6000')
    calls = capture_model(monkeypatch, 'Repeated unhelpful prose. ' * 35)
    with pytest.raises(InferenceLimitError, match='four bounded reduction rounds'):
        handler._summarize_open_text_chunks('Summary', ['Long response. ' * 80],
                                            'Summarize.', max_encoded_chars=500)
    assert len(calls) == 1 + handler.MAX_REDUCTION_ROUNDS


def test_exact_distributions_survive_long_text_and_missing_samples(monkeypatch):
    monkeypatch.setenv('LLM_MAX_PROMPT_CHARS', '6000')
    columns = [{'name': 'Position', 'type': 'categorized', 'options': [{'value': 'For'}, {'value': 'Against'}]},
               {'name': 'Summary', 'instructions': 'Summarize.'}]
    rows = [{'Position': 'For' if index < 6 else ('Against' if index < 9 else ''),
             'Summary': 'Long data <&>. ' * 400} for index in range(10)]
    capture_model(monkeypatch)
    formatted = handler._format_data_for_analysis(make_file(rows, columns), columns)
    assert 'For: 6 (60.0%)' in formatted
    assert 'Against: 3 (30.0%)' in formatted
    assert '(unmatched/blank): 1 (10.0%)' in formatted
    assert 'Sample rows omitted for prompt size: 10.' in formatted
    assert len(handler._construct_aggregate_prompt(formatted, columns)) <= 6000


def test_limit_failure_propagates_without_replacing_complete_row_output(monkeypatch):
    def exhausted(_prompt):
        raise InferenceLimitError('Deployment budget reached.')
    monkeypatch.setattr(handler, '_call_chunk_model', exhausted)
    columns = [{'name': 'Summary', 'instructions': 'Summarize.'}]
    rows = [{'Summary': 'Long evidence. ' * 1000} for _ in range(150)]
    parsed = make_file(rows, columns)
    originals = [dict(row) for row in rows]
    with pytest.raises(InferenceLimitError, match='Deployment budget'):
        handler._format_data_for_analysis(parsed, columns)
    assert parsed.rows == originals


def test_final_prompt_never_silently_slices_evidence(monkeypatch):
    monkeypatch.setenv('LLM_MAX_PROMPT_CHARS', '1000000')
    data = 'Evidence. ' * 95000 + 'UNIQUE_END_OF_EVIDENCE'
    prompt = handler._construct_aggregate_prompt(data, [{'name': 'Summary', 'instructions': 'Summarize.'}])
    assert 'UNIQUE_END_OF_EVIDENCE' in prompt
    monkeypatch.setenv('LLM_MAX_PROMPT_CHARS', '200000')
    with pytest.raises(InferenceLimitError, match='prompt exceeds'):
        handler._construct_aggregate_prompt(data, [{'name': 'Summary', 'instructions': 'Summarize.'}])
