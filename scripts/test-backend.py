"""Run each legacy handler suite in isolation, then portable integration contracts."""
from pathlib import Path
import os
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
environment = dict(os.environ, AWS_EC2_METADATA_DISABLED='true')
failed = False
for directory in [*sorted((root / 'backend').glob('*')), root / 'tests']:
    if directory.is_dir() and any(directory.glob('test_*.py')):
        print(f'Testing {directory.relative_to(root)}', flush=True)
        result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--tb=short'], cwd=directory, env=environment)
        failed = failed or result.returncode != 0
raise SystemExit(1 if failed else 0)
