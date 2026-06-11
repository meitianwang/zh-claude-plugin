"""Individual, failure-isolated patch steps.

Each function performs one edit and raises ``PatchError`` on a recoverable
problem (e.g. an anchor that drifted in a new Claude version). The orchestrator
in cli.py catches ``PatchError`` per step, warns, and continues, so a single
drifted anchor degrades one feature instead of aborting the whole install.
"""

from __future__ import annotations


class PatchError(Exception):
    """A patch step could not be applied to this Claude version."""
