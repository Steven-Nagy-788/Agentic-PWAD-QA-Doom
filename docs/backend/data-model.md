# Backend Data Model

## Core Records

| Model | Purpose |
| --- | --- |
| `WadFile` | Uploaded WAD identity and storage path |
| `WadMap` | Discovered map metadata |
| `StaticAnalysis` | Static QA metrics |
| `TestRun` | Run configuration, outcome, metrics, environment metadata |
| `AgentDecision` | Prompt input, raw model decision, normalized tool call, MCP output, decision source |
| `GameEvent` | Factual per-decision event evidence |
| `AgentPositionTrail` | Telemetry points including angle and internal sentinels |
| `Defect` | Evidence-backed map-author issue |
| `TestReport` | Generated PDF report metadata |
| `WadSpatialMemory` | Reviewer-only aggregated QA cells |
| `WadHypothesis` | Reviewer-only persistent map hypotheses |

## Evidence Semantics

`GameEvent.tick_number` stores factual MCP game tics. Multiple rows may share a
tic. Consumers order rows by `(tick_number, id)`.

`AgentDecision.decision_source` identifies Gemini decisions and explicit
fallbacks. `guard_modified` remains for backward compatibility but new runs
write `false`.

`AgentPositionTrail.is_sentinel` identifies internal decision-boundary rows.
Public trail and report calculations exclude these rows.

The former generated knowledge-document table has been removed. Reviewer
analytics use spatial cells, hypotheses, defects, and run summaries directly.
