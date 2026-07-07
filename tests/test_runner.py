"""MUR-009 — AgentRunner seam: tool matrix, command/prompt builders, envelope parsing, mock.

No real `claude` invocation anywhere — command construction is tested without running, and
the envelope parser is fed strings directly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from murari.config import Config
from murari.runner import (
    ClaudeCliRunner,
    MockAgentRunner,
    RunnerError,
    RunRequest,
    Usage,
    _exit_detail,
    _extract_usage,
    _parse_envelope,
    allowed_tools,
    build_prompt,
    strip_frontmatter,
)

FIX = Path(__file__).parent / "fixtures" / "contract-v2"


def _contract(role: str) -> dict:
    return json.loads((FIX / f"{role}.json").read_text(encoding="utf-8"))


def _cfg(tmp_path) -> Config:
    return Config(runs=6, max_turns=15, model="claude-opus-4-8", home=tmp_path)


def _canon(tmp_path) -> Path:
    p = tmp_path / "brainstormer.md"
    p.write_text(
        "---\nname: brainstormer\ntools: WebSearch, WebFetch, Read, Write\nmodel: opus\n---\n\n"
        "# Канон\nТи — brainstormer.\n",
        encoding="utf-8",
    )
    return p


# --- tool matrix ---


@pytest.mark.parametrize(
    "role,mtype,expected",
    [
        ("generate", None, ("Read", "Write")),
        ("weave", None, ("Read", "Write")),
        ("mutate", "invert", ("Read", "Write")),
        ("mutate", "analogy", ("WebSearch", "Read", "Write")),
        ("evaluate", None, ("WebSearch", "WebFetch", "Read", "Write")),
        ("deepen", None, ("WebSearch", "WebFetch", "Read", "Write")),
        ("oppose", None, ("WebSearch", "WebFetch", "Read", "Write")),
        (None, None, ("WebSearch", "WebFetch", "Read", "Write")),  # full-cycle fallback
    ],
)
def test_allowed_tools(role, mtype, expected):
    assert allowed_tools(role, mtype) == expected


# --- prompt builder ---


def test_build_prompt_renders_role_target_mutation():
    p = build_prompt("mutate", target_idea="H3", mutation_type="invert")
    assert "Алхімік" in p and "H3" in p and "invert" in p and "JSON" in p


def test_build_prompt_evaluate():
    assert "Суддя" in build_prompt("evaluate")


def test_build_prompt_none_is_full_cycle():
    p = build_prompt(None)
    assert "повний цикл" in p and "WebSearch" in p


def test_strip_frontmatter():
    body = strip_frontmatter("---\nname: x\nmodel: opus\n---\n\n# Канон\nтекст\n")
    assert body.startswith("# Канон") and "name: x" not in body


def test_deepen_seeks_both_sides():
    p = build_prompt("deepen", target_idea="H1")
    assert "ЗА" in p and "ПРОТИ" in p  # both-sides evidence, not one-directional


def test_deepen_writes_structured_arguments():
    p = build_prompt("deepen", target_idea="H1")
    assert "## Аргументи" in p and "### H1" in p and "НЕ" in p  # structured, not crammed inline


def test_oppose_writes_structured_arguments():
    p = build_prompt("oppose", target_idea="H3")
    assert "## Аргументи" in p and "### H3" in p and "ПРОТИ" in p


@pytest.mark.parametrize("style_step", ["explore[5]", "debate[5]"])
def test_weave_is_catalog_no_winner_in_divergent_styles(style_step):
    p = build_prompt("weave", style_step=style_step)
    assert "каталог" in p and "переможц" in p  # no winner, catalog all ideas


@pytest.mark.parametrize("style_step", ["investigate[5]", "evolve[5]", None])
def test_weave_converges_in_other_styles(style_step):
    p = build_prompt("weave", style_step=style_step)
    assert "каталог" not in p and "DOCUMENT.md" in p  # the convergent weave


@pytest.mark.parametrize("style_step", ["investigate[5]", "explore[5]", "debate[5]", None])
def test_weave_never_crowns_a_winner(style_step):
    # product principle: analyse ideas, don't pick a winner — the scorecard clause is universal
    assert "переможець не один" in build_prompt("weave", style_step=style_step)


@pytest.mark.parametrize("style_step", ["investigate[5]", None])
def test_convergent_weave_does_not_crown_one_answer(style_step):
    # the softened convergent weave: state of analysis, no single "correct" idea
    assert "не крони" in build_prompt("weave", style_step=style_step).lower()


def test_generate_is_wild_in_divergent_styles():
    assert "СПЕКУЛЯТИВНІ" in build_prompt("generate", style_step="explore[0]")
    assert "СПЕКУЛЯТИВНІ" in build_prompt("generate", style_step="riff[2]")


@pytest.mark.parametrize("style_step", ["explore[5]", "debate[5]", "investigate[5]", None])
def test_weave_always_appends_scorecard(style_step):
    # every weave closes with the multi-axis ranking table, in all styles
    p = build_prompt("weave", style_step=style_step)
    assert "ТАБЛИЦЮ-РАНЖУВАННЯ" in p
    for axis in ("Доказовість", "Оригінальність", "Популярність", "Пояснювальна сила"):
        assert axis in p


def test_weave_renders_scorecard_from_ledger():
    # the scorecard is rendered from LEDGER state, not invented at weave time
    p = build_prompt("weave", style_step="investigate[5]")
    assert "Ранжування" in p and "не вигадуй" in p


@pytest.mark.parametrize("style_step", ["investigate[5]", "explore[5]", "debate[5]", None])
def test_weave_writes_for_a_newcomer(style_step):
    # DOCUMENT.md is explanatory (for a reader new to the topic), not a dense expert digest
    p = build_prompt("weave", style_step=style_step)
    assert "НОВОГО в темі" in p and "телеграфного" in p


@pytest.mark.parametrize("style_step", ["investigate[5]", "explore[5]", None])
def test_weave_preserves_untouched_ideas(style_step):
    # rebuilding must not drop ideas — «за/проти» is rendered in full from the ## Аргументи state
    p = build_prompt("weave", style_step=style_step)
    assert "не викидай" in p and "Аргументи" in p and "нічого звідти не губи" in p


def test_evaluate_score_only_in_explore():
    p = build_prompt("evaluate", style_step="explore[4]")
    assert "режим оцінки" in p and "джерела: ні" in p
    assert "НЕ вішай вердиктів" in p


@pytest.mark.parametrize("style_step", ["investigate[1]", "debate[4]", None])
def test_evaluate_verifies_and_scores_in_convergent(style_step):
    p = build_prompt("evaluate", style_step=style_step)
    assert "вердикт" in p and "Ранжування" in p  # verify + sourced score
    assert "джерела: так" in p


@pytest.mark.parametrize("style_step", ["investigate[0]", None])
def test_generate_is_plain_in_convergent_styles(style_step):
    assert "СПЕКУЛЯТИВНІ" not in build_prompt("generate", style_step=style_step)


# --- command construction (no subprocess) ---


def test_build_command(tmp_path):
    runner = ClaudeCliRunner(_cfg(tmp_path), canon_path=_canon(tmp_path))
    argv = runner.build_command(RunRequest(role="deepen", session_dir=tmp_path, target_idea="H1"))
    assert argv[0:2] == ["claude", "-p"]
    assert "--model" in argv and argv[argv.index("--model") + 1] == "claude-opus-4-8"
    assert argv[argv.index("--max-turns") + 1] == "15"
    assert argv[argv.index("--allowedTools") + 1] == "WebSearch,WebFetch,Read,Write"
    assert argv[argv.index("--disallowedTools") + 1] == "Bash,Task"
    assert argv[-2:] == ["--output-format", "json"]
    body = argv[argv.index("--append-system-prompt") + 1]
    assert body.startswith("# Канон") and "name: brainstormer" not in body  # frontmatter stripped


def test_subprocess_env_strips_api_key(tmp_path, monkeypatch):
    # Opus must ride the MAX subscription, not the API key — the key must not reach `claude -p`
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-should-not-leak")
    monkeypatch.setenv("PATH", "/usr/bin")  # an ordinary var stays
    runner = ClaudeCliRunner(_cfg(tmp_path), canon_path=_canon(tmp_path))
    env = runner._subprocess_env()
    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert env["PATH"] == "/usr/bin"


def test_build_command_analogy_grants_websearch(tmp_path):
    runner = ClaudeCliRunner(_cfg(tmp_path), canon_path=_canon(tmp_path))
    argv = runner.build_command(
        RunRequest(role="mutate", session_dir=tmp_path, target_idea="H1", mutation_type="analogy")
    )
    assert argv[argv.index("--allowedTools") + 1] == "WebSearch,Read,Write"


# --- envelope parsing ---


def test_parse_envelope_valid():
    contract = _contract("evaluate")
    env = {"type": "result", "is_error": False, "result": json.dumps(contract)}
    assert _parse_envelope(json.dumps(env)) == contract


def test_parse_envelope_fenced_result():
    contract = _contract("weave")
    env = {"result": f"```json\n{json.dumps(contract)}\n```"}
    assert _parse_envelope(json.dumps(env)) == contract


def test_parse_envelope_bad_json_raises():
    with pytest.raises(RunnerError):
        _parse_envelope("not json at all")


def test_parse_envelope_missing_result_raises():
    with pytest.raises(RunnerError):
        _parse_envelope(json.dumps({"type": "result"}))


def test_parse_envelope_is_error_raises():
    with pytest.raises(RunnerError):
        _parse_envelope(json.dumps({"is_error": True, "result": "API Error: ..."}))


def test_parse_envelope_invalid_contract_raises():
    bad = _contract("evaluate")
    bad["role"] = "planner"
    with pytest.raises(RunnerError):
        _parse_envelope(json.dumps({"result": json.dumps(bad)}))


# --- nonzero-exit diagnostics ---


class _Proc:
    def __init__(self, stdout="", stderr=""):
        self.stdout = stdout
        self.stderr = stderr


def test_exit_detail_prefers_stderr():
    assert _exit_detail(_Proc(stderr="boom")) == "boom"


def test_exit_detail_reads_error_from_stdout_envelope():
    # Claude Code writes the real error to stdout while stderr is empty
    out = json.dumps({"type": "result", "is_error": True, "result": "Overloaded"})
    assert _exit_detail(_Proc(stdout=out)) == "Overloaded"


def test_exit_detail_handles_empty_output():
    assert "transient" in _exit_detail(_Proc())


# --- usage (tokens + cost) ---


def test_extract_usage_reads_tokens_and_cost():
    env = {
        "usage": {
            "input_tokens": 5,
            "output_tokens": 12,
            "cache_read_input_tokens": 100,
            "cache_creation_input_tokens": 200,
        },
        "total_cost_usd": 0.42,
    }
    u = _extract_usage(env)
    assert u.input_tokens == 5 and u.output_tokens == 12
    assert u.cache_read_tokens == 100 and u.cache_creation_tokens == 200
    assert u.billed_input == 305 and u.cost_usd == 0.42


def test_extract_usage_missing_fields_are_zero():
    assert _extract_usage({}) == Usage()


def test_usage_adds():
    total = Usage(input_tokens=1, output_tokens=2, cost_usd=0.1) + Usage(
        input_tokens=3, output_tokens=4, cost_usd=0.2
    )
    assert total.input_tokens == 4 and total.output_tokens == 6
    assert abs(total.cost_usd - 0.3) < 1e-9


def test_mock_runner_reports_usage(tmp_path):
    mock = MockAgentRunner(
        {"generate": _contract("generate")}, usage=Usage(input_tokens=7, output_tokens=3)
    )
    res = mock.run(RunRequest(role="generate", session_dir=tmp_path))
    assert res.usage.input_tokens == 7 and res.usage.output_tokens == 3


# --- mock runner ---


def test_mock_runner_returns_canned_and_records(tmp_path):
    contracts = {r: _contract(r) for r in ("generate", "evaluate", "weave")}
    mock = MockAgentRunner(contracts)
    res = mock.run(RunRequest(role="evaluate", session_dir=tmp_path))
    assert res.role == "evaluate" and res.contract == contracts["evaluate"]
    assert res.dry_run is False
    assert [c.role for c in mock.calls] == ["evaluate"]


def test_mock_runner_on_run_mutates_workspace(tmp_path):
    marker = tmp_path / "touched"

    def _on_run(req):
        marker.write_text("done", encoding="utf-8")

    mock = MockAgentRunner({"generate": _contract("generate")}, on_run=_on_run)
    mock.run(RunRequest(role="generate", session_dir=tmp_path))
    assert marker.read_text() == "done"


def test_mock_runner_unknown_role_raises(tmp_path):
    mock = MockAgentRunner({"generate": _contract("generate")})
    with pytest.raises(RunnerError):
        mock.run(RunRequest(role="oppose", session_dir=tmp_path))
