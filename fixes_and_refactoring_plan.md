# Fixes & Refactoring Plan — Make This Perfect

Based on 155 past runs + 3 fresh live runs + full code audit + smoke test.

---

## 🔴 PHASE 1 — The Agent Can't Play Doom (Fix the Core)

### 1.1 Weapon Switching Is Broken
```
select_weapon → weapon_switch_failed  (happens every. single. run.)
```
**Root cause:** `Backend/app/services/run_loop.py` calls `select_weapon` but the MCP tool doesn't wait for the switch to complete before returning. ViZDoom weapon switching takes multiple tics.

**Fix:**
- In `doom_mcp_server.py` `select_weapon`: loop for up to 20 tics checking `SELECTED_WEAPON == requested_weapon`
- `game_manager.py` line ~310: add `await self._wait_for_weapon_select(requested_slot)`
- In `run_loop.py` guard system: if `select_weapon` fails, fallback to `take_action` with the weapon key instead

### 1.2 Agent Gets Stuck 23% of the Time
**Root cause:** The LLM receives depth data but has no concept of "I haven't moved in 5 decisions." The stuck detection exists but recovery is weak (just `take_action` with random inputs).

**Fix:**
- Add `position_stuck_counter` in `run_loop.py`: if x,y hasn't changed by >5 units in 3+ consecutive decisions, force an `explore` with `max_tics: 200` and no `stop_on_enemy`
- Track a "visited position hash" grid (already partially done with `visited_cells`) — use it to detect looping
- In `mcp-doom` `explore` tool: add wall-hugging logic (follow left wall when stuck)

### 1.3 Agent Avoids Combat (0.34 avg kills)
**Root cause:** The LLM prompt biases toward exploration over combat. The agent sees "explore" as safer than "aim_and_shoot."

**Fix (`run_loop.py` prompt builder, ~line 230):**
- Add explicit combat priority: *"If an enemy is visible and within 500 units, you MUST engage before exploring"*
- Add ammo awareness: *"When you have >20 ammo and see an enemy, aim_and_shoot first"*
- Add a `target_hp` field to the state prompt — if the agent's health is high, be aggressive

### 1.4 LLM Latency Is Too Slow (avg 4.3s/decision)
**Root cause:** Prompt is massive (~15K tokens per call). `gemini-3.1-flash-lite` is reasonably fast but the context includes full depth arrays, weapon inventory, object lists.

**Fix:**
- Deduplicate the weapon state — it's included in BOTH `game_variables` AND a separate `weapon_state` block. Remove the duplicate.
- Truncate object list: only include visible objects + nearest 3 non-visible. Currently sending 12+ objects every decision.
- Reduce depth data: instead of 6 zone averages, send just `min_dist` and `mean_dist` for 3 zones (left, center, right)
- Target: cut prompt from ~15K to ~8K tokens. Should cut latency from 4.3s to ~2.5s.

### 1.5 The "Repeated issue hypotheses" Spiral
Looking at the trace, decisions #3, #7, #10, #13 all have reason: *"Repeated issue hypotheses are less useful than clearing the visible threat first"* — this is an LLM pattern where it keeps repeating the same meta-commentary instead of acting differently. This wastes decisions.

**Fix:** Add a `decision_diversity_check` in the guard system: if the last 3 decisions had the same `mcp_tool` and similar `reasoning_summary`, force `explore` with a random delta angle.

---

## 🟠 PHASE 2 — Defect Detection Is Hollow

### 2.1 Runtime Defects Are Never Promoted
The DB has 200 hypotheses including `BLOCKED_PATH` (18), `VISUAL_GLITCH` (8), `ENCOUNTER_HOTSPOT` (11) — but `DefectService.detect_for_run()` only checks static analysis ratios.

**Fix — `Backend/app/services/defect_service.py`:**
- Add a `_promote_hypotheses_to_defects(run_id, hypotheses)` method
- For each hypothesis with `confidence >= 0.5` and matching this run's map: promote to a `Defect` with `defect_type` mapped from `tag`:
  - `BLOCKED_PATH` → `progression_blocker`
  - `VISUAL_GLITCH` → `visual_clipping`  
  - `ENCOUNTER_HOTSPOT` → `balance_encounter_density`
  - `RESOURCE_CACHE` → `balance_resource_starvation`
- Add a `max_tick` parameter: only promote hypotheses where `last_seen_tick <= run.max_ticks`

### 2.2 Stuck Monsters Are Detected but Lost
The fresh run without memory found `visual_stuck_monster` and `weapon_malfunction` defects, but with memory they weren't found. This is because the `SituationMemoryService` swallows these observations.

**Fix:**
- `Backend/app/services/situation_memory_service.py`: change the confidence threshold for promoting to `memory.remember()` from 0.5 to 0.3 for visual defects (low bar — any visible clipping is a bug)
- Add a direct `DefectService.add_runtime_defect()` path that the memory service can call immediately when it detects something certain (e.g., `dead == 1` while `HEALTH > 0` = wall-clip death)

### 2.3 Weapon Malfunction Is a Missed Defect Category
Every run has `weapon_switch_failed` events. These are logged but never reported as defects.

**Fix:**
- In `defect_service.py` `_analyze_weapon_failures()`: count `weapon_switch_failed` events per weapon. If >2 failures on the same weapon in one run → `defect_type: weapon_malfunction` with `severity: 2`

---

## 🟡 PHASE 3 — Guard System & Wasted LLM Calls

### 3.1 Guards Are Effective But Waste 20-40% of LLM Calls
The guard system has 3 layers (recovery, validation, execution) with 19 distinct guard paths. They catch real problems: retargeting collected items, combat without weapons, weapon switch loops, getting stuck. But the **LLM is always called first** (line 319), then guards override it.

| Layer | Guards | What They Catch | Override Rate |
|-------|--------|-----------------|---------------|
| Recovery | 4 paths | Stuck loops, low-value explore, hypothesis repetition | ~5-15% |
| Validation | 9 paths | Repeated actions, enemy loops, bad targets, weapon loops | ~10-20% |
| Execution | 3 paths | Missing params, invalid targets, param bounding | ~1-5% |

**Total: ~20-40% of LLM calls are thrown away.**

The guard_modified flag exists per-decision but is **not persisted to the DB** (`agent_decisions` table has no `guard_modified` column). The only tracked counters are `blocked_decision_count` (counts just 4 of the 19 guard paths) and `recovery_count`, `low_value_explore_count`, `meaningful_progress_events`.

**Fix:**

1. **Move checks BEFORE the LLM call** — some guards are deterministic and can skip the LLM entirely:
   - Path 11 (early-game priority pickup) — runs for first 3 decisions, always forces `move_to`. If we know decisions 0-2 are forced, don't call the LLM for them.
   - Path 1 (excessive USE attempts) — if `use_attempt_count >= 8`, skip LLM and go straight to wide explore.
   - Path 4 (no-progress recovery) — if `recovery_count >= 1`, pre-empt the LLM with a recovery action.

2. **Persist `guard_modified` to DB** — add column to `agent_decisions` table so we can analyze override rates per run/profile without replaying decisions.

3. **Add a `guard_interventions` counter** to the run's progress_metrics (currently has 6 counters but none for total overrides).

4. **Path 15 duplicates Path 12** — remove the invisible-target check in `_execute_tool` (dead code).

Estimated savings from pre-LLM guards: ~10-15% of LLM calls eliminated, 3x fewer wasted decisions.

### 3.2 Guard Path 11 Is Overly Prescriptive
The early-game priority pickup forces `move_to` for decisions 0-2 even when the LLM would correctly engage a visible enemy. This wastes runs where combat comes to the player.

**Fix:** Add a visible-enemy exception: if an enemy is within 300 units, skip the forced pickup and let the LLM's decision through.

### 3.3 Guard Path 6 (Enemy-Spotted Loop) Fights the LLM
When the LLM intentionally chooses to bypass an enemy (low ammo, low health), the guard overrides with combat. This gets the agent killed.

**Fix:** Only trigger Path 6 if the agent has >20 ammo AND >50% health. Otherwise trust the LLM's bypass decision.

---

## 🔵 PHASE 4 — Data Integrity & Robustness

### 4.1 Fix `is_sentinel` in Serializer (1-line fix)
**File:** `Backend/app/serializers/game_event_serializers.py` line 79-87
```python
# ADD:
is_sentinel: bool
```
**Also fix frontend:** `frontend/lib/api.ts` line 139-146 — add `is_sentinel: boolean;`

### 4.2 Fix Angle Data Loss
**File:** `Backend/app/serializers/game_event_serializers.py` — add `angle: float` to `PositionTrailOut`
**File:** `Backend/app/routers/runs.py` line 242 — replace `"angle": 0` with `"angle": round(sample.angle, 1)`
**File:** `frontend/lib/api.ts` — add `angle: number;` to `PositionSample`

### 4.3 Add Timeouts on External Processes
| File | Function | Fix |
|------|----------|-----|
| `recording_service.py:162` | `_transcode_h264` | Add `timeout=300` to `subprocess.run` |
| `run_loop.py:867` | `_execute_tool` → `mcp.call_tool` | Wrap with `asyncio.wait_for(mcp.call_tool(...), timeout=30)` |
| `report_service.py:96` | `_render_pdf` | Wrap with `asyncio.wait_for(..., timeout=120)` |
| `report_service.py:442` | `generate` | Wrap with `asyncio.wait_for(..., timeout=60)` |

### 4.4 Fix Silent Exception Handlers
| File | Line(s) | Issue | Fix |
|------|---------|-------|-----|
| `report_service.py` | 1066-1071 | `contextlib.suppress(Exception)` | Add `logger.warning(...)` before suppress |
| `run_loop.py` | 744, 753 | `except Exception: pass` | Add `logger.error(...)` with exception info |
| `recording_service.py` | 55 | writer is None, returns silently | Add `logger.warning("recording skipped")` |

### 4.5 Fix DefectService Side-Effect
**File:** `Backend/app/services/defect_service.py` lines 296, 316

`detect_for_run()` should NOT mutate `run.outcome`. Instead:
- Return the suggested outcome as a return value
- Let the caller (`run_loop.py`'s `finally` block) apply it if appropriate
- Or add a separate `RunService.update_outcome(run_id, outcome)` method

### 4.6 Add Frontend Loading/Error States
| Page | Current State | Fix |
|------|---------------|-----|
| `/run/[id]` | No loading skeleton while data fetches | Add `SkeletonRows` until `isLoading` is false |
| `/history` | No error state if API fails | Add `InlineError` with retry button |
| `/health` | Storage stats shown as raw JSON | Parse and display as structured cards |
| `/wad/[id]` | Launch button disabled silently if MCP is down | Show tooltip "MCP not connected — start MCP-Doom first" |

### 4.7 Fix Frontend Stale-Ref Bug Between SPA Navigations
The `agent-browser` session shows stale content between SPA navigations because the React state doesn't reset properly on route change.

**Fix:** In `frontend/app/providers.tsx` or `shell.tsx`:
```typescript
useEffect(() => {
  setHasError(false);
}, [pathname]);
```

### 4.8 Add Max Upload Size (POC sanity check)
**File:** `Backend/app/services/wad_service.py` `_validate_binary()`:
```python
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50MB
if file_size > MAX_UPLOAD_BYTES:
    raise HTTPException(413, f"File too large: {file_size} bytes (max {MAX_UPLOAD_BYTES})")
```

---

## 🟢 PHASE 5 — The Cross-Run Memory (Fix or Remove)

### 5.1 Memory Was Making Things Worse — Proof
Fresh run without memory: **progress score 26 vs 15** (+73%), **coverage 3.1% vs 2.2%** (+40%), **5 defects vs 2** (+150%).

**Root cause:** 200 hypotheses with avg confidence 0.34 (barely above random). The memory system accumulates noise from 155 failed runs and feeds it back into the LLM prompt, biasing the agent toward cautious/repetitive behavior.

### 5.2 Quick Fix — Raise Confidence Threshold
If keeping the memory system:
- Change `SituationMemoryService.confidence_threshold` from 0.5 to **0.8**
- Add a `min_occurrences = 3` check: only remember something seen 3+ times across runs
- Add decay: reduce confidence by 0.1 for every 10 runs that pass without the observation being confirmed

### 5.3 Better Fix — Rebuild Memory as Achievements
Instead of "what went wrong" (failed hypotheses), store "what worked":
- `POSITION_REACHED`: when the agent successfully moves to a previously unvisited area
- `ENEMY_DEFEATED`: when an enemy is killed at a specific position  
- `ITEM_COLLECTED`: when an item is collected
- `MAP_PROGRESS`: when the agent finds a key, presses a switch, or exits

Then the prompt includes positive signals: *"Previous agent runs have successfully navigated to these areas."* rather than *"Previous agent runs got stuck in these areas."*

### 5.4 Nuclear Option — Delete the Memory Tables
If not fixed within 1 sprint: delete `wad_spatial_memory`, `wad_hypotheses`, `wad_knowledge_base` and the `SituationMemoryService`. The system performs **better without it**.

---

## 🟣 PHASE 6 — Architecture & Deployment

### 6.1 Add Docker Compose
```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: doom_agentic_qa
      POSTGRES_USER: doom_agentic
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data

  mcp-doom:
    build: ./mcp-doom
    environment:
      - DISPLAY=:99
      - DOOM_DEFAULT_IWAD=freedoom2
    depends_on:
      - postgres

  backend:
    build: ./Backend
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      GEMINI_API_KEY:<REDACTED>
      MCP_DOOM_SSE_URL: http://mcp-doom:8001/sse
    depends_on:
      - postgres
      - mcp-doom

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - backend
```

### 6.2 Allow Concurrent Runs
- Replace `pg_advisory_xact_lock` with a per-WAD lock (`pg_try_advisory_xact_lock(hash(wad_id))`)
- Change `RUN_TASKS` from a single dict to a dict of `{run_id: task}`
- Add a `max_concurrent_runs = 2` setting

### 6.3 Fix PDF Hallucinations
**File:** `Backend/app/services/report_service.py` (the prompt that generates the report)

The LLM fabricates hardware/software spec because the prompt doesn't include actual runtime values. Fix:
- Pass `platform.uname()` and `sys.version` as actual runtime values
- Replace `"vizdoom": "1.2.3"` with `vizdoom.__version__`
- Replace `"python": "3.10"` with `sys.version.split()[0]`
- Replace `"os": "Ubuntu 22.04 LTS"` with `platform.platform()`

---

## ⚡ QUICK WINS (Do These Today)

| # | Fix | File(s) | Lines | Effort |
|---|-----|---------|-------|--------|
| 1 | Add `is_sentinel` to serializer | `game_event_serializers.py` | +1 line | 2 min |
| 2 | Add `is_sentinel` to frontend type | `api.ts` | +1 line | 2 min |
| 3 | Add angle to position trail serializer | `game_event_serializers.py`, `runs.py` | ~3 lines | 5 min |
| 4 | Add angle to frontend PositionSample | `api.ts` | +1 line | 2 min |
| 5 | Raise memory confidence threshold to 0.8 | `situation_memory_service.py` | 1 line | 1 min |
| 6 | Move pre-LLM guards (skip LLM for forced decisions 0-2) | `run_loop.py` | ~15 lines | 20 min |
| 7 | Add weapon_switch wait loop | `game_manager.py` | ~15 lines | 30 min |
| 8 | Add stuck position counter | `run_loop.py` guard system | ~20 lines | 20 min |
| 9 | Add combat priority to prompt | `run_loop.py` prompt builder | ~5 lines | 10 min |
| 10 | Promote high-confidence hypotheses to defects | `defect_service.py` | ~30 lines | 45 min |
| 11 | Fix DefectService side-effect (don't mutate outcome) | `defect_service.py` | ~5 lines | 10 min |
| 12 | Add max upload size | `wad_service.py` | ~5 lines | 5 min |
| 13 | Remove duplicate guard Path 15 | `run_loop.py` | ~5 lines | 5 min |

**Total quick wins: ~2.5 hours of work**

---

## 📊 Summary

| Phase | Focus | Issues | Effort | Impact |
|-------|-------|--------|--------|--------|
| 🔴 1 | Agent can't play | 5 root causes | 1 week | 🔥 Critical |
| 🟠 2 | Defect detection hollow | 3 gaps | 2 days | 🔥 Critical |
| 🟡 3 | Guard system + wasted LLM | 3 improvements | 2 days | ⚡ High |
| 🔵 4 | Data integrity & robustness | 8 fixes | 2 days | ⚡ High |
| 🟢 5 | Memory system | 4 options | 1 day | ⚡ High |
| 🟣 6 | Architecture | 3 improvements | 3 days | 📈 Medium |

**Total estimated effort: ~3 weeks for one developer** to go from "mechanically works" to "actually useful QA tool." Security items removed — this is a POC graduation project.
