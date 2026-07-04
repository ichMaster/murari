# Phase p0 — GitHub Issues Report

**Uploaded:** 2026-07-04
**Repository:** https://github.com/ichMaster/murari
**Total issues:** 5

## Issue Mapping

| MUR ID | GitHub # | Title | Phase | Labels | URL |
|--------|----------|-------|-------|--------|-----|
| MUR-001 | #1 | Install the brainstormer agent | p0 | p0::phase:0, p0::size:S, p0::area:agent | https://github.com/ichMaster/murari/issues/1 |
| MUR-002 | #2 | Hand-written test session workspace (TOPIC.md) | p0 | p0::phase:0, p0::size:S, p0::area:tests | https://github.com/ichMaster/murari/issues/2 |
| MUR-003 | #3 | By-hand run: fire the loop and capture artifacts | p0 | p0::phase:0, p0::size:M, p0::area:agent | https://github.com/ichMaster/murari/issues/3 |
| MUR-004 | #4 | Contract test: pin the agent JSON output schema | p0 | p0::phase:0, p0::size:S, p0::area:tests | https://github.com/ichMaster/murari/issues/4 |
| MUR-005 | #5 | Workspace-format test: pin LEDGER structure + dry-run counter | p0 | p0::phase:0, p0::size:M, p0::area:tests | https://github.com/ichMaster/murari/issues/5 |

## Dependencies (blocked-by comments)

- #3 (MUR-003) blocked by #1 (MUR-001), #2 (MUR-002)
- #4 (MUR-004) blocked by #3 (MUR-003)
- #5 (MUR-005) blocked by #3 (MUR-003)

**Critical path:** #1 → #3 → #4 / #5

## Labels Created

- p0::phase:0 — Phase v0.0 — Agent alone (firing the core)
- p0::size:S, p0::size:M
- p0::area:agent, p0::area:tests
