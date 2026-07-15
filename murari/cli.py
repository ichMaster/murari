"""murari — headless CLI (v0.1).

Three subcommands over the style engine:
  murari new  <topic> [--name N] [--style S] [--seed K]   create a session and run one style
  murari open <session-dir>                                reopen and print its current state
  murari run  <session-dir>  [--style S] [--seed K]        run one style over an existing session
  murari list                                              list sessions, most recent first

The AgentRunner is injectable (`main(..., runner=...)`) so tests drive the engine with a
MockAgentRunner and never touch `claude`. A run is wrapped in snapshot/restore: a failure
leaves the workspace exactly as it was.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from murari.chat import ChatSession, run_repl
from murari.config import Config, load_config
from murari.engine import (
    DEFAULT_DEPTH,
    DEFAULT_STYLE,
    DEPTHS,
    STYLES,
    Engine,
    EngineError,
    EngineResult,
)
from murari.haiku import AnthropicHaikuModel, HaikuModel, Namer
from murari.ledger import LedgerError
from murari.runner import AgentRunner, ClaudeCliRunner
from murari.session import (
    Session,
    SessionError,
    create_session,
    list_sessions,
    open_session,
    titled_topic,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="murari", description="headless brainstorm orchestrator")
    sub = p.add_subparsers(dest="cmd", required=True)

    new = sub.add_parser("new", help="create a session and run one style")
    new.add_argument("topic", help="the brainstorm topic (written to input/TOPIC.md)")
    new.add_argument("--name", default=None, help="optional slug for the session directory")
    new.add_argument(
        "--style", default=DEFAULT_STYLE, choices=sorted(STYLES), help="brainstorm style"
    )
    new.add_argument(
        "--depth",
        default=DEFAULT_DEPTH,
        choices=DEPTHS,
        help="full (6) / brief (3) / tiny (1 role)",
    )
    new.add_argument("--moves", type=int, default=None, help="cap moves below MURARI_RUNS")
    new.add_argument("--seed", type=int, default=0, help="RNG seed for mutation/target choices")

    op = sub.add_parser("open", help="reopen a session and print its state")
    op.add_argument("session", help="path to an existing session directory")

    run = sub.add_parser("run", help="run one style over an existing session")
    run.add_argument("session", help="path to an existing session directory")
    run.add_argument(
        "--style", default=DEFAULT_STYLE, choices=sorted(STYLES), help="brainstorm style"
    )
    run.add_argument(
        "--depth",
        default=DEFAULT_DEPTH,
        choices=DEPTHS,
        help="full (6) / brief (3) / tiny (1 role)",
    )
    run.add_argument("--moves", type=int, default=None, help="cap moves below MURARI_RUNS")
    run.add_argument("--seed", type=int, default=0, help="RNG seed for mutation/target choices")
    run.add_argument(
        "--target",
        default=None,
        metavar="Hxx[,Hyy…]",
        help="pin deepen/oppose/mutate to a hypothesis; a comma list runs the style once per one",
    )

    sub.add_parser("list", help="list sessions, most recent first")

    chat = sub.add_parser("chat", help="facilitated chat over a session (v0.2, headless REPL)")
    chat.add_argument("session", nargs="?", default=None, help="existing session to continue")
    chat.add_argument("--new", dest="new_topic", default=None, help="start a fresh session")
    chat.add_argument("--name", default=None, help="optional slug/title for --new")
    chat.add_argument(
        "--style", default=None, choices=sorted(STYLES), help="style (default: inferred)"
    )
    return p


def _format_result(session: Session, res: EngineResult) -> str:
    lines = [
        f"session: {session.path}",
        f"style: {res.style}/{res.depth}  seed: {res.seed}  ({res.stopped})",
    ]
    for m in res.moves:
        tgt = f" →{m.target}" if m.target else ""
        mut = f" [{m.mutation_type}]" if m.mutation_type else ""
        flag = " DRY" if m.dry else ""
        dev = f"  ⤳ {m.deviated}" if m.deviated else ""
        lines.append(f"  {m.index}: {m.move}{tgt}{mut} ({m.budget_tier}){flag}{dev}")
    u = res.usage
    lines.append(
        f"usage: {res.duration_s:.0f}s · in {u.billed_input} / out {u.output_tokens} tokens "
        f"· ${u.cost_usd:.2f}"
    )
    led = session.read_ledger()
    if led is not None:
        lines.append(
            f"ledger: {len(led.hypotheses)} hypotheses, {len(led.survivors())} survivors, "
            f"dry-streak {led.dry_streak}"
        )
    lines.append("document: " + ("present" if session.read_document() else "none"))
    return "\n".join(lines)


def _run_style(
    session: Session,
    config: Config,
    runner: AgentRunner,
    style: str,
    depth: str,
    seed: int,
    moves: int | None,
    target: str | None = None,
) -> int:
    """Run a style, streaming live progress. The engine keeps completed moves and rolls back only
    a failed move, so a mid-run failure never discards the paid work before it."""
    engine = Engine(config, runner)
    try:
        res = engine.run_style(
            session,
            style,
            depth=depth,
            seed=seed,
            max_moves=moves,
            target=target,
            on_progress=print,
        )
    except (EngineError, LedgerError) as e:  # pre-run: unknown style/target, malformed ledger
        print(f"cannot run: {e}", file=sys.stderr)
        return 1
    print(_format_result(session, res))
    if res.stopped == "failed":
        print(f"run stopped: {res.error} — completed moves kept", file=sys.stderr)
        return 1
    return 0


def cmd_new(
    args: argparse.Namespace, config: Config, runner: AgentRunner, haiku: HaikuModel | None
) -> int:
    # --name overrides the Namer entirely (no Haiku call); otherwise Haiku titles the topic
    # with a no-API local fallback, so `new` never blocks on naming.
    title = args.name or Namer(haiku).name(args.topic)
    session = create_session(config, titled_topic(title, args.topic), args.name)
    print(f"created {session.path} — {title}")
    return _run_style(session, config, runner, args.style, args.depth, args.seed, args.moves)


def cmd_open(
    args: argparse.Namespace, config: Config, runner: AgentRunner, haiku: HaikuModel | None
) -> int:
    try:
        session = open_session(Path(args.session))
    except SessionError as e:
        print(f"cannot open session: {e}", file=sys.stderr)
        return 1
    topic = session.read_topic()
    print(f"session: {session.path}")
    title = session.read_title()
    if title:
        print(f"name: {title}")
    lines = [ln for ln in topic.splitlines() if ln.strip()]
    if title and lines:  # skip the `# <name>` heading — show the topic body itself
        lines = lines[1:]
    print("topic: " + (lines[0] if lines else "—"))
    led = session.read_ledger()
    if led is None:
        print("ledger: (none yet)")
    else:
        print(
            f"ledger: {len(led.hypotheses)} hypotheses, {len(led.survivors())} survivors, "
            f"dry-streak {led.dry_streak}"
        )
        for h in led.hypotheses:  # list H-ids (with the ranking, if scored) for --target
            text = h.text if len(h.text) <= 55 else h.text[:54] + "…"
            s = led.score(h.id)
            score = ""
            if s is not None:
                mark = "джерела" if s.sourced else "чорнова"
                score = (
                    f"  ★ дк{s.evidence} ор{s.originality} "
                    f"пп{s.popularity} пс{s.explanatory} ({mark})"
                )
            args = led.arguments_for(h.id)
            argc = ""
            if args:
                za = sum(1 for a in args if a.side == "за")
                argc = f"  ({za} за / {len(args) - za} проти)"
            print(f"  {h.id} [{h.status}] {text}{score}{argc}")
    print("document: " + ("present" if session.read_document() else "none"))
    return 0


def _parse_targets(raw: str | None) -> list[str | None]:
    """`None` → a single auto-target run; "H1,H3" → one run per listed hypothesis."""
    if not raw or not raw.strip():
        return [None]
    return [t.strip() for t in raw.split(",") if t.strip()]


def cmd_run(
    args: argparse.Namespace, config: Config, runner: AgentRunner, haiku: HaikuModel | None
) -> int:
    try:
        session = open_session(Path(args.session))
    except SessionError as e:
        print(f"cannot open session: {e}", file=sys.stderr)
        return 1

    targets = _parse_targets(args.target)
    if any(t is not None for t in targets):  # validate the whole list up front (before spending)
        try:
            led = session.read_ledger()
        except LedgerError as e:
            print(f"cannot read ledger: {e}", file=sys.stderr)
            return 1
        ids = led.ids() if led else set()
        unknown = [t for t in targets if t not in ids]
        if unknown:
            avail = sorted(ids) or "none"
            print(f"unknown target(s) {unknown}; available: {avail}", file=sys.stderr)
            return 1

    rc = 0
    for target in targets:
        if len(targets) > 1:
            print(f"--- target {target} ---")
        rc |= _run_style(
            session, config, runner, args.style, args.depth, args.seed, args.moves, target
        )
    return rc


def cmd_chat(
    args: argparse.Namespace, config: Config, runner: AgentRunner, haiku: HaikuModel | None
) -> int:
    if args.new_topic:
        title = args.name or Namer(haiku).name(args.new_topic)
        session = create_session(config, titled_topic(title, args.new_topic), args.name)
        print(f"created {session.path} — {title}")
    elif args.session:
        try:
            session = open_session(Path(args.session))
        except SessionError as e:
            print(f"cannot open session: {e}", file=sys.stderr)
            return 1
    else:
        print('вкажи сесію або --new "<тема>"', file=sys.stderr)
        return 1
    chat = ChatSession(config, session, runner, haiku, style=args.style, on_progress=print)
    run_repl(chat, sys.stdin, print)
    return 0


def cmd_list(
    args: argparse.Namespace, config: Config, runner: AgentRunner, haiku: HaikuModel | None
) -> int:
    sessions = list_sessions(config)
    if not sessions:
        print("no sessions")
        return 0
    for s in sessions:
        title = s.read_title()
        print(f"{s.path.name} — {title}" if title else s.path.name)
    return 0


_COMMANDS = {"new": cmd_new, "open": cmd_open, "run": cmd_run, "list": cmd_list, "chat": cmd_chat}


def main(
    argv: list[str] | None = None,
    *,
    runner: AgentRunner | None = None,
    config: Config | None = None,
    haiku: HaikuModel | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    config = config or load_config()
    runner = runner if runner is not None else ClaudeCliRunner(config)
    # The real Haiku model degrades to the local fallback when keyless/SDK-less, so this
    # default stays offline-safe; tests inject MockHaikuModel to script it.
    haiku = haiku if haiku is not None else AnthropicHaikuModel(config)
    return _COMMANDS[args.cmd](args, config, runner, haiku)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
