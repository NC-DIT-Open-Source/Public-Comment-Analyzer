"""Shared utilities for the portable application."""

from .file_parser import FileParser, ParsedFile
from .file_writer import FileWriter

__all__ = [
    'JobClient',
    'JobStatus',
    'FileParser',
    'ParsedFile',
    'FileWriter'
]


def __getattr__(name):
    if name in {'JobClient', 'JobStatus'}:
        from .job_client import JobClient, JobStatus
        return {'JobClient': JobClient, 'JobStatus': JobStatus}[name]
    raise AttributeError(name)
