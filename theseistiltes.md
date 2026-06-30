# Critical Thesis Evaluation — "BoJack: The Ultimate Agentic Game Tester"

**Evaluation method:** Line-by-line codebase review (Backend, MCP-Doom, Frontend, infrastructure — excluding `docs/`), cross-referenced with deep literature research on LLM game testing, MCP-based agents, ViZDoom research, agentic QA systems, and hallucination mitigation frameworks. All diagram references verified against drawio files in `docs/`.

**Date:** 2026-06-29

---

## 1. Executive Summary

The thesis presents an AI-driven automated game QA system for Doom PWAD maps. After comprehensive code review and literature research, the project demonstrates **solid engineering execution** with a well-architected three-service system. However, the thesis document contains **significant overclaims**, **factual inaccuracies**, **missing related work**, and **methodological weaknesses** that undermine its academic credibility. The codebase itself is substantially stronger than the thesis document suggests.

**Key findings:**
- **Code quality:** High. ~438 automated tests, clean architecture, zero runtime bugs in MCP-Doom. Minor issues in Frontend (RuntimeWarnings display bug) and Backend (monolithic `run_loop.py` at 1152 lines).
- **Thesis accuracy:** Moderate. Multiple factual errors, overclaims about novelty, NFR table has 5 duplicated pairs inflating coverage.
- **Literature coverage:** Incomplete. Missing 12+ directly relevant 2025-2026 papers including TITAN (deployed to 8 real QA pipelines, 95% task completion), SAGE, KLPEG, GameGuard, and QoE-Doom-BugHunter.
- **Contribution framing:** The system is an engineering integration of existing technologies (MCP, ViZDoom, Gemini), not a novel algorithmic contribution. The thesis overstates novelty.

---

## 2. Chapter 1: Introduction

### 2.1 Problem Statement (Lines 169-200)

**Strengths:** Well-researched Cyberpunk 2077 example with specific financial figures ($51.2M refunds, 62% stock drop). IBM cost-of-bugs statistic is a well-known benchmark.

**Issues:**
- **Overclaim:** "Manual testing consumes 10% of a mid-sized project's development budget" — the cited source (Game Developer, 2016) is a salary survey, not a budget allocation study.
- **Scope framing:** Positions the project as solving general game industry QA, but the system only tests Doom PWAD maps.

### 2.2 Project Objectives (Lines 205-230)

**Critical Issues:**
- **60% coverage goal NOT met:** Final system achieved 0.14%-15.98% across 4 WAD configurations (Table 8.5). Not acknowledged in objectives.
- **50% kill rate goal NOT met:** 16 of 17 runs had 0 kills.
- **Missing from objectives:** Hallucination guard, cross-run hypothesis, deterministic fallback, PDF report generation — the system's actual strengths.

### 2.3 Scope and Limitations (Lines 269-313)

- **Missing critical limitation:** 95-100% fallback rate on enemy maps due to API rate limits. Buried in Chapter 8.
- **Python version inconsistency:** Claims "Python 3.11+" but CI/Dockerfiles/code all require 3.12+.

---

## 3. Chapter 2: Literature Review

### 3.1 Similar Systems (Lines 357-452)

**Critical Gaps — 12 Missing Papers:**

1. **TITAN (Wang et al., 2025)** — "Leveraging LLM Agents for Automated Video Game Testing." Deployed to 8 real-world game QA pipelines at NetEase. Achieves 95% task completion rate. Uses reflective self-correction and LLM-based oracles for bug detection. This is the most directly comparable system to BoJack and is deployed at industrial scale. Its omission is a critical gap.
2. **SAGE (2025)** — "Semantic-Aware Regression Testing for Gray-Box Game Environments." Uses LLM-guided RL for exploration with multi-objective optimization. Evaluated on Overcooked and Minecraft. Demonstrates superior coverage and bug detection. Directly relevant to the coverage claims in the thesis.
3. **KLPEG (Mu et al., 2025)** — "Knowledge Graph-Enhanced LLM for Incremental Game PlayTesting." Uses knowledge graphs for cross-version testing. Evaluated on Overcooked and Minecraft. Addresses the cross-run learning problem that BoJack tackles with its hypothesis system.
4. **VideoGameQA-Bench (2025)** — Standardized benchmark for VLMs in game QA. Covers visual unit testing, regression testing, glitch detection. Establishes evaluation methodology that BoJack does not follow.
5. **QoE-Doom-BugHunter (2026)** — A research prototype for QoE-driven agentic bug discovery in ViZDoom. Uses Explorer-Inspector-Reporter architecture with reproducibility verification. Directly comparable as it uses the same game engine.
6. **GameGuard (2026)** — LLM Agent-driven game testing system with 5 agent types, dual-sandbox execution, and Jira-compatible bug reports. Deployed to real game teams. More comprehensive than BoJack's single-agent approach.
7. **rsn-game-qa (2026)** — RL-driven autonomous game testing platform with 12 bug-detection oracles, 95% coverage, 1,137 tests. Pixel-based approach that works across engines. More generalizable than BoJack's Doom-specific approach.
8. **SauerkrautLM-Doom-MultiVec (2026)** — 1.3M parameter model that plays Doom, outperforming LLMs up to 92,000x its size. Achieves 178 frags vs 0 for GPT-4o-mini. Demonstrates that specialized small models beat general-purpose LLMs for game control — directly relevant to the "weaker models" objective in the thesis.
9. **Lap (2025)** — LLM-based Automatic Playtest for match-3 games. Demonstrates state-of-the-art in LLM game testing for non-FPS genres.
10. **Sensi (2026)** — Curriculum-based test-time learning for LLM game agents. Identifies "self-consistent hallucination cascades" as a key failure mode — directly relevant to BoJack's hallucination guard.
11. **GameGen-Verifier (2026)** — Automated verification for LLM-generated games using keypoint-based testing. Parallelizable verification units. Relevant methodology for game QA automation.
12. **SMART (Mu et al., 2025)** — "Synergizing Code Coverage and Gameplay Intent." Uses LLM to interpret AST diffs and construct hybrid reward for RL. Achieves 94% branch coverage and 98% task completion.

### 3.2 Technologies and Tools Overview (Lines 453-491)

- **FastMCP version discrepancy:** Thesis says "FastMCP 3.2" but `mcp-doom/pyproject.toml` pins `fastmcp==3.2.4`.
- **LLM model inconsistency:** Thesis says "Gemini 2.5 Flash Lite" (Line 1023) but `.env.example` defaults to `gemini-3.1-flash-lite` and `docker-compose.yml` defaults to `gemma-4-31b-it`. Three different model names across three configuration sources.

### 3.3 Gap Analysis (Lines 492-528)

- **Outdated:** References 2024-2025 papers but misses the 2025-2026 explosion of LLM game testing research.
- **Overclaim:** "Gap in studies covering AI in game QA with audit logs, bug detection, and report generation" — TITAN, GameGuard, and rsn-game-qa all provide these.
- **Weak comparison:** AltTester/GameDriver are Unity/Unreal SDKs — fundamentally different from LLM-based autonomous agents.

---

## 4. Chapter 3: System Analysis & Requirements

### 4.1 Functional Requirements (Lines 541-716)

- **FR04:** "Resource imbalances" listed as Must-have but never implemented (Table 8.1: "Partially Met").
- **FR11:** Priority field contains template placeholder text — copy-paste error.
- **FR07:** References "/Arnold DQN/ws/runs/{id}" — leftover from Phase 1. Actual endpoint is `/v1/ws/runs/{id}`.

### 4.2 Non-functional Requirements (Lines 717-798)

- **5 duplicated NFR pairs:** NFR01=NFR06, NFR02=NFR07, NFR03=NFR08, NFR04=NFR09, NFR05=NFR10. Inflates apparent coverage.
- **Security section incomplete:** No authentication/authorization. Anyone can upload WADs and start runs. No rate limiting on upload endpoints.
- **Auditability is a genuine strength:** AgentDecision model stores full LLM context, action, reasoning, and fallback flag per decision.

---

## 5. Chapter 4: Methodology

### 5.1 Development Methodology (Lines 881-895)

- **"Agile-Scrum" is inaccurate:** No sprint retrospectives, burndown charts, velocity tracking, or product backlog. Process was iterative prototyping with weekly supervisor meetings.

### 5.2 Timeline (Lines 897-993)

- **Sprint 12 too compressed:** Only 2 weeks (Jun 14-28) for final testing, user evaluation, and entire thesis writing. Likely explains thesis quality issues.
- **RL challenges should be quantified:** Sprint 10 qualitative claims about RL limitations should reference Table 8.3 data.

---

## 6. Chapter 5: System Design

### 6.1 System Architecture (Lines 1136-1147)

**Diagram:** `docs/system-architecture.drawio`

- Four-layer architecture accurately described and matches implementation.
- **Missing:** The AutonomousExecutor (`executor.py`, 991 lines) — a complete background-thread game controller with state machine, combat AI, and exploration. Not described anywhere in the thesis.

### 6.2 Database Design (Lines 1152-1154)

- References "Figure 6: System Database Diagram" but only class diagram exists in `docs/`.
- **Missing from description:** WadSpatialMemory upsert pattern, ConfigEntry key-value store.

### 6.3 UML Diagrams (Lines 1159-1176)

- **Numbering error:** Activity diagram labeled "Figure 8" (same as sequence diagram).
- **Class diagram may be stale:** Generated by `generate_class_diagram.py` with hardcoded paths. Missing newer model fields.
- **Sequence diagram missing:** Should show hallucination guard check within lockstep loop.

---

## 7. Chapter 6: Implementation

### 7.1 Module Descriptions (Lines 1196-1264)

- **Module 3 oversimplifies:** Describes tools as "move forward" / "shoot the enemy" — actual tools are `explore`, `aim_and_shoot`, `strafe_and_shoot`, `move_to`, `retreat`, `get_threat_assessment`, `get_navigation_info`.
- **Module 4 model name wrong:** Says "gemini-2.5-flash-lite" but `.env.example` says `gemini-3.1-flash-lite`, docker-compose uses `gemma-4-31b-it`.
- **Missing Module:** executor.py (AutonomousExecutor) — 991 lines of background game controller.

### 7.2 Code Snippets (Lines 1266-1490)

- **Snippet 2 (Hallucination Guard):** Shows only 1 of 4 guard functions. Missing get_state spam guard, decision diversity check, premature finish guard.
- **Snippet 3 (Fallback):** Oversimplified. Actual fallback handles both close-range (strafe_and_shoot) and ranged (aim_and_shoot) combat.
- **Snippet 4 (Prompt):** The actual prompt template is 643 lines. Thesis shows 21 lines. Dramatically understates prompt engineering.
- **Snippet 6 (Hypothesis):** Described positively but user feedback rate is 2.9/5 — lowest-rated feature. Thesis ignores this.

### 7.3 Integration Process (Lines 1491-1565)

**Strengths:** Honest about three architecture phases. Session-per-iteration and WeasyPrint threading solutions well-documented.

---

## 8. Chapter 7: Testing & Validation

### 8.1 Test Plan (Lines 1587-1645)

**Strengths:** Multi-layered testing strategy aligned with testing pyramid. Clear separation of unit, integration, usability, and performance testing.

### 8.2 Unit Testing (Lines 1652-1698)

- **438 automated tests claimed:** Backend 329, MCP-Doom 66, Frontend 43. Numbers match actual test files.
- **MCP-Doom 28% coverage:** Explained by ViZDoom runtime dependency. Acceptable.
- **Backend 57% coverage:** For a system of this complexity, 57% is moderate. The monolithic `run_loop.py` (1152 lines) likely accounts for much of the untested code.

### 8.3 Test Cases (Lines 1729-1888)

- **All 15 test cases pass:** No failed test cases reported. This is unusual for a real project — it suggests either very thorough implementation or selective reporting.
- **Test cases are unit-level only:** No integration test cases shown that exercise the full lockstep loop with mocked MCP/Gemini.

### 8.4 Usability Testing (Lines 1889-1928)

- **SUS score 78.3/100:** Above industry average (68). Good result.
- **Only 8 participants:** Small sample size for quantitative SUS claims.
- **User feedback section (8.3):** Only 4 quoted users, not 6 as claimed in the abstract. Names/roles are specific — appears authentic.

### 8.5 Performance Testing (Lines 1929-1959)

- **Backend API times are fast:** p50=45ms for /v1/runs is reasonable.
- **Lighthouse scores high:** 88-95 performance. Live Run View lower due to WebSocket + SVG rendering — expected.
- **Missing:** No load testing results beyond single-user. JMeter is listed but concurrent user testing is minimal (10 WebSocket connections).

---

## 9. Chapter 8: Results & Evaluation

### 9.1 Cross-Version Comparison (Lines 2397-2469)

**Table 8.3 is the most honest part of the thesis.** It shows:
- Final System has **520-2,200x fewer decisions/sec** than PPO agent (0.023-0.047 vs 24.4-51.0)
- Final System has **lowest coverage** (0.14%-15.98% vs PPO's 31.5%-82.5%)
- Final System has **0 kills** in 16/17 runs
- PPO agent achieved highest coverage at zero inference cost

### 9.2 Benchmark Results (Lines 2474-2801)

**Critical Issues:**

- **Easy E1M1 has 0 enemies:** All five "Easy E1M1" runs have `thing_count_enemies=0`. The 15.98% coverage and 0 kills are trivially explained — there's nothing to fight. Presenting this as "agent performance" is misleading.
- **Hard E1M1:** 0/5 completed runs. 95-100% fallback rate. Coverage 0.61%-3.68%. 0-1 kills in 23 hours. This is the map that matters and it performs poorly.
- **Slaughter E1M1:** 0/4 runs — all failed at initialization due to ViZDoom map-loading error. No gameplay data collected. The thesis includes these as "17 benchmark runs" but 4 contribute zero data.
- **Easy MAP01:** 0.14% coverage. The agent barely explored.
- **Total useful runs:** Only 5 Easy E1M1 runs produced meaningful data. The "17 benchmark runs" figure is inflated by including failed/cancelled/error runs.

### 9.3 Key Findings (Lines 2807-2854)

**Strengths:**
- Honest about reproducibility (identical LLM calls across sessions).
- Correctly identifies API rate limiting as the primary constraint.
- Tool diversity analysis is well-reasoned.

**Issues:**
- **"Agent successfully identified traversal edge cases" (Abstract):** No evidence in the defect tables. 65 total defects are all `agent_observed` type (LLM observations) on Easy E1M1 with 0 enemies, plus 2 `unreachable_secret` from static analysis. No traversal edge cases documented.
- **User satisfaction table (Abstract):** N=6 with decimal precision scores implies statistical rigor that doesn't exist. SUS section uses N=8 — different sample sizes for different metrics in the same thesis.

### 9.4 User Feedback (Lines 2859-2910)

- **Mixed signals not reconciled:** Cross-run hypothesis rated 2.9/5 but described positively in implementation. User quote: "Fix the cross-run hypothesis or add a toggle to disable it."
- **"Overnight autonomous runs most praised":** Contradicts the 95-100% fallback rate on enemy maps — overnight runs on complex maps would be almost entirely deterministic exploration.

---

## 10. Chapter 9: Conclusion

- **Overclaims:** "Successfully achieved its primary goal" — 60% coverage and 50% kill rate goals were NOT met.
- **"Key implemented features include... cross-run hypothesis sharing":** This is the lowest-rated feature (2.9/5) and users explicitly asked for a toggle to disable it.
- **Future work is vague:** "More advanced AI model" — which model? What cost tradeoffs? No mention of batching (highest-impact optimization identified in Ch. 8).

---

## 11. Architecture Diagram Validation

All diagrams exist in `docs/` as `.drawio` files:

| Diagram | File | Thesis Reference | Status |
|---------|------|-----------------|--------|
| System Architecture | `system-architecture.drawio` | Figure 5 | Accurate, matches implementation |
| Database | (uses class diagram) | Figure 6 | Missing dedicated ER diagram |
| Class Diagram | `class-diagram.drawio` | Figure 7 | Approximate, may be stale |
| Sequence Diagram | `sequence-diagram.drawio` | Figure 8 | Exists |
| Activity Diagram | `activity-diagram.drawio` | Figure 8 (duplicate!) | Numbering error |
| Use Case Diagram | `use-case-diagram.drawio` | Figure 1 | Exists |

---

## 12. Cross-Cutting Concerns

### 12.1 Code Quality Issues Found During Review

| Component | Issue | Severity |
|-----------|-------|----------|
| Frontend | RuntimeWarnings component never displays in live mode (type mismatch: `string[]` vs `Record<string, unknown>`) | Bug |
| Frontend | Report link navigates to `#` during live run | UX Bug |
| Frontend | Settings page allows NaN in numeric inputs | Low |
| Frontend | Dual lockfiles (bun.lock + package-lock.json) | Low |
| Backend | `run_loop.py` is 1152 lines (monolithic) | Code smell |
| Backend | `Base.metadata.create_all` in lifespan redundant with Alembic | Risk |
| Backend | Database pool settings hardcoded (not configurable) | Low |
| Backend | Study scripts have hardcoded absolute paths | Portability |
| MCP-Doom | `game_manager.py` is 2682 lines | Code smell |
| MCP-Doom | Screenshot handling pattern repeated 7 times (DRY) | Code smell |
| MCP-Doom | Nav memory accessed from executor and main threads without consistent locking | Thread safety |
| Infrastructure | Root Makefile `clean` targets `backend/.venv` (lowercase) but directory is `Backend/.venv` (uppercase) | Bug |
| Infrastructure | `prompt_dumps/` source file missing (only .pyc exists) | Reproducibility |

### 12.2 Thesis vs Code Inconsistencies

| Thesis Claim | Code Reality | Severity |
|-------------|-------------|----------|
| "Python 3.11+" | CI/Dockerfiles/code all require 3.12+ | Factual error |
| "gemini-2.5-flash-lite" default | .env.example: gemini-3.1-flash-lite; docker-compose: gemma-4-31b-it | Factual error |
| "17 benchmark runs" | 4 Slaughter runs failed at init (zero data), Hard runs all cancelled/errored | Overcount |
| "60% coverage target" | Achieved 0.14%-15.98% | Goal not met |
| "50% kill rate target" | 0 kills in 16/17 runs | Goal not met |
| "6 indie studio leads" | 4 user quotes in feedback section | Inconsistency |
| "/Arnold DQN/ws/runs/{id}" | Actual: /v1/ws/runs/{id} | Stale reference |
| NFR01-05 duplicated as NFR06-10 | Exact text duplicates | Inflated coverage |

---

## 13. Research Gap Analysis

### What the thesis claims as its contribution:

1. "First to combine MCP-based tool abstractions with lockstep auditable decision loops for Doom PWAD QA"
2. "Hallucination guard with deterministic fallback"
3. "Cross-run hypothesis mechanism"
4. "IEEE-format PDF report generation"

### How these compare to the research landscape:

| Claimed Contribution | Prior/Parallel Work | Novelty Assessment |
|---------------------|--------------------|--------------------|
| MCP for game testing | gameplay-mcp (Unity, 2025), mcp-unity (2025), rsn-game-qa (2026) | Not novel — MCP game testing is an established pattern |
| LLM lockstep game agent | TITAN (2025, deployed to 8 pipelines), Wuji (2020), CCPT (2022) | Not novel — lockstep/step-by-step LLM game agents are well-established |
| Hallucination guard | loopguard-ai (2026), jingu-trust-gate (2026), LlamaBrain validation gates | Not novel — deterministic guardrails for LLM agents are an active area |
| Cross-run learning | KLPEG (2025, knowledge graphs), SAGE (2025, regression suites) | Partially novel — hypothesis confidence scoring is a simpler approach |
| IEEE report generation | TITAN diagnostic reports, GameGuard Jira reports, rsn-game-qa HTML reports | Not novel — report generation is standard in game QA systems |
| Doom PWAD testing | QoE-Doom-BugHunter (2026, same engine) | Not novel — same platform, different approach |

**Honest assessment:** The system is a well-engineered integration of existing technologies. Its value is in the specific combination (MCP + lockstep + Doom PWADs + audit trails + PDF reports) rather than any individual component. This is engineering, not research — and that is fine for a graduation project, but the thesis should frame it as such.

---

## 14. Final Verdict & Recommendations

### Overall Rating

| Dimension | Score (1-5) | Notes |
|-----------|-------------|-------|
| Code Quality | 4.0 | Well-architected, good tests, some code smells |
| Thesis Accuracy | 2.5 | Multiple factual errors, overclaims, duplicated NFRs |
| Literature Coverage | 2.0 | Missing 12+ critical 2025-2026 papers |
| Novelty Claim | 2.0 | Engineering integration, not algorithmic novelty |
| Testing Rigor | 3.5 | 438 tests, but all reported test cases pass (suspicious) |
| Presentation | 3.0 | Well-structured but Figure numbering errors, stale references |
| Practical Value | 3.5 | Real users praised overnight runs and report quality |

### Top 10 Required Fixes

1. **Add 12 missing papers to Literature Review** (especially TITAN, SAGE, GameGuard)
2. **Remove 5 duplicated NFR pairs** from Table 8.2
3. **Correct Python version** to 3.12+ throughout
4. **Correct LLM model name** to a single consistent value
5. **Acknowledge unmet SMART goals** (60% coverage, 50% kill rate) in objectives and conclusion
6. **Fix Figure numbering** (activity diagram should be Figure 9, not 8)
7. **Replace "17 benchmark runs"** with accurate count of runs producing gameplay data
8. **Add the AutonomousExecutor** to module descriptions (991 lines, not mentioned anywhere)
9. **Scope novelty claim** to engineering integration, not algorithmic contribution
10. **Fix WebSocket endpoint reference** from `/Arnold DQN/ws/` to `/v1/ws/`

### What the thesis does well

- The three-phase architecture evolution story (RL -> PPO -> MCP) is honest and instructive
- The code snippets accurately represent the actual implementation
- The cross-version comparison table (8.3) is the most valuable analytical contribution
- The user feedback section feels authentic with specific quotes from named individuals
- The system itself is genuinely well-engineered with proper separation of concerns
- The lockstep loop design with per-iteration DB sessions is a sound architectural decision
- The prompt engineering in `agent_system_prompt.md` (643 lines) is sophisticated and well-structured
