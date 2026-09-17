"""Puts the plugin repository on the import path, so tests import the plugin's
backend package as `backend` -- the same package the host imports under its own
name. The framework's `app.plugin_api` is on PYTHONPATH when publishing runs these."""
import sys
from pathlib import Path

_REPOSITORY = Path(__file__).resolve().parents[1]
if str(_REPOSITORY) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY))
