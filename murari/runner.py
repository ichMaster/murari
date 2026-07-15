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
        "(confirmed/refuted/partial); немає джерела — лишай open. Далі онови секцію "
        "`## Ранжування` в LEDGER: кожній оціненій гіпотезі — ★1–5 по осях доказовість/"
        "оригінальність/популярність/пояснювальна сила, рядок «- Hn — доказ:N ориг:N попул:N "
        "поясн:N — джерела: так»."
    ),
    "deepen": (
        "Роль Дослідник: глибоко копай ідею {target} — факти, цифри, умови, межі. Шукай докази "
        "І ЗА, І ПРОТИ (обидві сторони), а не лише підтвердні; кілька пошуків саме про неї. Кожну "
        "знахідку запиши ОКРЕМИМ пунктом у секцію `## Аргументи` LEDGER під `### {target}`, "
        "рядок «- ЗА: … — джерело: url» або «- ПРОТИ: … — джерело: url»; у рядок гіпотези НЕ "
        "втрамбовуй. Додай джерела в SOURCES. Вердикт не виноси — це робота Судді."
    ),
    "oppose": (
        "Роль Опонент: знайди аргументи ПРОТИ ідеї {target} з джерелами. Мета — не перемогти, а "
        "видобути й записати. Кожен контраргумент — ОКРЕМИМ пунктом у `## Аргументи` під "
        "`### {target}`: «- ПРОТИ: … — джерело: url». Статус зсувай лише доказами; познач "
        "«випробувано: N»."
    ),
    "mutate": (
        "Роль Алхімік: застосуй мутацію типу {mtype} до ідеї {target}; нащадок — status open з "
        "parents і born_from: mutation. Жодних вердиктів."
    ),
    "weave": (
        "Роль Ткач: перебудуй DOCUMENT.md як зв'язний поточний СТАН АНАЛІЗУ (що підтверджено / "
        "спростовано / відкрито) — стан, не лог. Вагомі тези — з джерелом; неперевірене познач як "
        "гіпотетичне. НЕ крони одну «правильну» ідею й не давай єдиного вердикту-відповіді: це "
        "середовище аналізу, фінальний вибір — за людиною."
    ),
}

_FULL_CYCLE_PROMPT = (
    "Виконай повний цикл розслідування над TOPIC.md: read → diverge → select → verify → "
    "synthesize → document → write. Ужий WebSearch для перевірки. " + _JSON_REMINDER
)

_STYLE_STEP = re.compile(r"^([a-z]+)\[")

# Style-shaped kickoffs (this is the kickoff layer — the engine builds no prompts). Divergent
# styles keep ideas open and refuse a winner; the Фантазер runs wilder in them.
_WILD_GENERATE_STYLES = frozenset({"explore", "riff"})
_NO_WINNER_WEAVE_STYLES = frozenset({"explore", "debate"})
# Styles where the Суддя scores WITHOUT sources (quick estimate, no verdict) — explore.
_SCORE_ONLY_STYLES = frozenset({"explore"})

_WILD_BOOST = (
    " Стиль дивергентний: дай СПЕКУЛЯТИВНІ, дикі, навіть неможливі ідеї; не зводь за "
    "замовчуванням до правдоподібного чи наукового спростування — цінність тут у розмаїтті."
)

# The Суддя in a score-only style: rate every hypothesis on the axes, no verdicts, no web.
_EVALUATE_SCORE_ONLY = (
    "Роль Суддя (режим оцінки, без джерел): НЕ вішай вердиктів і НЕ шукай у вебі — лише швидко "
    "оціни КОЖНУ гіпотезу й онови секцію `## Ранжування` в LEDGER: ★1–5 по осях доказовість/"
    "оригінальність/популярність/пояснювальна сила, рядок «- Hn — доказ:N ориг:N попул:N поясн:N — "
    "джерела: ні». Статуси лишаються open."
)

_WEAVE_CATALOG = (
    "Роль Ткач (режим каталогу): перебудуй DOCUMENT.md як КАТАЛОГ усіх ідей — кожну окремим "
    "пунктом з коротким описом і що за/проти неї (бери «за/проти» з секції `## Аргументи` LEDGER). "
    "НЕ обирай єдиного переможця й НЕ виноси «головний висновок», яка ідея правильна: цінність тут "
    "— розмаїття."
)

# DOCUMENT.md is written for a reader NEW to the topic — explanatory prose, not a dense expert
# digest. Applied to every weave (both modes).
_WEAVE_STYLE = (
    " Пиши DOCUMENT.md для читача, НОВОГО в темі: пояснюй терміни при першій згадці, повними "
    "звʼязними реченнями, веди думку крок за кроком простою мовою. Уникай телеграфного стилю — "
    "без нагромадження тире й стиснутих фрагментів; краще довше й зрозуміло, ніж щільно."
)

# Rebuilding must not LOSE knowledge: the за/проти is durable LEDGER state, render it in full.
_WEAVE_PRESERVE = (
    " Перебудова НЕ означає втрату знання: жодну гіпотезу з LEDGER не викидай із документа, а "
    "«за/проти» кожної рендери з секції `## Аргументи` LEDGER ПОВНІСТЮ (вона накопичується між "
    "прогонами — нічого звідти не губи й не вихолощуй, навіть для ідей, по яких цей прогін нічого "
    "не додав)."
)

# Every weave (both modes) closes DOCUMENT.md with the multi-axis scorecard — RENDERED from the
# `## Ранжування` state the Суддя wrote, a ranking not a single winner (the axes disagree).
_SCORECARD = (
    " Наприкінці DOCUMENT.md виведи ЗВЕДЕНУ ТАБЛИЦЮ-РАНЖУВАННЯ, РЕНДЕРЯЧИ оцінки з секції "
    "`## Ранжування` LEDGER (не вигадуй нових): рядок на гіпотезу (H-id + короткий опис), ★1–5 по "
    "осях Доказовість/Оригінальність/Популярність/Пояснювальна сила + позначка, чи оцінка з "
    "джерелами. Осі різні, тож переможець не один — таблиця показує сильні й слабкі боки кожної "
    "ідеї, а не єдину «правильну»."
)


def _style_of(style_step: str | None) -> str | None:
    """The style name from an engine style_step like 'explore[3]' (None if absent/unparseable)."""
    if not style_step:
        return None
    m = _STYLE_STEP.match(style_step)
    return m.group(1) if m else None


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
class Usage:
    """Token counts + cost of one agent move, read from the `claude -p` envelope."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def billed_input(self) -> int:
        """All input tokens the run touched (fresh + cache read/creation)."""
        return self.input_tokens + self.cache_read_tokens + self.cache_creation_tokens

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_creation_tokens=self.cache_creation_tokens + other.cache_creation_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
        )


def _extract_usage(env: dict) -> Usage:
    """Pull token counts and cost from a `claude -p` result envelope (missing fields → 0)."""
    u = env.get("usage") or {}
    return Usage(
        input_tokens=int(u.get("input_tokens") or 0),
        output_tokens=int(u.get("output_tokens") or 0),
        cache_read_tokens=int(u.get("cache_read_input_tokens") or 0),
        cache_creation_tokens=int(u.get("cache_creation_input_tokens") or 0),
        cost_usd=float(env.get("total_cost_usd") or 0.0),
    )


@dataclass(frozen=True)
class RunResult:
    role: str | None
    contract: dict
    raw_envelope: dict = field(repr=False, default_factory=dict)
    duration_s: float | None = None
    usage: Usage = field(default_factory=Usage)

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
    the full role definitions; this just says which move to do — shaped by the style: the
    Фантазер runs wilder in divergent styles and the Ткач catalogs (no winner) in them."""
    if role is None:
        return _FULL_CYCLE_PROMPT
    style = _style_of(style_step)
    if role == "weave":
        base = _WEAVE_CATALOG if style in _NO_WINNER_WEAVE_STYLES else ROLE_PROMPTS["weave"]
        # explanatory prose + preserve untouched ideas' text + the ranking table
        body = base + _WEAVE_STYLE + _WEAVE_PRESERVE + _SCORECARD
    elif role == "evaluate" and style in _SCORE_ONLY_STYLES:
        body = _EVALUATE_SCORE_ONLY  # score, don't judge — no sources, no verdicts
    else:
        body = ROLE_PROMPTS[role].format(target=target_idea or "?", mtype=mutation_type or "?")
    if role == "generate" and style in _WILD_GENERATE_STYLES:
        body += _WILD_BOOST
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
    if not isinstance(env, dict):
        raise RunnerError("run envelope is not a JSON object")
    if "result" not in env:
        # Claude Code omits `result` when the run ends on an error subtype (no final text) —
        # most often error_max_turns: the move used all --max-turns before emitting the contract.
        subtype = env.get("subtype") or env.get("type") or "?"
        turns = env.get("num_turns")
        hint = " — raise MURARI_MAX_TURNS" if subtype == "error_max_turns" else ""
        raise RunnerError(f"run ended without a result (subtype={subtype}, turns={turns}){hint}")
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
                timeout=self.config.run_timeout_s,
                env=self._subprocess_env(),
            )
        except subprocess.TimeoutExpired as e:
            raise RunnerError(f"agent run timed out after {self.config.run_timeout_s}s") from e
        if proc.returncode != 0:
            raise RunnerError(f"claude exited {proc.returncode}: {_exit_detail(proc)}")
        contract = _parse_envelope(proc.stdout)
        env = json.loads(proc.stdout)  # valid — _parse_envelope already succeeded
        return RunResult(
            role=req.role, contract=contract, raw_envelope=env, usage=_extract_usage(env)
        )


class MockAgentRunner:
    """Test double: returns a canned contract per role, optionally mutating the workspace via
    an `on_run(req)` callback (used by the engine integration test). Records every request."""

    def __init__(
        self,
        contracts: dict[str | None, dict],
        *,
        on_run: Callable[[RunRequest], None] | None = None,
        usage: Usage | None = None,
    ) -> None:
        self._contracts = contracts
        self._on_run = on_run
        # a small fixed usage per move so token/cost aggregation is exercised without paid calls
        self._usage = (
            usage if usage is not None else Usage(input_tokens=100, output_tokens=20, cost_usd=0.01)
        )
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
        return RunResult(
            role=req.role,
            contract=contract,
            raw_envelope=envelope,
            duration_s=0.0,
            usage=self._usage,
        )
