"""Make the repo root (holding the `murari` package) importable in tests.

`python -m pytest` already puts the cwd on sys.path; this keeps `import murari`
working under a bare `pytest` too.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
