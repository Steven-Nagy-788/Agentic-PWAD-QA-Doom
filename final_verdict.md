# Final Comprehensive Evaluation: Agentic PWAD QA Doom

**Date:** 2026-05-29  
**Scope:** Full live E2E test + deep code review + data analysis

---

## 1. Executive Summary

**Verdict: Functionally working — structurally flawed in critical areas.**

The system achieves its core purpose: an LLM agent plays Doom maps autonomously, records gameplay, detects defects, and generates QA reports. All 277 tests pass, all 3 services start and communicate, a full run lifecycle completes, and the frontend renders all data correctly.

However, beneath the surface, there are **significant issues** in agent intelligence (9% map completion), defect coverage (only 2 types), security (API keys in plaintext, no auth), and data fidelity (sentinel field dropped, angles lost).

---

## 2. What Works Well

### Core Functionality
| Feature | Status | Evidence |
|---------|--------|----------|
| WAD upload & validation | ✅ | 13 WADs validated, magic bytes checked |
| Static analysis | ✅ | Enemies, items, sectors, difficulty estimated |
| Run lifecycle | ✅ | create → analyze → run → complete → report |
| LLM decision loop | ✅ | Gemini receives state, returns actions |
| MCP tool execution | ✅ | 14 MCP calls in last run, all succeeded |
| Defect detection | ✅ | Ammo/health insufficiency detected per run |
| PDF report generation | ✅ | 32-section report, 129KB, substantive content |
| MP4 recording | ✅ | 2.4MB, video playable in browser |
| WebSocket streaming | ✅ | Live updates during run |
| Cross-run memory | ✅ | 131 spatial entries, 200 hypotheses, 9 KB docs |

### Frontend
| Page | Status | Notes |
|------|--------|-------|
| WAD Library | ✅ | Grid with thumbnails, counts, upload |
| WAD Detail | ✅ | Map overview, run launcher, difficulty, behavior selector |
| Run Detail | ✅ | Token usage, benchmark, decision trace, video, PDF link |
| Run History | ✅ | Paginated table, 155 runs, filters, sparklines |
| Health | ✅ | API/Gemini/MCP/Storage status |
| Settings | ✅ | Full config, editable |
| Docs | ✅ | Collapsible documentation |

### Testing
| Suite | Tests | Status |
|-------|-------|--------|
| Backend (pytest) | 218 | ✅ All pass |
| MCP-Doom unit | 39 | ✅ All pass |
| Frontend (vitest) | 20 | ✅ All pass |
| Frontend lint | — | ✅ Clean |
| Frontend build | — | ✅ Succeeds |
| Smoke test | 6 stages | ✅ All pass (MCP, Gemini, game start, state, prompt, cleanup) |

---

## 3. Critical Issues (Must Fix)

### 3.1 Agent Intelligence — 9% Map Completion Rate

**Only 14 out of 155 runs complete a map.** The rest end in timeout (25%), stuck (23%), error (12%), crashes (8%), or death (6%).

| Profile | Runs | Completed | Deaths | Stuck | Avg Kills |
|---------|------|-----------|--------|-------|-----------|
| thorough | 140 | 14 (10%) | 8 | 32 | 0.34 |
| fast | 12 | 0 (0%) | 3 | 1 | 0.58 |
| exploit_focused | 3 | 0 (0%) | 0 | 2 | 0.00 |

**MAP01 has 0 completions in 79 runs.** The agent cannot navigate or survive this basic test map. This is the primary product failure — an "autonomous QA agent" that can't effectively play the game.

**Root causes:**
- Average 0.34 kills per run (agent avoids combat)
- Weapon switching frequently fails
- Agent gets stuck on geometry (35/155 = 23% stuck rate)
- No pathfinding awareness — the LLM receives position/depth but can't plan routes
- LLM latency (avg 4.3s per decision) means only ~14 decisions in a typical run

### 3.2 Defect Detection — Only 2 Types, All Static

Every run reports exactly the same 2 defects:
1. `static_ammo_insufficiency` (S1)
2. `static_health_insufficiency` (S2)

These are derived purely from static analysis (ammo ratio, health ratio). **No runtime defects are ever detected** — no visual glitches, no geometry bugs, no progression blockers, no texture issues, no sound problems, no HOM effects, no stuck-in-wall scenarios, no lift/door/switch problems.

The 200 hypotheses in the DB include `VISUAL_GLITCH` (8 entries) and `BLOCKED_PATH` (18 entries), suggesting the `SituationMemoryService` detects these but `DefectService` never promotes them to defects. **Runtime observations are collected but never turned into actionable bug reports.**

### 3.3 Security — P0 Credential Exposure

**Hardcoded secrets in `.env` (not gitignored regarding working tree):**
```
```

**No authentication on any API endpoint.** Anyone with network access can:
- Upload WADs (disk fill attack)
- Launch runs (consume Gemini credits ~$0.02/run)
- Delete all data
- Access recordings, reports, screenshots

### 3.4 Data Fidelity — `is_sentinel` Dropped

The `AgentPositionTrail.is_sentinel` field (database model) is missing from the API serializer `PositionTrailOut`. The frontend also lacks the field in its `PositionSample` type. **Clients cannot distinguish real telemetry from synthetic sentinel entries** — position trail visualizations and analytics are potentially corrupted.

---

## 4. Moderate Issues (Should Fix)

### 4.1 PDF Report Contains LLM Hallucinations

The AI-generated report fabricates specifics:
- Claims `MAP01` is "3840x3840 units" (hallucinated map size)
- Reports `vizdoom: 1.2.3` (actual is 1.3.0)
- States `Ubuntu 22.04 LTS` (actual is Ubuntu 24.04)
- States `python: 3.10` (actual depends on venv)

**32 sections of report, but hardware/software specs are hallucinated.** This undermines the report's credibility for professional QA use.

### 4.2 No Timeout on External Processes

| Process | Risk |
|---------|------|
| FFmpeg transcoding | Can hang indefinitely, blocking run finalization |
| MCP tool calls | Can hang, blocking the entire lockstep loop |
| WeasyPrint PDF | Can hang on malformed HTML |
| Gemini API | Uses retries (3 attempts) but no overall timeout |

### 4.3 Side-Effect Surprise in DefectService

`DefectService.detect_for_run()` mutates the run's `outcome` field in-place (`timeout` → `stuck`, or → `inconclusive_agent_stall`). Callers don't expect a "detect" method to change the run's primary outcome field. No documentation, no logging of the change.

### 4.4 Single Active Run Limits Throughput

PostgreSQL advisory lock allows only one run at a time. A max-ticks run (35000 ticks) can block the pipeline for hours. With 155 runs in the DB and a 9% completion rate, throughput is severely limited.

### 4.5 No Frontend Loading/Error States for API Calls

While the health page has basic error handling, many pages lack:
- Loading skeletons for initial data fetch
- Error boundaries for API failures
- Retry logic for transient failures
- Offline/connection-lost warnings

---

## 5. Minor Issues (Nice to Fix)

| Issue | Category |
|-------|----------|
| Angle data lost in position trail (cast to int, then omitted) | Data loss |
| In-memory lockstep state grows unbounded | Memory |
| Knowledge distillation failures silently swallowed | Observability |
| No max upload size for WAD files | Security |
| Inconsistent "tics"/"ticks" spelling | Polish |
| Session management fragilities in run loop | Robustness |
| `_situation_finished` logic duplicated | Maintainability |
| Stale ref bug in browser session between SPA navigations | UX |

---

## 6. Is It Working As Intended?

**The product works at a mechanical level but fails at its mission.**

| Intended Function | Status | Verdict |
|-------------------|--------|---------|
| "Autonomously play through Doom maps" | ❌ | 9% map completion, 0.34 avg kills — can't effectively play |
| "Detect defects" | ⚠️ | Only 2 static defects, no runtime defects ever promoted |
| "Produce structured QA reports" | ✅ | 32-section PDF generated, substantive but contains hallucinations |
| "Support custom PWADs" | ✅ | 13 WADs uploaded, validated, analyzed |
| "WebSocket live streaming" | ✅ | Real-time state updates during run |
| "Cross-run learning" | ⚠️ | Memory accumulates (131 entries, 200 hypotheses) but confidence is low (avg 0.34) |

**The architecture is sound — the AI agent needs significant improvement.**

---

## 7. Improvement Roadmap

### Phase 1 (Critical — Agent Intelligence)
1. Fix weapon switching — `select_weapon` fails frequently
2. Improve stuck detection/recovery — 23% of runs end in "stuck"
3. Add pathfinding hints to the LLM prompt (waypoints, explored vs unexplored)
4. Reduce LLM latency (average 4.3s per decision is too slow for reactive gameplay)
5. Add combat training examples to the prompt

### Phase 2 (Critical — Defect Coverage)
1. Promote `BLOCKED_PATH`, `VISUAL_GLITCH`, `ENCOUNTER_HOTSPOT` hypotheses to actual defects
2. Add runtime defect detection (texture glitches, HOM, stuck-in-wall, missing textures)
3. Validate map geometry (unreachable items, broken lifts, misaligned textures)
4. Cross-reference multiple runs for consistent defect patterns

### Phase 3 (Security & Data Integrity)
1. Add API authentication (API key or JWT)
2. Remove secrets from `.env` (use environment variables only)
3. Add `is_sentinel` to `PositionTrailOut` serializer + frontend type
4. Add angle field to position trail
5. Add timeouts on all external process calls

### Phase 4 (Robustness)
1. Add loading/error/empty states to all frontend pages
2. Add Docker Compose for single-command deployment
3. Add max upload size for WAD files
4. Fix LLM hallucination in report generation (use actual runtime values for hardware/software)
5. Add logging for all silent exception handlers
