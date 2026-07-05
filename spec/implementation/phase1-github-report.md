# Phase p1 — GitHub Issues Report

**Uploaded:** 2026-07-05
**Repository:** https://github.com/ichMaster/murari
**Total issues:** 6

## Issue Mapping

| MUR ID | GitHub # | Title | Phase | Labels | URL |
|--------|----------|-------|-------|--------|-----|
| MUR-006 | #6 | Project scaffolding: pyproject, package layout, config | p1 | p1::phase:1, p1::size:S, p1::area:orchestrator | https://github.com/ichMaster/murari/issues/6 |
| MUR-007 | #7 | Canon v2 install + contract v2 re-pin | p1 | p1::phase:1, p1::size:M, p1::area:agent | https://github.com/ichMaster/murari/issues/7 |
| MUR-008 | #8 | LEDGER v2: parser, lineage, journal, per-move dry-run | p1 | p1::phase:1, p1::size:M, p1::area:orchestrator | https://github.com/ichMaster/murari/issues/8 |
| MUR-009 | #9 | AgentRunner seam: verified invocation, per-role tools, mock | p1 | p1::phase:1, p1::size:M, p1::area:orchestrator | https://github.com/ichMaster/murari/issues/9 |
| MUR-010 | #10 | Session lifecycle: create, open-and-continue, graceful failure | p1 | p1::phase:1, p1::size:S, p1::area:orchestrator | https://github.com/ichMaster/murari/issues/10 |
| MUR-011 | #11 | Style engine + CLI: sequences, randomness, budgets, ownership | p1 | p1::phase:1, p1::size:L, p1::area:orchestrator | https://github.com/ichMaster/murari/issues/11 |

## Dependencies (blocked-by comments)

- #7 (MUR-007) blocked by #6 (MUR-006)
- #8 (MUR-008) blocked by #6 (MUR-006), #7 (MUR-007)
- #9 (MUR-009) blocked by #6 (MUR-006), #7 (MUR-007)
- #10 (MUR-010) blocked by #6 (MUR-006)
- #11 (MUR-011) blocked by #8 (MUR-008), #9 (MUR-009), #10 (MUR-010)

**Critical path:** #6 → #7 → #9 → #11

## Labels Created

- p1::phase:1 — Phase v0.1 — Orchestration (style engine)
- p1::size:S, p1::size:M, p1::size:L
- p1::area:orchestrator, p1::area:agent
