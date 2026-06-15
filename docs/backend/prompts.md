# Prompt Engineering

Two LLM prompt templates in `Backend/app/prompts/`, rendered via Jinja2.

## 1. Agent System Prompt — `agent_system_prompt.md` (273 lines)

The core prompt presented to Gemini on every lockstep iteration. Built by `PromptService.render_agent_prompt()`.

### Structure

1. **Static Map Briefing** (from static analysis):
   - Map name, estimated difficulty, total monster HP
   - Enemy breakdown by type with counts
   - Health/armor/ammo pickups available
   - Hitscanner percentage
   - Health and ammo ratios
   - Map features: door/lift/teleporter/key counts

2. **Current Input** (dynamic per iteration, sanitized):
   - Game variables: health, armor, ammo, kills, secrets, items, weapon state, selected weapon
   - Nearby objects: filtered to monsters, keys, weapons, powerups, health/armor (capped, IDs hidden)
   - Threat assessment: prioritized enemies with distance, aim angle
   - Navigation info: explored cells, walkable cells, coverage %, suggested direction
   - Depth stats: 7-region depth buffer summary
   - Run memory: same-run action ledger (most recent actions for anti-loop)
   - Cross-run memory: accumulated hypotheses for this WAD+map
   - Lockstep state: consecutive no-progress count, tics used, tics remaining
   - Exploration coverage: visited cells, total cells, percentage

3. **Tactical Doctrine** (priority-ordered):
   - Survival > Threat Elimination > Progression > Collection > Coverage
   - Anti-stuck rules (change strategy if hitting walls)
   - Navigation heuristics (unexplored > cardinal direction > suggested)
   - Weapon selection guide (match weapon to enemy distance/threat)
   - Combat rules (strafe, use cover, prioritize dangerous enemies)
   - Defect reporting format

4. **Guard System**:
   - Describes why actions might be modified
   - Explains guard_modified/guard_reason fields

5. **Tool Documentation**:
   - Describes all available MCP tools with parameters
   - Recommends compound actions (aim_and_shoot, move_to, explore) over raw take_action

### Sanitization (`_sanitize_prompt_value`)

- JSON strings preserved as-is
- Regular strings passed through
- int/float converted to string
- None→"None", bool→"true"/"false"
- Lists/dicts JSON-serialized with indent
- Object IDs hidden from LLM for `move_to`/`aim_and_shoot` targets

### Dynamic Tactical Directives (`_build_dynamic_tactical_directives`)

- **Low health** (HP < 30): prioritize health pickups, retreat from threats
- **No ammo**: switch to chainsaw/fist, search for ammo
- **Combat active**: focus on threat elimination, use cover
- **Stuck**: change direction, try new strategy

## 2. Report Generation Prompt — `report_generation_prompt.md` (367 lines)

Used by `ReportService._call_gemini_or_fallback()` to generate PDF narratives.

### 14 QA Sections

1. **Geometry & Structural Analysis** — map layout, architecture, exploitability
2. **Technical Performance** — rendering, framerate, compatibility
3. **Gameplay Flow & Progression** — difficulty curve, monster placement flow
4. **Combat Design & Balance** — encounter quality, ammo/health balance
5. **Itemization & Resource Placement** — pickup placement fairness
6. **Enemy & AI Behavior** — monster pathfinding, infighting, stuck analysis
7. **Navigation & Wayfinding** — signposting, key/door logic
8. **Secrets & Exploration** — secret placement, hinting
9. **Multiplayer & Co-op** — spawn balance, weapon placement
10. **Performance & Optimization** — visplane counts, seg limits
11. **Speedrunning Suitability** — route viability, skips
12. **Visual & Aesthetic Quality** — texture alignment, lighting
13. **Audio & Sound Design** — sound propagation
14. **Accessibility & Difficulty** — skill level tuning, fairness

### Input Data

- Run summary: WAD info, map, difficulty, outcome, duration, kills/deaths/items/secrets
- Static analysis snapshot: enemy/item/weapon counts, spawn summaries, map features
- Metrics: action/LLM call counts, benchmarks (LLM/MCP latency percentiles)
- Defects: all detected defects with severity/type/description
- Notable events: kills, deaths, pickups, damage events with tick/position
- Decision trace: last N decisions with tool, reasoning, source
- Evidence matrix: low/high confidence findings per section

### Output Contract

LLM must return valid JSON matching the 14-section structure. `_parse_report_json()` uses multi-strategy parsing:
1. Direct JSON parse
2. JSON extraction from code blocks (` ```json `)
3. Brace-pair extraction from surrounding text
4. Deterministic fallback if all parsing fails

### Fallback (`_deterministic_report()`)

When Gemini is unavailable (no API key, rate limited, or error), generates a structured report with:
- Executive summary stating this is a deterministic fallback
- Section-by-section analysis based on available metrics
- Defect listing from detected defects
- Pass/fail summary calculated from defect severity thresholds
- Recommendations based on map statistics

### Voice Sanitization (`_sanitize_report_voice()`)

Removes agent-blame phrases from LLM output:
- "The agent struggled" → neutral language
- "Poor decision-making" → factual description
- Maintains third-person objective tone
