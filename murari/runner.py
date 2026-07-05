"""murari — the AgentRunner seam.

The single place that talks to `claude -p`. `ClaudeCliRunner` builds the verified invocation
(canon body via --append-system-prompt, per-role tool narrowing, Bash/Task disallowed) and
parses the envelope through `murari.contract`. `MockAgentRunner` returns canned per-role
contracts for tests. The runner writes nothing to the workspace itself — the agent does.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from murari.config import PROJECT_ROOT, Config
from murari.contract import ContractError, extract_contract, validate_contract

DEFAULT_CANON = PROJECT_ROOT / ".claude" / "agents" / "brainstormer.md"
RUN_TIMEOUT_S = 600  # a role move with live web can run several minutes

# Opus must run on the MAX subscription (claude login), never an API key: these are stripped from
# the `claude -p` subprocess env so Claude Code falls back to its subscription OAuth. The API key
# belongs to the Haiku Messages-API layer (v0.2), not this subprocess (billing split, CLAUDE.md).
_SUBSCRIPTION_ONLY_STRIP = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")

# Per-role tool policy (strategies.md). Bash/Task are always disallowed on top of this.
_FULL = ("WebSearch", "WebFetch", "Read", "Write")
_NO_WEB = ("Read", "Write")
_ALCHEMIST_ANALOGY = ("WebSearch", "Read", "Write")

_FRONTMATTER = re.compile(r"^---\n.*?\n---\n", re.S)

_JSON_REMINDER = "Останнім повідомленням поверни лише JSON контракту, без обгорток."

ROLE_PROMPTS = {
    "generate": (
        "Роль Фантазер: породи щонайменше 3 нові сміливі ідеї/кути на тему; не самоцензуруй "
        "нереалістичне. Кандидати — status open, born_from: prior. Жодних вердиктів. Web не вживай."
    ),
    "evaluate": (
        "Роль Суддя: вибери з open-гіпотез перевірні й дай кожній вердикт із джерелом "
        "(confirmed/refuted/partial). Немає джерела — лишай open."
    ),
    "deepen": (
        "Роль Дослідник: глибоко копай ідею {target} — факти, цифри, умови, межі; кілька "
        "пошуків саме про неї. Збагати запис і додай джерела."
    ),
    "oppose": (
        "Роль Опонент: знайди аргументи ПРОТИ ідеї {target} з джерелами. Мета — не перемогти, "
        "а видобути й записати аргументи. Статус зсувай лише доказами."
    ),
    "mutate": (
        "Роль Алхімік: застосуй мутацію типу {mtype} до ідеї {target}; нащадок — status open з "
        "parents і born_from: mutation. Жодних вердиктів."
    ),
    "weave": (
        "Роль Ткач: перебудуй DOCUMENT.md як зв'язний поточний стан думки (стан, не лог). "
        "Вагомі тези — з джерелом; неперевірене познач як гіпотетичне."
    ),
}

_FULL_CYCLE_PROMPT = (
    "Виконай повний цикл розслідування над TOPIC.md: read → diverge → select → verify → "
    "synthesize → document → write. Ужий WebSearch для перевірки. " + _JSON_REMINDER
)


class RunnerError(RuntimeError):
    """Raised when a run fails to produce a valid contract (bad exit / JSON / schema / timeout)."""


@dataclass(frozen=True)
class RunRequest:
    role: str | None  # None = the full-cycle fallback
    session_dir: Path
    target_idea: str | None = None
    mutation_type: str | None = None
    partner_idea: str | None = None  # the second parent for a `combine` mutation
    style_step: str | None = None


@dataclass(frozen=True)
class RunResult:
    role: str | None
    contract: dict
    raw_envelope: dict = field(repr=False, default_factory=dict)
    duration_s: float | None = None

    @property
    def dry_run(self) -> bool:
        return bool(self.contract.get("dry_run"))


class AgentRunner(Protocol):
    """The seam the engine talks to: one move in, one validated `RunResult` out.
    Implemented by `ClaudeCliRunner` (real) and `MockAgentRunner` (tests)."""

    def run(self, req: RunRequest) -> RunResult: ...


def allowed_tools(role: str | None, mutation_type: str | None = None) -> tuple[str, ...]:
    """The tool set granted for a role's move (the analogy exception gives the Alchemist web)."""
    if role in ("generate", "weave"):
        return _NO_WEB
    if role == "mutate":
        return _ALCHEMIST_ANALOGY if mutation_type == "analogy" else _NO_WEB
    return _FULL  # evaluate / deepen / oppose, and the no-role full-cycle fallback


def build_prompt(
    role: str | None,
    target_idea: str | None = None,
    mutation_type: str | None = None,
    partner_idea: str | None = None,
    style_step: str | None = None,
) -> str:
    """The kickoff (user) message naming this run's move. The canon (system prompt) carries
    the full role definitions; this just says which move to do."""
    if role is None:
        return _FULL_CYCLE_PROMPT
    body = ROLE_PROMPTS[role].format(target=target_idea or "?", mtype=mutation_type or "?")
    if role == "mutate" and mutation_type == "combine" and partner_idea:
        body += f" Друга ідея для схрещення: {partner_idea}."
    return f"{body} {_JSON_REMINDER}"


def strip_frontmatter(text: str) -> str:
    """Drop the leading YAML frontmatter block (and the blank line after it) so the canon body
    can be a system prompt."""
    return _FRONTMATTER.sub("", text, count=1).lstrip("\n")


def _exit_detail(proc: subprocess.CompletedProcess[str]) -> str:
    """A legible reason for a nonzero `claude` exit. Claude Code often writes the real error to
    stdout (as a `result` envelope or plain text) while stderr is empty — check both."""
    err = proc.stderr.strip()
    if err:
        return err[:300]
    out = (proc.stdout or "").strip()
    if out:
        try:
            env = json.loads(out)
            if isinstance(env, dict):
                out = str(env.get("result") or env.get("error") or env)
        except json.JSONDecodeError:
            pass
        return out[:300]
    return "(no output on stdout/stderr — likely a transient API error; re-run)"


def _parse_envelope(stdout: str) -> dict:
    """Extract and validate the v2 contract from a `claude -p` JSON envelope."""
    try:
        env = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise RunnerError(f"run output is not JSON: {e}") from e
    if not isinstance(env, dict) or "result" not in env:
        raise RunnerError("run envelope missing 'result'")
    if env.get("is_error"):
        raise RunnerError(f"agent reported error: {str(env.get('result'))[:200]}")
    try:
        contract = extract_contract(env["result"])
    except (json.JSONDecodeError, ValueError) as e:
        raise RunnerError(f"could not extract contract JSON: {e}") from e
    try:
        validate_contract(contract)
    except ContractError as e:
        raise RunnerError(f"invalid contract: {e}") from e
    return contract


class ClaudeCliRunner:
    """The real runner: builds and executes the verified `claude -p` invocation."""

    def __init__(self, config: Config, canon_path: Path = DEFAULT_CANON) -> None:
        self.config = config
        self.canon_path = canon_path

    def _canon_body(self) -> str:
        return strip_frontmatter(self.canon_path.read_text(encoding="utf-8"))

    def _subprocess_env(self) -> dict[str, str]:
        """The env for `claude -p`: the current environment minus any Anthropic API credentials,
        so Opus runs on the logged-in MAX subscription rather than a (possibly invalid) key."""
        env = dict(os.environ)
        for key in _SUBSCRIPTION_ONLY_STRIP:
            env.pop(key, None)
        return env

    def build_command(self, req: RunRequest) -> list[str]:
        tools = allowed_tools(req.role, req.mutation_type)
        return [
            "claude",
            "-p",
            build_prompt(
                req.role, req.target_idea, req.mutation_type, req.partner_idea, req.style_step
            ),
            "--append-system-prompt",
            self._canon_body(),
            "--model",
            self.config.model,
            "--allowedTools",
            ",".join(tools),
            "--disallowedTools",
            "Bash,Task",
            "--max-turns",
            str(self.config.max_turns),
            "--output-format",
            "json",
        ]

    def run(self, req: RunRequest) -> RunResult:
        argv = self.build_command(req)
        try:
            proc = subprocess.run(
                argv,
                cwd=str(req.session_dir),
                capture_output=True,
                text=True,
                timeout=RUN_TIMEOUT_S,
                env=self._subprocess_env(),
            )
        except subprocess.TimeoutExpired as e:
            raise RunnerError(f"agent run timed out after {RUN_TIMEOUT_S}s") from e
        if proc.returncode != 0:
            raise RunnerError(f"claude exited {proc.returncode}: {_exit_detail(proc)}")
        contract = _parse_envelope(proc.stdout)
        return RunResult(role=req.role, contract=contract, raw_envelope=json.loads(proc.stdout))


class MockAgentRunner:
    """Test double: returns a canned contract per role, optionally mutating the workspace via
    an `on_run(req)` callback (used by the engine integration test). Records every request."""

    def __init__(
        self,
        contracts: dict[str | None, dict],
        *,
        on_run: Callable[[RunRequest], None] | None = None,
    ) -> None:
        self._contracts = contracts
        self._on_run = on_run
        self.calls: list[RunRequest] = []

    def run(self, req: RunRequest) -> RunResult:
        self.calls.append(req)
        if req.role not in self._contracts:
            raise RunnerError(f"no canned contract for role {req.role!r}")
        if self._on_run is not None:
            self._on_run(req)
        contract = self._contracts[req.role]
        validate_contract(contract)
        envelope = {
            "type": "result",
            "is_error": False,
            "result": json.dumps(contract, ensure_ascii=False),
        }
        return RunResult(role=req.role, contract=contract, raw_envelope=envelope, duration_s=0.0)
