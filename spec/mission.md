# murari — mission

> Derived document. Primary sources: [murari-CONCEPT.md](murari-CONCEPT.md), [brainstormer.md](brainstormer.md).

## In one sentence

**murari** is a brainstorming tool where a dedicated agent doesn't recite back what the model already
knows — it generates ideas traceable to findings verified against the live web, and weaves them into
a working document.

The name (Sanskrit मुरारि — "enemy of Mura," the demon who weaves snares) sets the role: to cut the
snares of unverified assumptions.

## The problem

An ordinary brainstorming chat returns the **model's priors** — a smooth retelling of what already
sits in the weights, or a rhetorical continuation of your own words. There's no line between "I think
so" and "it is so"; no trace from a claim to a source; confidence of tone substitutes for evidence.
An idea sounds fresh, but it can't be traced.

## The idea

Separate two roles and give each exactly the privileges it needs:

- **Conversation** — a cheap chat brain (Haiku) that holds the dialogue and turns your replies into
  seeds.
- **Research** — a dedicated agent (Claude Code, Opus 4.8) running a
  **diverge → select → verify → synthesize** loop: it generates hypotheses, strikes them against the
  live web, and from what it finds gives birth to fresh ideas.

The key edge of the loop is the **reverse** one: verify findings become the seed for the next
diverge. That is where freshness comes from — an idea grows out of what search returned, not out of
priors.

## What the result is

A session is work on a single document. Its deliverable is a **timestamped `DOCUMENT.md`**: coherent
prose where weighty claims rest on sources, and unverified material is honestly marked as
hypothetical. The document grows over the session, visible in the TUI, and **remains on disk after
exit**. Each document is stamped (created / last-updated), so deliverables accumulate as distinct,
datable artifacts instead of overwriting one file. The ledger and the other files are working
materials alongside it.

A document can be **reopened and continued**: a later session can load a prior session's document
(and its ledger) and keep building on it. There is still no *implicit* cross-session memory — the
agent never silently pulls in other sessions; continuation is always an explicit choice. A fresh
`/b <topic>` still starts from a blank sheet.

## Values (inherited by the agent)

- **Source over confidence.** A verdict without a URL doesn't exist. The model's own certainty is not
  evidence.
- **Freshness over erudition.** An idea from a finding is worth more than an idea from priors; the
  `born_from` field is filled in honestly.
- **Honesty about failure.** No evidence — the status stays `open`. No fresh idea — the run is dry
  (`dry_run: true`). A verdict is never bent to fit expectations.
- **Frugality.** The turn budget is a hard limit. Two hypotheses driven to a verdict beat five
  half-dug.

## Prototype goal

Prove **the agent itself**: that the loop yields ideas traceable to search findings, not a retelling
of priors or of the user's words. Everything else (chat, TUI, orchestration) is scaffolding around
that core.

Definition of done for a single session: within 2–3 runs the ledger holds ≥4 hypotheses with
verdicts and sources and ≥2 fresh ideas traceable to specific findings; `DOCUMENT.md` reads as
coherent prose with sources under weighty claims; a user reply visibly changes the direction of the
next run; dry runs are honestly marked; after `/quit` the timestamped document remains and can be
reopened to continue, while a fresh `/b` still starts from a blank sheet.

## The kiln pattern — fire it here first

murari is a dedicated, minimal tool, not immediately a part of Lumi. First the **firing**: prove the
loop in a narrow, controllable prototype. Once the agent proves itself — the **transfer** into Lumi:
there it becomes a tool in her reply loop or a separate burst worker, the ledger moves into her file
sandbox, the final take speaks in her voice. This is deliberately **outside** the prototype (see
[roadmap.md](roadmap.md)).
