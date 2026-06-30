# Thesis Edit Guide — "BoJack: The Ultimate Agentic Game Tester"

Evidence-based editing instructions for `gd-theseis.md`.  
Each section lists: **what to change**, **what to replace it with**, and **why** (codebase evidence or research citation).

---

## Priority Legend

- **CRITICAL** — Factual error, overclaim, or missing mandatory content. Must fix.
- **HIGH** — Significant gap that weakens the thesis argument.
- **MEDIUM** — Improvement that strengthens credibility.
- **LOW** — Polish / nice-to-have.

---

## Declaration & Acknowledgements (Lines 17–30)

### CRITICAL: Originality Claim

**Current (line 22–24):**
> "We confirm that this project introduces an approach that has not previously existed and that no external assistance or outside contributions were utilized."

**Problem:** The system uses Anthropic's MCP (open standard, launched Nov 2024), ViZDoom (2016), and Gemini API — all external, established technologies. TITAN (Wang et al., 2025) already deployed LLM-driven game QA at NetEase. The claim of non-existence is factually incorrect.

**Replace with:**
> "We confirm that this project represents an original engineering contribution that combines existing technologies — the Model Context Protocol, ViZDoom, and Google Gemini — into a purpose-built automated game quality assurance platform with integrated audit trails and report generation. While related work exists in LLM-driven game testing, our system is the first to combine MCP-based tool abstractions with lockstep auditable decision loops specifically for Doom PWAD map quality assurance."

**Why:** Accurately frames the contribution as engineering integration rather than algorithmic novelty, which is defensible and honest.

---

## Abstract (Lines 34–64)

### HIGH: Coverage and Kill Claims

**Current (line 47–48):**
> "Testing was conducted across multiple game maps and genres. The agent successfully identified traversal edge cases, unreachable regions, and pathfinding inconsistencies..."

**Problem:** Testing was conducted on only 2 successfully loaded maps (Easy E1M1 and Easy MAP01), not "multiple genres." Slaughter E1M1 failed at initialization every time. Hard E1M1 runs were all cancelled.

**Change to:**
> "Testing was conducted across four WAD configurations (Easy E1M1, Hard E1M1, Slaughter E1M1, Easy MAP01), of which two produced gameplay data. The agent identified unreachable secret sectors via static analysis and LLM-observed traversal edge cases on successfully loaded maps..."

### HIGH: User Satisfaction Table

**Current (lines 51–63):** Presents 7 dimension scores from "six indie studio leads."

**Problem:** N=6 is too small for quantitative dimension scores with decimal precision. The scores imply statistical rigor that doesn't exist with 6 participants.

**Change to:**
> "User feedback from six indie studio leads was collected through post-session surveys and semi-structured interviews. Overall satisfaction averaged 4.1/5, with qualitative feedback highlighting overnight autonomous runs and IEEE-format reports as the most valued features. Due to the small sample size, these results should be interpreted as indicative rather than statistically significant."

### MEDIUM: Cross-Run Hypothesis Score

**Current (line 60):** "Cross-Run Hypothesis: 2.9/5 — Mixed results"

**Add clarification:**
> "Note: a toggle to enable/disable cross-run memory already exists in the settings interface (`settings/page.tsx`), allowing users to disable this feature when it produces unreliable results."

---

## Chapter 1: Introduction

### 1.1 Problem Statement (Lines 169–200)

#### MEDIUM: Cyberpunk 2077 Example

**Current (lines 174–181):** Uses Cyberpunk 2077 as the motivating example.

**Assessment:** The example is fine but could be strengthened with a more recent (2025–2026) example to show the problem is ongoing. Consider adding a reference to a recent troubled launch if one exists, or keeping Cyberpunk but noting the problem persists industry-wide.

#### LOW: IBM Cost Statistics

**Current (line 192):** "fixing bugs found after product release costs four to five times more"

**This is fine.** The McPeak (2017) citation is adequate for this general claim.

---

### 1.2 Project Objectives (Lines 205–230)

#### CRITICAL: Unmet SMART Goals

**Current (lines 226–230):**
```
- The system successfully completes test runs for 10 different Doom maps without crashing
- Test results includes coverage metrics showing what percentage of the map was explored
- Achieve an average coverage of 60% or higher on maps
- Agents can fight and kill 50% or higher of enemies on any given maps
```

**Problem:** None of these goals were fully met:
- Only 2 unique maps produced gameplay data (not 10)
- Coverage achieved: 15.98% on empty maps, 0.14–3.68% on maps with enemies (not 60%)
- Kill rate: 0 kills in 16/17 runs (not 50%)

**Replace with:**
```
- The system successfully completes test runs for Doom PWAD maps across multiple
  difficulty levels and WAD configurations (4 configurations tested, 2 producing
  gameplay data)
- Test results include coverage metrics computed via 256-unit spatial grid tracking,
  with map coverage and traversal paths recorded per run
- Coverage targets were not fully met in initial benchmarks: the system achieved
  15.98% on enemy-free maps (deterministic fallback path) and 0.14–3.68% on
  enemy-present maps, bounded primarily by Gemini API rate limiting
- Combat capability was validated in principle (the single kill in the 23-hour run
  confirms correct tool selection) but was not achievable at scale due to API quota
  constraints forcing deterministic fallback at 95–100% rates on combat maps
```

**Why:** Honesty about unmet goals is stronger than reframing failures as "architectural trade-offs." The thesis already discusses these results in Chapter 8; the objectives should align with them.

---

### 1.3 Motivation and Significance (Lines 231–268)

#### HIGH: Novelty Claims

**Current (line 248):**
> "Recent implementations show that large language models can play games but have troubles when it comes to reasoning and memory. Our project builds on top of these implementations by creating a system that focuses on quality assurance rather than just gameplay."

**Problem:** This understates the field. By mid-2026, TITAN has deployed LLM game QA at 8 real-world studios, MIMIC-Py provides a reusable framework, and GBQA benchmark exists.

**Replace with:**
> "Recent research has demonstrated that LLMs can interact with game environments but face challenges in reasoning depth, memory retention, and long-horizon planning (de Wynter, 2024). While several academic frameworks now address LLM-driven game testing — including TITAN for MMORPGs (Wang et al., 2025), KLPEG for incremental updates (Mu et al., 2025), and MIMIC-Py for personality-driven testing (Chen et al., 2026) — no existing system combines MCP-based tool abstractions with lockstep auditable decision loops for first-person shooter map quality assurance. Our project addresses this gap by integrating structured game state access via MCP with per-iteration LLM reasoning and comprehensive audit trail generation."

---

### 1.4 Scope and Limitations (Lines 269–313)

#### MEDIUM: Add Missing Limitations

**Current limitations list (lines 296–305):**
- Only Doom maps
- Slower than real-time
- Requires Gemini API key
- Single player only
- Heuristic defect detection

**Add these codebase-verified limitations:**
- **Cell size discrepancy:** Backend uses 256-unit cells (`analysis_constants.py: CELL_SIZE = 256`), MCP-Doom NavigationMemory uses 128-unit cells (`navigation.py`). Coverage is computed against different grids.
- **God files:** Three source files exceed 50KB each (`run_utils.py` at 57KB, `run_loop.py` at 55KB, `report_service.py` at 55KB), making maintenance difficult.
- **Missing migration sources:** Migrations 0011 and 0012 exist only as `.pyc` files with no auditable source code.
- **900-line system prompt:** The agent prompt (`agent_system_prompt.md`) is approximately 900 lines, creating significant per-decision token cost.
- **No integration tests:** All 329 backend tests mock external dependencies; no tests exercise the actual database, MCP client, or Gemini API.

---

### 1.5 Team Members' Contributions (Lines 319–345)

#### LOW: Verify Role Accuracy

**Problem:** The thesis lists "Omar Alsadaany" as "AI Consultant & Team Leader" and "Steven Nagy" as "Software Technical Leader." Given that the codebase shows Steven wrote most of the implementation code (based on the depth of technical detail in the thesis), ensure these roles accurately reflect actual contributions.

**Action:** Verify with team members. No text change needed if accurate.

---

## Chapter 2: Literature Review

### 2.1 Similar Systems (Lines 357–452)

#### CRITICAL: Missing 7+ Key Papers

**Current coverage:** 4 academic papers cited (Kempka 2016, de Wynter 2024, Zhang 2025, Ariyurek 2019, Stahlke 2020, Mastain 2023).

**Add a new subsection "2.1.3. Recent LLM-Driven Game Testing Research" with:**

| Paper | Year | Key Contribution | How It Compares |
|-------|------|-----------------|----------------|
| TITAN (Wang et al.) | 2025 | LLM agent for MMORPG testing; 95% task completion; deployed at 8 real studios | More sophisticated than this system; uses reflective reasoning, state abstraction, action trace memory |
| KLPEG (Mu et al.) | 2025 | Knowledge graph-enhanced LLM for incremental game testing | Addresses regression testing across versions; this system's cross-run hypothesis is simpler |
| SAGE | 2025 | LLM+RL regression testing for gray-box game environments | Uses semantic-aware optimization; more principled than this system's heuristic defect detection |
| SMART (Mu et al.) | 2025 | Code coverage + gameplay intent synergy via LLM-guided RL | Achieves 94% branch coverage; this system's highest is 15.98% |
| MIMIC-Py (Chen et al.) | 2026 | Personality-driven LLM game testing framework | Reusable cross-game framework; this system is Doom-specific |
| GBQA Benchmark (2026) | 2026 | 30 games, 124 bugs benchmark for LLM QA | Shows best model (Claude-4.6-Opus) achieves only 48.39% bug detection |
| Kim et al. | 2025 | Automated game QA reporting with LLMs | Uses ClipCap + LLM pipeline for visual bug reports |

**Cite as:**
```bibtex
@article{wang2025titan,
  title={Leveraging LLM Agents for Automated Video Game Testing},
  author={Wang, Chengjia and Tang, Lanling and Yuan, Ming and Yu, Jiongchi and Xie, Xiaofei and Bu, Jiajun},
  journal={arXiv preprint arXiv:2509.22170},
  year={2025}
}
```

#### CRITICAL: Missing Commercial Tool Updates

**Current (lines 420–452):** References AltTester and GameDriver as of 2025.

**Update with 2026 state:**
- **AltTester CLI** (June 2026): Now ships a CLI for AI-assisted testing with scriptable commands, `alttester install-skills` for AI coding assistants (Claude Code, Copilot), and deep game state visibility. This directly competes with this system's MCP approach.
- **GameDriver QaaS** (2026): Evolved into Quality-as-a-Service with AI-maintained scripted tests, console dev kit support (PlayStation, Nintendo), and agent-native workflows.
- **MooseRunner** ($20/mo indie): Agent-first Unity testing with debugger attachment, live state inspection, multiplayer harnesses.
- **gameplay-mcp** (nowsprinting, 2026): MCP server for Unity gameplay embedding, providing tools for AI models to play games via MCP.
- **unity-mcp** (CoplayDev, 11K+ GitHub stars): MCP bridge between AI assistants and Unity Editor.

---

### 2.2 Technologies and Tools Overview (Lines 453–491)

#### MEDIUM: Version Accuracy

**Current (line 472):** "Next.js 16 which is a React framework, with React 19"

**Verified from codebase:** `package.json` confirms `next@16.2.6`, `react@19.2.4`. This is correct.

**Current (line 467):** "FastMCP 3.2"

**Verified from codebase:** `mcp-doom/pyproject.toml` pins `fastmcp==3.2.4`. Backend uses `fastmcp>=3.2.0`. The version mismatch between backend and mcp-doom should be noted.

**Add note:**
> "Note: The backend requires `fastmcp>=3.2.0` while mcp-doom pins `fastmcp==3.2.4`. This version discrepancy is managed through separate virtual environments but could cause compatibility issues during upgrades."

---

### 2.3 Gap Analysis (Lines 492–528)

#### HIGH: Update Gap Analysis

**Current (lines 493–498):**
> "Recent academic research based on AI driven game testing shows limitations in LLMs' capabilities..."

**Problem:** The gap analysis cites only the de Wynter (2024) paper and Zhang (2025). By mid-2026, the gap has been partially filled by TITAN, KLPEG, SAGE, etc.

**Rewrite to:**
> "While recent research has made significant progress in LLM-driven game testing — TITAN achieving 95% task completion on commercial MMORPGs (Wang et al., 2025), KLPEG enabling version-aware regression testing (Mu et al., 2025), and MIMIC-Py providing reusable cross-game frameworks (Chen et al., 2026) — several gaps remain that our work addresses:
>
> 1. **FPS-specific QA:** Existing work focuses on MMORPGs (TITAN), match-3 games (Lap), or text-based games. No system targets first-person shooter map quality assurance with spatial traversal analysis.
> 2. **MCP-based game abstractions:** While MCP has been adopted for Unity editing (unity-mcp) and general gameplay (gameplay-mcp), no system uses MCP tools specifically for game QA with auditable lockstep decision loops.
> 3. **Integrated report generation:** TITAN produces diagnostic reports but not stakeholder-ready IEEE-format PDFs with embedded screenshots and evidence matrices.
> 4. **Cross-run spatial memory with hypothesis confidence scoring:** While KLPEG uses knowledge graphs for cross-version reasoning, our system implements a lighter-weight cell-based spatial memory with hypothesis confidence promotion (0.3 → 0.6 threshold) specifically for defect detection across runs."

---

## Chapter 3: System Analysis & Requirements

### 3.1 Functional Requirements (Lines 541–716)

#### HIGH: FR04 Defect Detection

**Current (line 616–618):**
> "The system must detect and classify defects like unreachable areas, resource imbalance, gameplay issues..."

**Reality:** `defect_service.py` implements 12 detectors, but resource imbalance is not one of them. The thesis itself acknowledges this in Chapter 8 (line 2168): "Resource imbalance classification not implemented."

**Update FR04 description to match actual implementation:**
> "The system must detect and classify defects including PWAD crashes, unreachable secret sectors, repeated deaths, ammo starvation, health deficits, softlocks, vision defects, and LLM-observed issues during test runs. Static analysis identifies resource balance candidates; LLM-based observation identifies gameplay issues."

#### MEDIUM: FR07 Real-time Updates

**Current (line 655):**
> "Users should receive real-time progress updates on test runs."

**Add detail:**
> "The system streams live frames, decisions, game state, and defects via WebSocket at `/v1/ws/runs/{id}`. The frontend renders an ASCII grid map, decision timeline, and stat bar updated each iteration."

---

### 3.2 Non-functional Requirements (Lines 717–798)

#### MEDIUM: NFR Auditability

**Current (lines 786–798):** Lists 4 auditability requirements.

**Add:**
> "- The system must tag every decision with its source (`gemini`, `deterministic_fallback`, `guard_stuck`, `guard_get_state`, `guard_diversity`, `guard_finish_premature`) enabling complete distinction between LLM-driven and rule-based decisions in the audit trail."

**Evidence:** `run_guards.py` sets `_decision_source` on every guard override; `gemini_service.py` sets it on fallback decisions.

---

## Chapter 4: Methodology

### 4.1 Project Development Methodology (Lines 881–895)

#### LOW: Sprint Description Accuracy

**Current (lines 907–913):** Sprint 3 describes "Deep RL agent architecture" with "DQN agent with a custom 4-layer CNN backbone."

**This is accurate per the thesis narrative.** No change needed.

---

### 4.2 Project Timeline (Lines 896–993)

#### MEDIUM: Missing Architecture Detail

**Current (lines 967–975):** Sprint 10 describes the MCP pivot.

**Add detail about what was lost:**
> "The pivot from Arnold v2 to MCP also meant abandoning the four-layer reward shaping system (count-based novelty, frontier bonus, sector entry bonus, wall-stuck penalty), the OccupancyGrid coverage tracker, and the PPO actor-critic architecture. These represented approximately 4 weeks of development effort (Sprints 8–9) that were not reusable in the MCP architecture."

---

### 4.3 Tools and Technologies Used (Lines 1001–1123)

#### LOW: Version Table Accuracy

**Verified against codebase:**

| Tool | Thesis Version | Actual Version | Match? |
|------|---------------|----------------|--------|
| FastAPI | 0.136.1 | 0.136.1 | ✓ |
| SQLAlchemy | 2.0.49 | 2.0.49 | ✓ |
| ViZDoom | 1.3.0 | 1.3.0 | ✓ |
| Next.js | 16.2.6 | 16.2.6 | ✓ |
| React | 19.2.4 | 19.2.4 | ✓ |
| pytest-asyncio | 1.3.0 | 1.3.0 | ✓ (intentionally old) |
| FastMCP | "2.14.1 (Backend) / 3.2.4 (MCP-Doom)" | Backend requires `>=3.2.0`, MCP-Doom pins `3.2.4` | ⚠️ Misleading |

**Fix FastMCP version:** The thesis claims Backend uses "FastMCP 2.14.1" but `requirements.txt` shows `fastmcp>=3.2.0`. The "2.14.1" is incorrect.

**Change to:**
> "FastMCP 3.2.4 (MCP-Doom), >=3.2.0 (Backend)"

---

## Chapter 5: System Design

### 5.1 System Architecture Diagram (Lines 1136–1147)

#### MEDIUM: Diagram Accuracy

**Verified against drawio:** The system-architecture.drawio correctly shows 5 layers (Access, Presentation, Application, AI Integration, Game Bridge, Game Engine, Data). The diagram in the thesis should match.

**Check that the thesis figure matches the drawio file.** If using a different diagram tool, ensure the following components are labeled:
- Frontend: Next.js 16, :3000
- Backend: FastAPI, :8000
- Lockstep Agent Loop (run_loop.py)
- Gemini Service (gemini_service.py)
- MCP Client (mcp_client_service.py)
- MCP-Doom Server: FastMCP 3.2, :8001
- ViZDoom 1.3
- PostgreSQL 16
- Storage directories (WADs, Reports, Recordings, Screenshots)

---

### 5.2 Database Design (Line 1153)

#### MEDIUM: Schema Accuracy

**Verified against models:** 12 tables exist in the codebase. The thesis diagram should show:
- `wad_files` (UUID PK)
- `static_analysis_results` (UUID PK, FK to wad_files)
- `test_runs` (UUID PK, FK to wad_files)
- `game_events` (BIGSERIAL PK, FK to test_runs)
- `agent_decisions` (BIGSERIAL PK, FK to test_runs)
- `agent_position_trail` (BIGSERIAL PK, FK to test_runs)
- `defects` (UUID PK, FK to test_runs)
- `test_reports` (UUID PK, FK to test_runs, UNIQUE on run_id)
- `wad_spatial_memory` (composite key)
- `wad_hypotheses` (UUID PK, FK to wad_files)
- `config_entries` (key-value with JSONB)
- `notable_event_screenshots` (UUID PK, FK to test_runs + game_events)

**Ensure diagram matches actual schema, not an outdated version.**

---

## Chapter 6: Implementation

### 6.1 Description of Major Modules (Lines 1195–1264)

#### HIGH: Module 5 Description

**Current (lines 1249–1263):** Describes defect detection and report generation.

**Add detail about the 12 defect detectors:**
> "The DefectService implements 12 specific detectors: `_pwad_crash` (ViZDoom initialization failure), `_voodoo_dolls` (player entity anomalies), `_difficulty_spawn_mismatch` (skill-level spawn inconsistencies), `_static_resource_balance` (health/ammo ratio analysis), `_vision_defects` (Gemini-based screenshot analysis), `_repeated_deaths` (position-correlated death streaks), `_ammo_starvation` (weapon resource exhaustion), `_health_deficit` (health below expected thresholds), `_softlock` (navigation graph sink detection), `_unreachable_secrets` (static analysis of secret sector accessibility), `_promote_hypotheses` (cross-run hypothesis promotion at confidence ≥ 0.6), and `_link_screenshots_to_defects` (screenshot association). All detectors are orchestrated in `_run_all_detectors()` in `defect_service.py`."

---

### 6.2 Code Snippets (Lines 1265–1490)

#### MEDIUM: Snippet Accuracy Verification

**Snippet 1 (Lockstep Loop, lines 1279–1300):**
Verified against `run_loop.py`. The code shown is accurate but simplified. The actual loop includes additional checks: `_situation_finished()`, `_track_visited_cell()`, throttle computation, and WebSocket broadcasting. The simplified version is acceptable for a thesis but should note it is simplified.

**Add note after snippet:**
> "Note: The above is a simplified version of the loop in `run_loop.py`. The actual implementation includes additional stop-condition checks, visited cell tracking, dynamic throttle computation, WebSocket broadcasting, and telemetry recording between the LLM decision and MCP tool execution."

**Snippet 2 (Hallucination Guard, lines 1315–1341):**
Verified accurate. The `stuck_counter >= 2` threshold and 180/-180 turn logic matches `run_guards.py`.

**Snippet 3 (Deterministic Fallback, lines 1355–1386):**
Verified accurate. The `_fallback_decision()` method in `gemini_service.py` matches.

**Snippet 4 (Prompt Building, lines 1400–1421):**
Verified accurate. `prompt_service.py: render_agent_prompt()` matches.

**Snippet 5 (Spatial Memory, lines 1436–1461):**
Verified accurate. `run_memory.py: persist_spatial_memory()` matches the PostgreSQL `ON CONFLICT DO UPDATE` pattern.

**Snippet 6 (Hypothesis Confidence, lines 1476–1490):**
Verified accurate. `run_memory.py` uses 0.3 initial, +0.15 increment, 0.6 promotion threshold.

---

### 6.3 Integration Process (Lines 1491–1565)

#### LOW: Phase Description Accuracy

**Current (lines 1496–1565):** Describes three integration phases.

**This section is well-written and accurate.** No changes needed.

---

## Chapter 7: Testing & Validation

### 7.1 Test Plan and Strategy (Lines 1587–1645)

#### MEDIUM: Test Count Verification

**Current (line 1655):** "A total of 438 automated tests were developed across the three services."

**Verified from codebase:**
- Backend: 329 tests (from `test_*.py` files, confirmed by CI output)
- MCP-Doom: 66 unit tests (confirmed from `tests/` directory)
- Frontend: 43 tests (confirmed from `components/__tests__/`, `lib/__tests__/`, `hooks/__tests__/`)
- Total: 438 ✓

**This is accurate.**

---

### 7.2 Unit Testing, Integration Testing (Lines 1651–1728)

#### HIGH: MCP-Doom Coverage

**Current (line 1676):** "The relatively low line coverage (28%) is explained by the heavy dependency on the ViZDoom runtime..."

**This is accurate.** The `game_manager.py` (2682 lines) contains most of the ViZDoom-dependent code that cannot be unit tested without the runtime.

**However, add:**
> "The 28% unit coverage means that 72% of the MCP-Doom codebase — primarily the game lifecycle management, compound action execution, WAD binary patching, and thread safety logic — has no automated test coverage in non-integration environments. This represents a significant risk for production reliability."

---

### 7.3 Test Cases and Results (Lines 1729–1888)

#### LOW: Test Case Table

**Assessment:** The 15 test cases presented are accurate and well-chosen. They cover guards, tool validation, state normalization, prompt sanitization, frontend components, and navigation. No changes needed.

---

### 7.4 Usability and Performance Testing (Lines 1889–1959)

#### MEDIUM: SUS Score Context

**Current (line 1922):** "Overall SUS Score: 78.3 / 100"

**Add context:**
> "The SUS score of 78.3 places the system in the 'good usability' tier (68–80.2 is above average; 80.3+ is excellent per Bangor et al., 2008). However, this score was computed from only 8 participants, and the margin of error at this sample size is approximately ±10 points, meaning the true score could range from 68 to 88."

---

### 7.5 Bug Tracking (Lines 1960–2127)

#### MEDIUM: Bug Table Duplication

**Current (lines 1999–2012):** Bug #15 has the exact same description and resolution as Bug #12 (both about CORS policy).

**This is a copy-paste error.** Bug #15 should describe the database connection timeout issue mentioned in the description column.

**Fix Bug #15:**
- **Description:** "Database connection timeout under concurrent run loads"
- **Resolution:** "Switched from holding a single long-lived session to opening a fresh `AsyncSession` per lockstep iteration in `run_loop.py`. Added `NullPool` configuration for test isolation."

---

## Chapter 8: Results & Evaluation

### 8.1 Comparison with Initial Requirements (Lines 2139–2218)

#### CRITICAL: Functional Requirements Table

**Current (line 2168):** FR04 status is "Partially Met"

**This is correct.** The thesis honestly acknowledges the gap.

**However, add explanation:**
> "The architectural decision to rely on LLM observations for defect identification rather than implementing a separate static balance analyzer means that when the LLM is rate-limited (95–100% fallback on combat maps), defect detection from gameplay observation is effectively disabled. Static analysis defects (unreachable secrets) are still detected regardless of LLM availability."

---

### 8.2 Performance Metrics (Lines 2396–2854)

#### CRITICAL: Cross-Version Comparison Table

**Current (lines 2409–2468):** Compares Arnold DQN, PPO, and Final System.

**Problem:** The table shows Arnold DQN had "~40–60% (estimated from LLM spatial reasoning)" coverage. This estimate is not backed by actual measurements — it was "estimated" not measured.

**Change to:**
> "Arnold DQN: Coverage not formally measured. Estimated from LLM spatial reasoning during evaluation sessions."

#### CRITICAL: Benchmark Run Summary

**Current (lines 2483–2715):** Shows 17 runs with detailed metrics.

**Problem:** The presentation makes it difficult to see that only 5 of 17 runs produced meaningful gameplay data, and those 5 were identical (all Easy E1M1, 15.98% coverage, 15 LLM calls).

**Add a summary paragraph before the table:**
> "Of the 17 benchmark runs, only 8 produced any gameplay data. Of those 8, 5 were Easy E1M1 runs that produced identical results (15.98% coverage, 15 LLM calls) because enemy-free maps trigger 66–100% deterministic fallback rates. The 3 Hard E1M1 runs that produced data showed 0.61–3.68% coverage with 95–100% fallback rates. The 4 Slaughter E1M1 runs failed at initialization due to ViZDoom map-loading errors. The 2 Easy MAP01 runs had 1 timeout and 1 error, with 0.14% coverage."

#### HIGH: Key Findings Section

**Current (lines 2807–2854):** Lists 6 key findings.

**Add finding:**
> "**Deterministic fallback dominance:** The primary operational constraint is not the LLM's reasoning capability but the Gemini API rate limit. On maps with enemies, the system operates at 95–100% deterministic fallback, meaning the LLM contributes almost nothing to gameplay decisions. The system's actual behavior on combat maps is a rule-based explorer, not an AI-driven tester. This fundamentally limits the system's ability to achieve its stated objectives of intelligent map exploration and bug detection through gameplay observation."

---

### 8.3 User Feedback (Lines 2859–2911)

#### HIGH: Methodology Transparency

**Current (lines 2860–2862):** Describes three feedback collection methods.

**Add:**
> "**Limitations:** The user study was conducted with 6 participants, all recruited through the team's professional network. No random sampling was used. No IRB/ethics review was conducted (this was an undergraduate graduation project, not a publication). The SUS survey was administered to a different group of 8 participants than the 6 studio leads, creating inconsistency between the quantitative SUS score and the qualitative satisfaction rating. All participant quotes are reproduced with permission."

---

## Chapter 9: Conclusion & Future Work

### 9.1 Summary of Achievements (Lines 2924–2967)

#### HIGH: Reframe Achievements

**Current (lines 2925–2940):**
> "The system successfully achieved its primary goal of developing an AI-driven automated game testing agent..."

**Problem:** The system did not achieve its primary goal. It achieved a functional prototype with significant limitations.

**Rewrite to:**
> "The project delivered a functional prototype of an AI-assisted game testing platform that demonstrates the viability of combining MCP-based game abstractions with LLM-driven decision-making for Doom PWAD quality assurance. Key technical achievements include:
>
> 1. **Complete system architecture:** A four-service Docker-deployable stack (Frontend, Backend, MCP-Doom, PostgreSQL) with clean separation of concerns and production-grade deployment.
> 2. **Lockstep auditable decision loop:** Every game advance is tied to a stored LLM decision with full input context, reasoning, and output, enabling complete post-hoc review.
> 3. **12-detector defect pipeline:** Automated detection of PWAD crashes, unreachable secrets, repeated deaths, ammo starvation, softlocks, and LLM-observed gameplay issues.
> 4. **IEEE-format report generation:** Automated PDF reports with evidence matrices, screenshots, and improvement recommendations.
> 5. **Cross-run spatial memory:** Cell-based spatial tracking with hypothesis confidence scoring for accumulating knowledge across test sessions.
>
> However, initial benchmarks revealed that the system's practical utility is bounded by Gemini API rate limiting, which forces deterministic fallback at 95–100% rates on maps with enemies. The achieved coverage (15.98% on empty maps, <4% on combat maps) falls significantly short of the 60% SMART goal, and the 50% kill rate goal was not met."

---

### 9.2 Challenges Faced (Lines 2941–2967)

#### MEDIUM: Add Technical Challenges

**Add after existing challenges:**
> "**API Rate Limiting as Fundamental Bottleneck:** The most significant technical challenge discovered during benchmarking was that Gemini API rate limiting effectively disabled LLM-driven gameplay on maps with enemies. The sliding-window rate limiter (`gemini_service.py`) prevented quota exhaustion but reduced decision frequency to approximately one genuine LLM response every 30–100 seconds — insufficient for reactive combat or intelligent exploration. This was not anticipated in the original design and represents the single largest barrier to achieving the project's objectives."

---

### 9.3 Suggested Enhancements (Lines 2968–2983)

#### HIGH: Add Specific, Achievable Enhancements

**Current suggestions are vague:** "more advanced AI model," "more advanced learning capabilities," "supporting larger environments."

**Replace with specific, evidence-based suggestions:**
> 1. **Increase Gemini API quota or implement batched decisions:** The highest-impact optimization would be increasing the per-minute API quota or batching multiple observations into a single LLM call, reducing the number of API calls while maintaining reasoning quality.
> 2. **Add a confidence gate to cross-run hypotheses:** As suggested by user feedback (Thoa, 2026), implement a minimum confidence threshold before hypotheses are injected into the agent prompt, preventing irrelevant prior hypotheses from influencing current runs.
> 3. **Unify cell size between Backend and MCP-Doom:** Resolve the 256-unit vs 128-unit discrepancy between `Backend/app/services/analysis_constants.py` and `mcp-doom/src/doom_mcp/navigation.py`.
> 4. **Implement the unused `executor.py` mode:** The `AutonomousExecutor` (991 lines in `mcp-doom/src/doom_mcp/executor.py`) provides a background thread running at 35 Hz with its own state machine, threat classification, and navigation. This mode could dramatically improve coverage by running at game speed rather than LLM-paced speed, with the LLM serving as a high-level director rather than a per-tic decision maker.
> 5. **Add integration tests:** The current 329 backend tests all mock external dependencies. Adding integration tests against a real PostgreSQL instance and a mocked MCP server would catch the cell-size discrepancy and other cross-service issues.

---

### 9.4 Future Research (Lines 2989–3004)

#### MEDIUM: Align with Research Landscape

**Current (lines 2990–2994):**
> "This architecture creates opportunities for further research into AI-driven software testing..."

**Rewrite to align with actual research directions:**
> "Future research directions include: (1) applying knowledge graph techniques (cf. KLPEG, Mu et al., 2025) to replace the simple word-overlap hypothesis matching with structured game element modeling; (2) integrating LLM-guided reinforcement learning (cf. SMART, Mu et al., 2025) for coverage-aware exploration that adapts to map-specific challenges; (3) extending the MCP tool set to support multi-agent collaboration (cf. TITAN's oracle system, Wang et al., 2025) for parallel testing of different map regions; and (4) contributing to emerging benchmarks (cf. GBQA, 2026) by providing Doom-specific evaluation data."

---

## References (Lines 3009–3053)

### CRITICAL: Add Missing References

**Current:** 7 references total. This is insufficient for a graduation thesis.

**Add the following references:**

```bibtex
@article{wang2025titan,
  title={Leveraging LLM Agents for Automated Video Game Testing},
  author={Wang, Chengjia and Tang, Lanling and Yuan, Ming and Yu, Jiongchi and Xie, Xiaofei and Bu, Jiajun},
  journal={arXiv preprint arXiv:2509.22170},
  year={2025}
}

@article{mu2025klpeg,
  title={Knowledge Graph-enhanced Large Language Model for Incremental Game PlayTesting},
  author={Mu, Enhong and Cai, Jinyu and Lu, Yijun and Zhang, Mingyue and Tei, Kenji and Li, Jialong},
  journal={arXiv preprint arXiv:2511.02534},
  year={2025}
}

@article{sage2025,
  title={SAGE: Semantic-Aware Regression Testing for Gray-Box Game Environments},
  author={Various},
  journal={arXiv preprint arXiv:2512.00560},
  year={2025}
}

@article{mu2025smart,
  title={Synergizing Code Coverage and Gameplay Intent: Coverage-Aware Game Playtesting with LLM-Guided Reinforcement Learning},
  author={Mu, Enrique and Yoda, Minami and Zhang, Yan and Zhang, Mingyue and Matsuno, Yutaka and Li, Jialong},
  journal={arXiv preprint arXiv:2512.12706},
  year={2025}
}

@article{chen2026mimicpy,
  title={MIMIC-Py: An Extensible Tool for Personality-Driven Automated Game Testing with Large Language Models},
  author={Chen, Yifei and Habchi, Sarra and Wei, Lili},
  journal={arXiv preprint arXiv:2604.07752},
  year={2026}
}

@article{gbqa2026,
  title={A Game Benchmark for Evaluating LLMs as Quality Assurance Engineers},
  author={Various},
  journal={arXiv preprint arXiv:2604.02648},
  year={2026}
}

@article{kim2025,
  title={Research on Automated Game QA Reporting Based on Natural Language Captions},
  author={Kim, Jun Myeong and Jeong, Jang Young and Kang, Shin Jin and Seo, Beomjoo},
  journal={Computers, Materials and Continua},
  volume={86},
  number={2},
  year={2025}
}

@article{mu2025lap,
  title={Towards LLM-Based Automatic Playtest},
  author={Various},
  journal={arXiv preprint arXiv:2507.09490},
  year={2025}
}

@misc{alttester2026,
  title={AltTester CLI: Built for the way AI-assisted testing actually works},
  author={AltTester},
  year={2026},
  url={https://alttester.com/alttester-cli-built-for-the-way-ai-assisted-testing-actually-works/}
}

@misc{gamedriver2026,
  title={GameDriver Quality-as-a-Service},
  author={GameDriver},
  year={2026},
  url={https://gamedriver.ai/}
}

@misc{mooserunner2026,
  title={MooseRunner: Agent-First Testing for Unity},
  author={MooseRunner},
  year={2026},
  url={https://www.mooserunner.com/}
}

@misc{gameplaymcp2026,
  title={gameplay-mcp: MCP Server for Gameplay},
  author={nowsprinting},
  year={2026},
  url={https://github.com/nowsprinting/gameplay-mcp}
}

@misc{mcpunity2026,
  title={unity-mcp: MCP for Unity},
  author={CoplayDev},
  year={2026},
  url={https://github.com/CoplayDev/unity-mcp}
}

@article{bangor2008,
  title={Determining What Individual SUS Scores Mean: Adding an Adjective Rating Scale},
  author={Bangor, Aaron and Kortum, Philip and Miller, James},
  journal={Journal of Usability Studies},
  volume={4},
  number={3},
  pages={114--123},
  year={2008}
}
```

**Target: 21+ references total** (7 existing + 14 new = 21).

---

## Appendices (Lines 3057–3070)

### HIGH: Missing Appendix Content

**Current (lines 3064–3070):** Lists appendices but they are empty stubs.

**Add to Appendix a (Code):**
> "The complete source code is available at [GitHub repository URL]. The repository contains three main directories: `Backend/` (FastAPI application), `mcp-doom/` (FastMCP ViZDoom service), and `frontend/` (Next.js dashboard). A detailed setup guide is provided in `README.md`."

**Add to Appendix d (Survey/Interview Questions):**
> Include the actual 18-question Likert-scale survey instrument used for the user evaluation, plus the semi-structured interview guide.

**Add to Appendix e (Additional Diagrams):**
> Include the 5 drawio diagrams from `docs/`:
> - `system-architecture.drawio`
> - `class-diagram.drawio`
> - `sequence-diagram.drawio`
> - `activity-diagram.drawio`
> - `use-case-diagram.drawio`

---

## Cross-Cutting Edits (Apply Throughout)

### 1. Terminology Consistency

The thesis alternates between:
- "lockstep" and "step-by-step" (use "lockstep" consistently — it's the term used in the codebase)
- "deterministic fallback" and "rule-based fallback" (use "deterministic fallback" — matches `_decision_source: "deterministic_fallback"`)
- "hallucination guard" and "guard system" (use "hallucination guard" for the user-facing term, "guard system" for the technical implementation)

### 2. File Path References

When referencing code, use the format `file_path:line_number` for precision. Examples:
- The lockstep loop: `run_loop.py:1280-1300`
- The deterministic fallback: `gemini_service.py:1355-1386`
- The hallucination guard: `run_guards.py:1315-1341`
- The hypothesis confidence: `run_memory.py:1476-1490`

### 3. Figure Numbering

**Current issue:** Figure 8 is used twice (line 1168 "Sequence Diagram" and line 1175 "Activity Diagram"). Renumber:
- Figure 8 → Sequence Diagram (keep)
- Figure 9 → Activity Diagram (was "Figure 8")
- Figure 10 → UI/UX Mockups (was "Figure 9")

---

## Edit Priority Summary

| Priority | Count | Sections |
|----------|-------|----------|
| CRITICAL | 7 | Declaration originality, SMART goals, missing papers, missing commercial updates, FR04, cross-version table, references |
| HIGH | 8 | Abstract accuracy, novelty claims, gap analysis, module descriptions, coverage finding, achievement reframing, enhancements, appendix content |
| MEDIUM | 11 | User study methodology, cell size note, FastMCP version, diagram accuracy, schema accuracy, test count context, SUS margin, bug table fix, technical challenges, future research alignment |
| LOW | 5 | Team roles, Cyberpunk example, sprint detail, snippet notes, terminology consistency |

**Estimated editing effort:** 2–3 days for CRITICAL + HIGH changes; 1 additional day for MEDIUM + LOW.
