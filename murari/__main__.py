"""Enable `python -m murari` — delegates to the CLI entry point (`murari.cli:main`)."""

from __future__ import annotations

from murari.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
