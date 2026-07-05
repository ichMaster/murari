"""murari — command-line entry point (`python -m murari` / `murari`).

The commands (new / open / run) land in MUR-011 (the style engine). This is a placeholder
so the package installs and the entry point resolves.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Placeholder CLI — the style engine and commands arrive in MUR-011 (v0.1)."""
    print("murari: CLI not implemented yet (see MUR-011).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
