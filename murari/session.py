"""murari — session directories.

Create a fresh timestamped session (`input/TOPIC.md` + `output/artifacts/`), reopen an
existing one to continue its document, list sessions, and snapshot/restore the output state
files so a failed run leaves the workspace exactly as it was.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from pathlib import Path

from murari.config import Config
from murari.ledger import Ledger, parse_ledger

# The agent-maintained state files (not the raw run artifacts).
_STATE_FILES = ("LEDGER.md", "SOURCES.md", "IDEAS.md", "DOCUMENT.md")


class SessionError(ValueError):
    """Raised when a directory is not a valid session or cannot be created."""


def slugify(name: str) -> str:
    """ASCII slug: lowercase, spaces→-, keep [a-z0-9-]. Non-ASCII names slug to '' (the
    caller then falls back to a timestamp-only directory), matching new-session.sh."""
    s = name.lower().replace(" ", "-")
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s


def _stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


@dataclass(frozen=True)
class Session:
    path: Path

    @property
    def input_dir(self) -> Path:
        return self.path / "input"

    @property
    def output_dir(self) -> Path:
        return self.path / "output"

    @property
    def artifacts_dir(self) -> Path:
        return self.output_dir / "artifacts"

    @property
    def topic_file(self) -> Path:
        return self.input_dir / "TOPIC.md"

    @property
    def ledger_file(self) -> Path:
        return self.output_dir / "LEDGER.md"

    @property
    def document_file(self) -> Path:
        return self.output_dir / "DOCUMENT.md"

    def read_topic(self) -> str:
        return self.topic_file.read_text(encoding="utf-8")

    def read_ledger(self) -> Ledger | None:
        """Parsed LEDGER (or None if the agent hasn't written one yet). Raises LedgerError on
        a malformed ledger."""
        if not self.ledger_file.exists():
            return None
        return parse_ledger(self.ledger_file.read_text(encoding="utf-8"))

    def read_document(self) -> str | None:
        return (
            self.document_file.read_text(encoding="utf-8") if self.document_file.exists() else None
        )


def create_session(
    config: Config, topic: str, name: str | None = None, *, stamp: str | None = None
) -> Session:
    """Create a fresh session under MURARI_HOME/brainstorm-sessions/ and write input/TOPIC.md.
    Collision-safe: an existing name gets a -2, -3, … suffix."""
    stamp = stamp or _stamp()
    slug = slugify(name) if name else ""
    base = f"session-{stamp}" + (f"-{slug}" if slug else "")
    path = config.sessions_dir / base
    i = 2
    while path.exists():
        path = config.sessions_dir / f"{base}-{i}"
        i += 1
    (path / "input").mkdir(parents=True)
    (path / "output" / "artifacts").mkdir(parents=True)
    session = Session(path)
    session.topic_file.write_text(topic, encoding="utf-8")
    return session


def open_session(path: Path | str) -> Session:
    """Reopen an existing session to continue it. Validates the layout (input/TOPIC.md must
    exist) and ensures output/artifacts/ is present."""
    p = Path(path)
    session = Session(p)
    if not session.topic_file.exists():
        raise SessionError(f"not a session directory (no input/TOPIC.md): {p}")
    session.artifacts_dir.mkdir(parents=True, exist_ok=True)
    return session


def list_sessions(config: Config) -> list[Session]:
    """All sessions, most recent first (the timestamped directory name sorts chronologically)."""
    d = config.sessions_dir
    if not d.exists():
        return []
    dirs = [p for p in d.iterdir() if p.is_dir() and (p / "input" / "TOPIC.md").exists()]
    return [Session(p) for p in sorted(dirs, key=lambda p: p.name, reverse=True)]


def snapshot_state(session: Session) -> dict[str, bytes | None]:
    """Capture the output state files (None where a file is absent) so a failed run can be
    rolled back. Raw artifacts under output/artifacts/ are not snapshotted."""
    out: dict[str, bytes | None] = {}
    for name in _STATE_FILES:
        f = session.output_dir / name
        out[name] = f.read_bytes() if f.exists() else None
    return out


def restore_state(session: Session, snapshot: dict[str, bytes | None]) -> None:
    """Restore the output state files to a snapshot: rewrite changed files and remove files
    that were absent in the snapshot."""
    for name, data in snapshot.items():
        f = session.output_dir / name
        if data is None:
            if f.exists():
                f.unlink()
        else:
            f.write_bytes(data)
