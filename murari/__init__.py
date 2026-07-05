"""murari — a role-playing brainstorm tool.

A dedicated agent plays six roles (generate/evaluate/deepen/oppose/mutate/weave) over a
shared session state, sequenced by styles; the human is a participant, not a spectator.
See the specs under `spec/` for the design.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["__version__"]


def _read_version() -> str:
    """Version — single source of truth is the root VERSION file."""
    try:
        return (
            (Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip()
        )
    except OSError:
        return "0.0.0"


__version__ = _read_version()
