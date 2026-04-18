"""Shared import shim.

helper.py lives at skills/imessage-review/bin/helper.py, which is not on
sys.path by default. Each test module imports this shim first to load
helper as a module object.

We deliberately do NOT rely on editable installs, pytest plugins, or
other magic — the tests should run with nothing more than a stock
Python 3 interpreter, via either:

    python3 -m unittest discover -s tests -v
    python3 -m unittest tests.test_redaction -v
    python3 tests/test_redaction.py

Works regardless of whether `tests` was imported as a package or each
test file was run as a top-level script.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_BIN = _REPO_ROOT / "skills" / "imessage-review" / "bin"
_HELPER_PY = _BIN / "helper.py"

if str(_BIN) not in sys.path:
    sys.path.insert(0, str(_BIN))

# Load helper.py by absolute path so we don't rely on import-path heuristics.
# Module-level code runs; main() is guarded by `if __name__ == "__main__":`
# so this is side-effect-free beyond importing stdlib modules.
if "helper" in sys.modules:
    helper = sys.modules["helper"]
else:
    spec = importlib.util.spec_from_file_location("helper", _HELPER_PY)
    helper = importlib.util.module_from_spec(spec)
    sys.modules["helper"] = helper
    spec.loader.exec_module(helper)
