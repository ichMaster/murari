"""murari — the Haiku model seam (Tier 1's brain) and the session Namer.

The single place that talks to the Anthropic Messages API. Billing split (CLAUDE.md): Haiku
bills to the metered `ANTHROPIC_API_KEY` from the gitignored `.env`; the Opus agent runs on
the MAX subscription and never sees that key (the runner strips it from `claude -p`'s env).
`AnthropicHaikuModel` needs the optional `anthropic` SDK; everything else here is stdlib.
The Namer never raises — missing key / missing SDK / API failure falls back to a local,
deterministic title, so naming can never block `new` (and CI makes no paid call).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from murari.config import Config

_TITLE_MAX = 60  # characters — a display name, not a summary
_TITLE_WORDS = 8

_NAMER_SYSTEM = (
    "Дай коротку українську назву (3–6 слів) темі брейнштормінгу, яку надішле користувач. "
    "Відповідай лише назвою — без лапок, крапки в кінці та пояснень."
)


class HaikuError(RuntimeError):
    """Raised when the Haiku API cannot be reached (no key / no SDK) or the call fails."""


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation requested by Haiku (v0.2 has exactly one tool: run_brainstorm)."""

    name: str
    arguments: dict
    id: str = ""


@dataclass(frozen=True)
class HaikuReply:
    """What one Messages-API turn returned: assistant text and/or a single tool call."""

    text: str = ""
    tool_call: ToolCall | None = None
    stop_reason: str | None = None


class HaikuModel(Protocol):
    """The seam the chat layer talks to: one completion in, one `HaikuReply` out.
    Implemented by `AnthropicHaikuModel` (real) and `MockHaikuModel` (tests)."""

    def complete(
        self, system: str, messages: list[dict], tools: list[dict] | None = None
    ) -> HaikuReply: ...


class AnthropicHaikuModel:
    """The real client. Key and SDK are resolved at call time so a keyless environment
    constructs fine and only fails (typed) when actually asked to complete."""

    def __init__(self, config: Config, max_tokens: int = 64_000) -> None:
        # Haiku 4.5's maximum output (64K tokens). Responses are delivered via streaming —
        # the SDK refuses non-streaming requests this large to avoid HTTP timeouts.
        self.config = config
        self.max_tokens = max_tokens

    def complete(
        self, system: str, messages: list[dict], tools: list[dict] | None = None
    ) -> HaikuReply:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key or not key.strip():
            raise HaikuError("ANTHROPIC_API_KEY is not set (put it in .env)")
        try:
            import anthropic
        except ImportError as e:
            raise HaikuError("the 'anthropic' SDK is not installed (pip install .[chat])") from e
        kwargs: dict = {"tools": tools} if tools else {}
        try:
            client = anthropic.Anthropic(api_key=key)
            with client.messages.stream(
                model=self.config.chat_model,
                max_tokens=self.max_tokens,
                system=system,
                messages=messages,
                **kwargs,
            ) as stream:
                resp = stream.get_final_message()
        except Exception as e:  # API/network failure — callers decide how to degrade
            raise HaikuError(f"Haiku call failed: {e}") from e
        text_parts: list[str] = []
        tool_call: ToolCall | None = None
        for block in resp.content:
            btype = getattr(block, "type", "")
            if btype == "text":
                text_parts.append(block.text)
            elif btype == "tool_use" and tool_call is None:
                tool_call = ToolCall(name=block.name, arguments=dict(block.input), id=block.id)
        return HaikuReply(
            text="\n".join(text_parts).strip(),
            tool_call=tool_call,
            stop_reason=resp.stop_reason,
        )


class MockHaikuModel:
    """Test double: pops scripted replies in order (an Exception entry is raised instead),
    recording every call. Exhausting the script raises HaikuError."""

    def __init__(self, replies: list[HaikuReply | Exception] | None = None) -> None:
        self._replies = list(replies or [])
        self.calls: list[dict] = []

    def complete(
        self, system: str, messages: list[dict], tools: list[dict] | None = None
    ) -> HaikuReply:
        # snapshot the message list: callers mutate their history after the call
        self.calls.append({"system": system, "messages": list(messages), "tools": tools})
        if not self._replies:
            raise HaikuError("mock script exhausted")
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


# --- Session naming ----------------------------------------------------------


def local_name(topic: str) -> str:
    """No-API fallback title: the topic's first non-empty line, trimmed to a few words."""
    first = next((ln.strip().lstrip("#").strip() for ln in topic.splitlines() if ln.strip()), "")
    title = " ".join(first.split()[:_TITLE_WORDS])
    if len(title) > _TITLE_MAX:
        title = title[:_TITLE_MAX].rsplit(" ", 1)[0]
    return title.rstrip(" ,.;:—-–?!") or "Без назви"


class Namer:
    """Names a session from its topic: Haiku when reachable, `local_name` otherwise.
    Never raises and never blocks — naming is a nicety, not a gate on `new`."""

    def __init__(self, model: HaikuModel | None) -> None:
        self.model = model

    def name(self, topic: str) -> str:
        if self.model is None:
            return local_name(topic)
        try:
            reply = self.model.complete(_NAMER_SYSTEM, [{"role": "user", "content": topic[:2000]}])
        except Exception:
            return local_name(topic)
        title = (reply.text or "").strip()
        title = title.splitlines()[0].strip().strip('"«»').strip() if title else ""
        return title[:_TITLE_MAX].strip() or local_name(topic)
