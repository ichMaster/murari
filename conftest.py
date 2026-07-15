"""Make the repo root (holding the `murari` package) importable in tests, and provide a
shared `FakeAgent` — a scripted stand-in for the brainstormer that mutates the session
workspace per move (the way the real agent would) so engine/CLI integration tests can run
the full style loop with zero paid calls.

`python -m pytest` already puts the cwd on sys.path; this keeps `import murari` working
under a bare `pytest` too.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from murari.runner import RunRequest  # noqa: E402
from murari.session import Session  # noqa: E402


@pytest.fixture(autouse=True)
def _no_api_credentials(monkeypatch):
    """Tests never make paid calls: strip any real Anthropic credentials from the environment
    so the Haiku layer (v0.2 Namer/Ведучий) always takes its no-API fallback unless a test
    injects a MockHaikuModel explicitly."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)


class FakeAgent:
    """Scripted brainstormer: on each move it writes the workspace files the real agent would,
    so `is_dry`, the SOURCES delta, and the DOCUMENT-ownership guard all see real changes.
    Stateful across the moves of a single style run. Only `weave` touches DOCUMENT.md."""

    def __init__(self) -> None:
        self.hyps: list[dict] = []
        self.sources = 0
        self._n = 0
        self.scored = False  # set once an evaluate has written the ## Ранжування section
        self.args: list[tuple[str, str, str]] = []  # (hid, side, text) for the ## Аргументи section

    def _add(self, *, status="open", source=None, parents=(), mutation=None) -> str:
        self._n += 1
        hid = f"H{self._n}"
        self.hyps.append(
            {
                "id": hid,
                "status": status,
                "text": f"ідея {hid}",
                "source": source,
                "parents": tuple(parents),
                "mutation": mutation,
            }
        )
        return hid

    def _write_ledger(self, session: Session) -> None:
        lines = ["# LEDGER", "", "## Гіпотези"]
        for h in self.hyps:
            row = f"- [{h['id']}][{h['status']}] {h['text']}"
            if h["source"]:
                row += f" — джерело: {h['source']}"
            if h["parents"]:
                row += " — parents: " + "+".join(h["parents"])
            if h["mutation"]:
                row += f" — mutation: {h['mutation']}"
            lines.append(row)
        lines += ["", "## Прогони", ""]
        if self.scored:  # the Суддя's ## Ранжування (sourced iff the hypothesis got a verdict)
            lines.append("## Ранжування")
            for h in self.hyps:
                sourced = "так" if h["source"] else "ні"
                lines.append(f"- {h['id']} — доказ:2 ориг:3 попул:2 поясн:3 — джерела: {sourced}")
            lines.append("")
        if self.args:  # the Дослідник/Опонент за/проти, grouped per hypothesis
            lines.append("## Аргументи")
            for hid in dict.fromkeys(a[0] for a in self.args):
                lines.append(f"### {hid}")
                lines += [
                    f"- {side}: {text} — джерело: https://e.com/arg"
                    for h, side, text in self.args
                    if h == hid
                ]
            lines.append("")
        lines += ["## Сухі прогони поспіль: 0", ""]
        session.ledger_file.write_text("\n".join(lines), encoding="utf-8")

    def _add_arg(self, hid: str | None, side: str) -> None:
        """Record a за/проти point for a known hypothesis (the target of deepen/oppose)."""
        if hid and any(h["id"] == hid for h in self.hyps):
            self.args.append((hid, side, f"{side.lower()} довід {hid}"))

    def _add_sources(self, session: Session, n: int) -> None:
        f = session.output_dir / "SOURCES.md"
        text = f.read_text(encoding="utf-8") if f.exists() else "# SOURCES\n"
        for _ in range(n):
            self.sources += 1
            text += f"- https://e.com/{self.sources}\n"
        f.write_text(text, encoding="utf-8")

    def __call__(self, req: RunRequest) -> None:
        session = Session(req.session_dir)
        role = req.role
        if role == "generate":
            for _ in range(3):
                self._add()
        elif role == "evaluate":
            self.scored = True  # write the ranking; confirm one open idea (convergent verdict)
            for h in self.hyps:
                if h["status"] == "open":
                    h["status"] = "confirmed"
                    h["source"] = "https://e.com/verdict"
                    break
        elif role == "deepen":
            self._add_sources(session, 2)
            self._add_arg(req.target_idea, "ЗА")
            self._add_arg(req.target_idea, "ПРОТИ")
        elif role == "oppose":
            self._add_sources(session, 1)
            self._add_arg(req.target_idea, "ПРОТИ")
        elif role == "mutate":
            parents = (req.target_idea,) if req.target_idea else ()
            self._add(parents=parents, mutation=req.mutation_type)
        elif role == "weave":
            session.document_file.write_text("# ДОКУМЕНТ\nстан думки\n", encoding="utf-8")
        self._write_ledger(session)


@pytest.fixture
def fake_agent_cls():
    """The FakeAgent class (tests instantiate per run: `agent = fake_agent_cls()`)."""
    return FakeAgent
