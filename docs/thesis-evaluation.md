# Thesis Evaluation — "BoJack: The Ultimate Agentic Game Tester"

**PDF**: `docs/GP Thesis - myDOOM.pdf`
**Evaluated**: 2026-06-23
**Score**: 6.5/10 (strong implementation, weak document polish)

---

## P0 — Blocking (thesis will not pass without these)

| # | Issue | Location | Status | Fix |
|---|-------|----------|--------|-----|
| 1 | Chapter 8.1 "Comparison with Initial Requirements" is template text only | Ch 8.1 | ⬜ TODO | Fill with actual requirement-to-implementation mapping |
| 2 | Chapter 8.2 "Performance Metrics" is template text only | Ch 8.2 | ⬜ TODO | Add actual response time, throughput, accuracy metrics from codebase |
| 3 | Section 5.3 "Data Design" is template text ("OPTIONAL: for projects that work with datasets...") | Ch 5.3 | ⬜ TODO | Replace with actual DB schema explanation (4 tables: run, llm_action, memory_entry, run_defect) |
| 4 | Section 5.5 "UI/UX Mockups" is template text only | Ch 5.5 | ⬜ TODO | Add actual frontend screenshots from `frontend/app/page.tsx` |
| 5 | Section 6.4 "Version Control" is template text only | Ch 6.4 | ⬜ TODO | Write about git workflow, branching strategy used |
| 6 | All appendices are empty template text | Appendix A-F | ⬜ TODO | Fill: code snippets, deployment manual, survey questions, diagrams |
| 7 | Gantt chart missing (Section 4.2.2) | Ch 4.2.2 | ⬜ TODO | Create Gantt chart based on Sprint timeline in 4.2.1 |
| 8 | Tools table missing (Section 4.3) | Ch 4.3 | ⬜ TODO | List: Python, FastAPI, SQLAlchemy, Alembic, ViZDoom, MCP, Next.js, etc. |
| 9 | Placeholder text "Showdown with a figure of the use case diagram of ……." | Ch 3, p.26 | ⬜ TODO | Replace with actual use case figure |
| 10 | Figure 2 caption "Figure 2: Use-Case Diagram of ….." — unfinished | Ch 3 | ⬜ TODO | Complete caption |
| 11 | FR11 post-condition "Indicate the priority level..." — template text | Ch 3, FR11 | ⬜ TODO | Write actual post-condition for FR11 |
| 12 | Figure 8 numbered twice (Sequence Diagram p.40 AND Activity Diagram p.41) | Ch 5 | ⬜ TODO | Renumber Activity Diagram as Figure 9 |
| 13 | Bug #15 "Fix Details" is copy-paste from #12 (CORS fix) | Ch 7, Table 7.9 | ⬜ TODO | Write correct fix details for Bug #15 |
| 14 | No conclusion section after evaluation results in Ch 8 | Ch 8 | ⬜ TODO | Add brief analysis/conclusion paragraph |

---

## P1 — High Impact on Grade

| # | Issue | Location | Status | Fix |
|---|-------|----------|--------|-----|
| 15 | Only 13 references — need 25-40 | References | ⬜ TODO | Add: MCP Spec [22], TITAN [8], Orak, modl.ai, MIMIC-Py [7], SAGE [9], VideoGameBench [11], GameSense, lmgame-Bench, Khan [14], Meghji [15], Zhang [17], WeTest [24], ViZDoom GitHub [26], Google GenAI [29] |
| 16 | Ch 2.3 gap analysis doesn't cite TITAN, Orak, modl.ai, QA-Doom-Agents | Ch 2.3 | ⬜ TODO | Expand gap table with 6+ additional competitors |
| 17 | SMART goals from Ch 1 (60% coverage, 50% kill rate) never evaluated in Ch 8/9 | Ch 8/9 | ⬜ TODO | Add honest assessment — goals not met, discuss why |
| 18 | SUS only shows 4/10 standard statements | Ch 7, SUS | ⬜ TODO | Add remaining 6 statements |
| 19 | No defect detection accuracy metrics (true positive rate, false positive rate) | Ch 7/8 | ⬜ TODO | Add precision/recall metrics |
| 20 | No manual testing time comparison | Ch 7/8 | ⬜ TODO | Estimate manual QA time vs automated time |
| 21 | Test count inconsistency: 438 (thesis) vs 591 (docs/chapter-7-testing-validation.md) | Ch 7 | ⬜ TODO | Reconcile — pick one number, explain discrepancy |
| 22 | User survey size inconsistency: "6 indie studio leads" (Ch 1/8) vs "8 participants" (Ch 7 SUS) | Ch 1/7/8 | ⬜ TODO | Clarify: 6 studio leads for interviews, 8 for SUS survey |
| 23 | Ch 9.2 "Suggested Enhancements" is vague | Ch 9.2 | ⬜ TODO | Add specific technical suggestions (e.g., multi-agent orchestration, replay buffer, coverage-guided Fuzzing) |
| 24 | Ch 9.3 "Future Research" is generic | Ch 9.3 | ⬜ TODO | Tie to specific gaps found (e.g., defect detection pipeline, runtime monitoring) |

---

## P2 — Differentiators (good to have)

| # | Issue | Location | Status | Fix |
|---|-------|----------|--------|-----|
| 25 | Ch 6 missing defect detection pipeline description (7 detectors) | Ch 6 | ⬜ TODO | Add section describing: stuck-detection, exit-reduction, damage-without-progress, pickup-regression, backtrack, stuck-loop, death-repetition |
| 26 | Ch 6 missing prompt engineering explanation (273-line agent prompt, 367-line report prompt) | Ch 6 | ⬜ TODO | Explain prompt structure: static briefing, tactical doctrine, tool docs, output format |
| 27 | Ch 6 only shows stuck guard — missing premature-finish and get-state-spam guards | Ch 6 | ⬜ TODO | Add brief descriptions of all 3 guard checks |
| 28 | No comparison with direct ViZDoom competitors (QA-Doom-Agents, QoE-Doom-BugHunter, Inspector) | Ch 2/8 | ⬜ TODO | Add comparison table |
| 29 | Ch 3 use case diagram shows 5 actors but Ch 5 architecture only describes 3-layer system | Ch 3/5 | ⬜ TODO | Ensure consistency between analysis and design |
| 30 | No discussion of the Director mode (experimental) vs lockstep (active) | Ch 6 | ⬜ TODO | Brief mention that Director mode exists but lockstep was chosen |

---

## Code vs Thesis Mismatches

| Thesis Claims | Code Reality | Action |
|---------------|-------------|--------|
| "591 automated tests" (docs) vs "438" (thesis) | Different document versions | Pick one, update all references |
| "gemini-2.5-flash-lite" (Ch 6.1) | Code uses `gemini-3.1-flash-lite` | Update thesis model name |
| "rolling 16-action history" (abstract) | Code uses `SAME_RUN_LEDGER_MAX_CHARS` | Verify actual count in code |
| SMART goal: "60% coverage" | `final_verdict.md`: 9% completion | Must address honestly |
| SMART goal: "50% kill rate" | `final_verdict.md`: 0.34 avg kills | Must address honestly |
| User survey: "6 indie studio leads" (Ch 1/8) | Ch 7 says "8 participants" | Clarify sample sizes |

---

## Diagram Inventory

| Diagram | File | In Thesis? | Quality |
|---------|------|-----------|---------|
| Use Case | `docs/use-case-diagram.drawio` | Yes (Figure 2) | ✅ Good — needs caption fix |
| System Architecture | `docs/system-architecture.drawio` | Yes (Figure 3) | ✅ Excellent — 5-layer, legend, connection labels |
| Sequence | `docs/sequence-diagram.drawio` | Yes (Figure 8) | ✅ Very detailed — 49 messages, may need trimming for page |
| Class | `docs/class-diagram.drawio` | Yes (Figure 7) | ✅ Comprehensive — ~870 lines XML |
| Activity | `docs/activity-diagram.drawio` | Yes (Figure 8 duplicate) | ✅ Detailed — 6 swimlanes, needs renumber to Figure 9 |
| ER Diagram | `docs/diagrams.md` (text only) | Partial | ⚠️ Needs actual diagram |
| Deployment | Missing | No | ❌ Docker architecture not visualized |
| State Diagram | Missing | No | ❌ Run lifecycle not shown |

---

## Chapter Scores

| Chapter | Score | Notes |
|---------|-------|-------|
| Ch 1: Introduction | 7/10 | Good Cyberpunk case study, SMART goals not evaluated |
| Ch 2: Literature Review | 5/10 | Missing MCP, TITAN, Orak, modl.ai, most competitors |
| Ch 3: System Analysis | 7/10 | Good FR/NFR structure, placeholder text remains |
| Ch 4: Methodology | 8/10 | Excellent sprint timeline, missing Gantt + tools table |
| Ch 5: System Design | 6/10 | Good diagrams, template text in 5.3, 5.5 |
| Ch 6: Implementation | 8/10 | Strongest chapter, missing defect pipeline + prompt eng |
| Ch 7: Testing & Validation | 7/10 | Good structure, SUS incomplete, no accuracy metrics |
| Ch 8: Results & Evaluation | 4/10 | 8.1-8.2 are empty templates, user feedback is excellent |
| Ch 9: Conclusion | 6/10 | Honest about pivots, SMART goals never revisited |
| References | 5/10 | Only 13 refs, need 25-40 |
| Appendices | 2/10 | All empty |

---

## Execution Order (Recommended)

### Phase 1: Critical Fixes (1-2 days)
1. Fill Ch 8.1-8.2 with actual results
2. Fill Ch 5.3 with DB schema explanation
3. Fill Ch 5.5 with frontend screenshots
4. Fill Ch 6.4 with version control description
5. Fix all figure numbering
6. Fix placeholder text (Ch 3 caption, FR11)
7. Fix bug tracking copy-paste error

### Phase 2: References & Analysis (1 day)
8. Add 12-15 references to bibliography
9. Expand Ch 2.3 gap analysis
10. Add Ch 2.4 competitive positioning table

### Phase 3: Metrics & Evaluation (1 day)
11. Reconcile test counts (438 vs 591)
12. Reconcile user survey sizes (6 vs 8)
13. Evaluate SMART goals in Ch 8/9
14. Complete SUS (10 statements)
15. Add defect accuracy metrics
16. Add manual testing comparison

### Phase 4: Enrichment (1 day)
17. Add defect detection pipeline to Ch 6
18. Add prompt engineering explanation to Ch 6
19. Add guard system descriptions to Ch 6
20. Fill appendices with actual content
21. Create Gantt chart and tools table
