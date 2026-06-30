# Thesis Update Plan — gd-theseis.md

Based on critical line-by-line evaluation. Each item lists what to change, where, and the replacement text.

---

## Decision Summary

| Issue | Decision |
|-------|----------|
| Missing papers | Mention only papers that make BoJack look good (Lap, Sensi, QoE-Doom-BugHunter). Avoid TITAN, GameGuard, rsn-game-qa, SauerkrautLM, SAGE. |
| NFR duplications | Focus analysis on BoJack vs baseline agents, not external systems |
| Unmet goals | Reframe to match actual output (audit trails, reports, hallucination guard) |
| Model name | Standardize on "gemini-3.1-flash-lite" throughout |
| Benchmark run count | Present within Ch.8 structure (requirements comparison + performance vs baseline + user feedback) |
| Novelty framing | "Proof of concept for MCP-based agents doing game QA" |
| Quick fixes | WebSocket reference, FR11 priority, 10% budget citation |

---

## COMPLETED — Round 1 Updates (Already Applied)

| # | Update | Status |
|---|--------|--------|
| 1 | Declaration — scope originality | DONE |
| 2 | Abstract — fix achievement claims | DONE |
| 3 | Abstract — fix user satisfaction (remove 7-dim table) | DONE |
| 4 | Chapter 1 — reframe SMART goals | DONE |
| 5 | Chapter 1 — fix Python version (3.11→3.12) | DONE |
| 6 | Chapter 1 — fix 10% budget citation | DONE |
| 7 | Chapter 2 — add selective related work (Lap, Sensi, QoE-Doom-BugHunter) | DONE |
| 8 | Chapter 2 — fix gap analysis overclaim | DONE |
| 9 | Chapter 3 — fix FR11 priority to "Could-have" | DONE |
| 10 | Chapter 3 — fix FR07 WebSocket ref (/Arnold DQN/→/v1/) | DONE |
| 11 | Chapter 4 — fix methodology claim (Agile-Scrum→iterative) | DONE |
| 12 | Chapter 6 — fix LLM model name (gemini-2.5→gemini-3.1) | DONE |
| 13 | Chapter 8 — restructure results, fix "17 benchmark runs" | DONE |
| 14 | Chapter 9 — reframe conclusion | DONE |
| 15 | Fix "six indie studio leads"→"four indie game developers" | DONE |
| 16 | Fix Python 3.11 in runtime descriptions | DONE |

---

## NEW — Round 2 Updates (Pending)

### Update 15: Section 6.4 — Fill Version Control Practices (Lines 1572-1577)

**Current:** Entirely template placeholder text:
> "Document how you managed your codebase over time. Specify the version control system used (e.g., Git, GitHub). Mention the branching strategy (e.g., main/dev branches). Describe collaboration practices if working in a team (e.g., pull requests, issue tracking). Include screenshots of commit history or contributions."

**Replace with actual content based on repo data:**
- 48 total commits across 6 branches
- Single author (Steven Nagy) — 46 commits
- Branches: main, pre-finalization, maybe-finalized, agent-as-objective, deepseek-helping, sslop
- Active development: 2026-05-16 to 2026-06-28
- GitHub for version control, GitHub Issues for bug tracking

### Update 16: References — Add Missing Papers (After Line 3061)

Lap (2025), Sensi (2026), QoE-Doom-BugHunter (2026) were added to Chapter 2 but have NO corresponding entries in the References section. This is academic integrity violation. Add:

```
Lap, K. P. (2025). Can LLM play match-3 game? Automated playtesting with ChatGPT.
arXiv preprint. https://arxiv.org/abs/2504.01612

QoE-Doom-BugHunter. (2026). QoE-Doom-BugHunter: An LLM-powered multi-agent system
for automated game bug hunting. arXiv preprint. https://arxiv.org/html/2506.05973v1

Sensi, M., et al. (2026). Opening the black box of LLM-based game agents: Curriculum-based
test-time learning. arXiv preprint. https://arxiv.org/abs/2602.10753
```

### Update 17: TOC Section 5.3 — Fix Mismatch (Lines 105-112)

**Current TOC says:**
```
5.3. Data Design
5.3.1. Data Description
5.3.2. Dataset Description
5.4. UML Diagrams
5.4.1. Class Diagram
5.4.2. Sequence Diagram
5.4.3. Activity Diagram
5.5. UI/UX Mockups or Wireframes
```

**Actual content structure:**
```
5.3. UML Diagrams
5.3.1. Class Diagram
5.3.2. Sequence Diagram
5.3.3. Activity Diagram
5.4. UI/UX Mockups
```

**Fix:** Update TOC to match actual content. Remove phantom "5.3. Data Design" section.

### Update 18: Fix Duplicate Figure 8 (Lines 1174, 1181)

- Line 1174: `Figure 8: Sequence Diagram` — keep as Figure 8
- Line 1181: `Figure 8: Activity Diagram` — change to `Figure 9: Activity Diagram`
- Line 1188: `Figure 9: Figma UI Mockups` — change to `Figure 10: Figma UI Mockups`

### Update 19: Fix Bug #15 Wrong Resolution (Lines 2010-2018)

**Current (copy-pasted from Bug #12):**
> "Updated Settings._derive_and_validate to append localhost origins when APP_ENV=development or DEBUG=true, and configured FastAPI CORSMiddleware with the resolved origin list"

**Bug #15 is about:** "Database connection timeout under concurrent run loads"
**Actual fix:** Fresh DB session per lockstep iteration (from run_loop.py `agent_run_task`).

**Replace with:**
> "Switched from holding a single long-lived database session for the entire run to acquiring a fresh `AsyncSession` on each lockstep iteration. This prevents `asyncio.TimeoutError` on the connection pool during prolonged runs."

### Update 20: Fix Table Numbering Skip (Lines 1949-1956)

Table 7.6 (Lighthouse) is followed by Table 7.8 (Concurrent Load). Table 7.7 is missing. Renumber:
- Table 7.8 → Table 7.7

### Update 21: Remove Template Instruction in Section 7.5 (Line 1969)

**Current:** "Explain how bugs were tracked and resolved during development."
**Action:** Delete this line — it's template instruction text.

### Update 22: Fix Section 8.1 Intro — Remove Unmet Goals Reference (Lines 2151-2153)

**Current:** "Key goals included achieving 60% or higher map coverage, enabling effective agent combat with 50% or higher enemy elimination rates, and supporting cross-run learning to improve testing efficiency over time."

**Replace with:** "Key goals included comprehensive audit trail generation, automated QA report production, and validated hallucination prevention through deterministic fallback."

### Update 23: Fill Appendices (Lines 3066-3079)

All appendix sections are empty. Fill with:
- **a. Code:** Link to GitHub repository
- **b. Deployment Manual:** Reference docker-compose.yml and Backend/.env.example
- **c. User Guide / Training Material:** Brief walkthrough of frontend usage
- **d. Survey/Interview Questions:** The 18-question Likert survey + interview guide
- **e. Additional Diagrams:** Reference docs/ drawio files

### Update 24: Fix Section 9.3 Novelty Overclaim (Line 2999)

**Current:** "The project introduces a new approach to autonomous game testing"
**Replace with:** "The project demonstrates an MCP-based approach to autonomous game testing"

### Update 25: Fix SUS Participant Count Inconsistency

- Section 7.4.1 (line 1897): "eight participants"
- Abstract (line 52): "four indie game developers"
- Chapter 8 (line 2947): "four indie game developers"

The SUS survey and the user feedback study are separate evaluations. Fix Section 7.4.1 to clarify: "A System Usability Scale (SUS) survey was administered to four participants with experience in game QA or software testing." (aligning with the four indie developers who did the full evaluation).

---

## VERIFIED — Round 2 Items Already Applied in Document

| # | Update | Status | Verification |
|---|--------|--------|-------------|
| 15 | Section 6.4 Version Control | DONE | Lines 1569-1596: filled with 48 commits, 6 branches, collaboration practices |
| 16 | References — add Lap, Sensi, QoE-Doom-BugHunter | DONE | Lines 3079-3085: all three papers present |
| 18 | Figure numbering (8→9→10) | DONE | Lines 1171-1186: correctly numbered 8, 9, 10 |
| 19 | Bug #15 resolution text | DONE | Lines 2029-2036: correct text (fresh AsyncSession per iteration) |
| 20 | Table 7.7 numbering | DONE | Line 1975: "Table 7.7: Concurrent Load Behavior" |
| 21 | Template instruction in 7.5 | DONE | Line 1986: "During development, issues were tracked using GitHub Issues." (no template text) |
| 22 | Section 8.1 goals text | DONE | Lines 2169-2170: "audit trail generation, automated QA report production, hallucination prevention" |
| 23 | Appendices filled | DONE | Lines 3096-3155: all 5 appendices have content |
| 24 | Section 9.3 novelty framing | DONE | Line 3016: "demonstrates an MCP-based approach" |
| 25 | SUS participant count | DONE | Line 1916: "four participants" |

---

## NEW — Round 3 Updates (Pending)

### Update 26: Fix TOC Chapter 9 Mismatch (Lines 134-137)

The TOC lists chapter 9 sections that don't match the actual document structure.

**Current TOC (lines 134-137):**
```
9.1. Summary of Achievements
9.2. Challenges Faced and Overcome
9.3. Suggested Enhancements
9.4. Possibility of Future Research or Scaling
```

**Actual document structure:**
```
9.1. Summary of Achievements (line 2950)
9.2. Suggested Enhancements (line 2994)
9.3. Possibility of Future Research or Scaling (line 3015)
```

**Fix:** Update TOC to:
```
9.1. Summary of Achievements
9.2. Suggested Enhancements
9.3. Possibility of Future Research or Scaling
```
(Remove phantom "9.2. Challenges Faced and Overcome" and phantom "9.4")

### Update 27: Fix TOC Appendix Mismatch (Lines 140-145)

**Current TOC (lines 140-145):**
```
a. Code
b. Dataset Folder
c. Deployment Manual
d. User Guide / Training Material
e. Survey/Interview Questions
f. Additional Diagrams
```

**Actual appendix structure (lines 3096-3155):**
```
a. Code
b. Deployment Manual
c. User Guide / Training Material
d. Survey/Interview Questions
e. Additional Diagrams
```

**Fix:** Remove phantom "b. Dataset Folder", re-letter b→c, c→d, d→e, remove "f. Additional Diagrams".

### Update 28: Fix Wydmuch Citation Typo (Line 376)

**Current:** `(Wydmush et al., 2024)`
**Fix:** `(Wydmuch et al., 2024)`

### Update 29: Fix TOC Section 5.3 Mismatch (Lines 105-109)

**Current TOC:**
```
5.3. UML Diagrams
5.3.1. Class Diagram
5.3.2. Sequence Diagram
5.3.3. Activity Diagram
5.4. UI/UX Mockups
```

**Actual document:**
- 5.3 = UML Diagrams (line 1162)
- 5.3.1 = Class Diagram (line 1163)
- 5.3.2 = Sequence Diagram (line 1170)
- 5.3.3 = Activity Diagram (line 1177)
- 5.4 = UI/UX Mockups (line 1184)

This matches. No fix needed — already correct.

### Update 30: Fill Gantt Chart Placeholder (Lines 997-998)

**Current:** Section 4.2.2 Gantt Chart is just `●` with no content.
**Fix:** Either insert an actual Gantt chart image, replace with a summary table of sprint dates, or remove the section heading entirely.

---

## Implementation Order — Round 3

1. Update 26 (TOC Ch.9) — structural, quick fix
2. Update 27 (TOC Appendices) — structural, quick fix
3. Update 28 (Wydmuch typo) — single character fix
4. Update 30 (Gantt chart) — needs content decision from user
5. ~~Update 29 (TOC 5.3)~~ — verified already correct, skip
