"""murari — configuration: budgets, paths, and a dependency-free .env loader.

Deterministic, stdlib-only. Every module imports these without circular deps.
Opus 4.8 is expensive, so the budgets here are the primary cost ceiling of a session.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# --- Paths ------------------------------------------------------------------
# The package lives at <repo>/murari, so the project root is its parent.
_PKG_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = _PKG_DIR.parent
ENV_FILE = PROJECT_ROOT / ".env"  # secrets (ANTHROPIC_API_KEY for the Haiku layer); gitignored

# --- Defaults ---------------------------------------------------------------
DEFAULT_RUNS = 6
DEFAULT_MAX_TURNS = 15
DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_RUN_TIMEOUT = 900  # seconds a single agent move may take before it is killed (15 min)
# The Ведучий brain (v0.2 chat layer / Namer) — Messages API, billed to the metered key.
DEFAULT_CHAT_MODEL = "claude-haiku-4-5"


def load_dotenv(path: Path = ENV_FILE) -> None:
    """Minimal KEY=VALUE .env loader with no third-party dependency. Supports whole-line
    and inline (` # ...`) comments. Real environment variables take priority — setdefault
    does not overwrite an already-set value."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        val = val.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), val)


@dataclass(frozen=True)
class Config:
    """Session budgets, agent model, and home directory."""

    runs: int  # agent moves per session (MURARI_RUNS)
    max_turns: int  # --max-turns per move (MURARI_MAX_TURNS)
    model: str  # agent model (MURARI_MODEL)
    home: Path  # base dir (MURARI_HOME)
    # seconds a single move may take before it is killed (MURARI_RUN_TIMEOUT)
    run_timeout_s: int = DEFAULT_RUN_TIMEOUT
    # Haiku chat model (MURARI_CHAT_MODEL) — the Ведучий/Namer brain, never the agent
    chat_model: str = DEFAULT_CHAT_MODEL

    @property
    def sessions_dir(self) -> Path:
        return self.home / "brainstorm-sessions"


def _int_env(key: str, default: int) -> int:
    v = os.environ.get(key)
    if v is None or not v.strip():
        return default
    try:
        return int(v)
    except ValueError:
        return default


def load_config() -> Config:
    """Resolve config from the environment (after loading .env). `MURARI_HOME` defaults to
    a gitignored `<repo>/.murari`; budgets and model fall back to the DEFAULT_* constants."""
    load_dotenv()
    home = os.environ.get("MURARI_HOME")
    home_path = Path(home).expanduser() if home and home.strip() else PROJECT_ROOT / ".murari"
    return Config(
        runs=_int_env("MURARI_RUNS", DEFAULT_RUNS),
        max_turns=_int_env("MURARI_MAX_TURNS", DEFAULT_MAX_TURNS),
        model=os.environ.get("MURARI_MODEL") or DEFAULT_MODEL,
        home=home_path,
        run_timeout_s=_int_env("MURARI_RUN_TIMEOUT", DEFAULT_RUN_TIMEOUT),
        chat_model=os.environ.get("MURARI_CHAT_MODEL") or DEFAULT_CHAT_MODEL,
    )
