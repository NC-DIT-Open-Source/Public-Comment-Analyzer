"""Provider-neutral convenience methods for the stable job record schema."""

from datetime import datetime, timedelta, timezone
if __package__:
    from .runtime import get_job_store
else:
    from runtime import get_job_store


class JobStatus:
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'


def _now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


class JobClient:
    def __init__(self, store=None):
        self.store = store or get_job_store()

    def create_job(self, job_id, file_id, total_rows, analysis_columns, input_file_key, file_type):
        now = _now()
        record = {
            'jobId': job_id, 'fileId': file_id, 'status': JobStatus.PENDING,
            'totalRows': total_rows, 'completedRows': 0, 'analysisColumns': analysis_columns,
            'inputFileKey': input_file_key, 'fileType': file_type, 'outputFileKey': '',
            'aggregateAnalysis': '', 'createdAt': now, 'updatedAt': now, 'errors': [],
            'ttl': int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp()),
        }
        self.store.put(record)
        return record

    def get_job(self, job_id):
        return self.store.get(job_id)

    def update_job_status(self, job_id, status, completed_rows=None, errors=None):
        fields = {'status': status, 'updatedAt': _now()}
        if completed_rows is not None:
            fields['completedRows'] = completed_rows
        if errors is not None:
            fields['errors'] = errors
        self.store.update(job_id, fields)

    def update_job_progress(self, job_id, completed_rows):
        self.store.update(job_id, {'completedRows': completed_rows, 'updatedAt': _now()})

    def update_output_file(self, job_id, output_file_key):
        self.store.update(job_id, {'outputFileKey': output_file_key, 'updatedAt': _now()})

    def update_aggregate_analysis(self, job_id, aggregate_analysis):
        self.store.update(job_id, {'aggregateAnalysis': aggregate_analysis, 'updatedAt': _now()})

    def add_job_error(self, job_id, error_message, row_number=None):
        record = {'message': error_message, 'timestamp': _now()}
        if row_number is not None:
            record['rowNumber'] = row_number
        self.store.append_error(job_id, record)

    def increment_completed_rows(self, job_id, increment=1):
        self.store.increment(job_id, 'completedRows', increment)

    def get_job_progress(self, job_id):
        item = self.store.get(job_id)
        if not item:
            return {'status': 'not_found', 'progress': 0, 'completedRows': 0, 'totalRows': 0}
        total = item.get('totalRows', 0)
        completed = item.get('completedRows', 0)
        return {'jobId': item['jobId'], 'status': item['status'],
                'progress': round(completed / total * 100, 2) if total else 0,
                'completedRows': completed, 'totalRows': total, 'errors': item.get('errors', [])}
