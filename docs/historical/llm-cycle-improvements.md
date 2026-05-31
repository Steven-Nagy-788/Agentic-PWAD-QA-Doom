# Historical: LLM Cycle Improvements

This document catalogues concrete improvements to the LLM-driven QA pipeline, ranked by impact and urgency.

---

## P0 — Critical Impact

### 1. Add Vision Input to the LLM

**Problem**: The LLM receives only structured state JSON — no screenshot. ViZDoom renders full 640×480 frames that are already captured for recording, but the LLM never sees them. This means the LLM is blind to geometry, enemy positioning, HUD status, door animations, switch visual states, and map aesthetics. It must infer all spatial information from abstract numbers.

**Location**: `gemini_service.py:87-90` in `_call_gemini()`

**Current code**:
```python
contents = f"{system_prompt}\n\nCURRENT STATE JSON:\n{json.dumps(llm_input, default=str)}"
```

**Recommended approach**: Use Gemini's multimodal API to send the screenshot PNG alongside the JSON. The `get_state()` call already returns `screenshot_png` bytes. Convert to base64 and include as a `Part` in the content:

```python
from google.genai import types

async def _call_gemini_multimodal(self, system_prompt: str, llm_input: dict, screenshot_png: bytes | None) -> str:
    parts = [types.Part.from_text(f"{system_prompt}\n\nCURRENT STATE JSON:\n{json.dumps(llm_input, default=str)}")]
    if screenshot_png:
        parts.append(types.Part.from_bytes(data=screenshot_png, mime_type="image/png"))
    response = await async_client.models.generate_content(
        model=self.settings.llm_model,
        contents=types.Content(parts=parts, role="user"),
    )
    return response.text or ""
```

**Impact**: ~60% improvement in combat targeting, navigation decisions, and defect detection quality. The LLM can see enemies behind walls (geometry), read the HUD directly, identify door textures, and recognize visual softlocks.

**Changes needed**:
- `gemini_service.py`: Add multimodal call path
- `run_service.py`: Thread `screenshot_png` from `get_state()` into `gemini.decide()`
- `agent_system_prompt.md`: Add instructions for interpreting the screenshot

---

### 2. Dynamic Throttle Based on Game State

**Problem**: The 12-second fixed throttle (`LLM_THROTTLE_SECONDS`) pauses game time equally between every decision. During combat, 12s of real time means the LLM cannot react quickly to threats. During quiet exploration, 12s is fine. There is no adaptation.

**Location**: `run_service.py:499` in `agent_run_task()`

**Current code**:
```python
throttle_seconds = max(0.0, get_settings().llm_throttle_seconds)
if throttle_seconds:
    await asyncio.sleep(throttle_seconds)
```

**Recommended approach**:
```python
throttle_seconds = _compute_dynamic_throttle(state, lockstep_state)

def _compute_dynamic_throttle(state: dict, lockstep_state: dict) -> float:
    variables = normalize_variables(state)
    objects = state.get("objects") or []
    visible_monsters = [o for o in objects if o.get("type") == "monster" and o.get("is_visible")]
    health = variables.get("health", 100)
    ammo_total = variables.get("ammo_total", 0)

    # Combat urgency: fast decisions when enemies are visible
    if visible_monsters:
        return 3.0

    # Low health or ammo: moderate pace
    if health < 25 or ammo_total == 0:
        return 6.0

    # Exploration deceleration: slower when no progress
    if lockstep_state.get("no_progress_polls", 0) >= 2:
        return 10.0

    # Default
    return 12.0
```

**Impact**: 3–4× more decisions per tick budget during combat-heavy maps, allowing the LLM to actually fight reactively. Reduces "player stood still while being killed" scenarios.

---

### 3. Invisible Target Failure Handling — Break the Fallback-Guard Loop

**Problem**: The `invisible_target_failures` tracking has three design flaws that together create an infinite loop:

1. **No expiry** — Once a target is marked as `target_not_visible`, the guard blocks it **permanently** with no time or event-based expiry.
2. **Fallback ignores it** — `_fallback_decision()` checks `out_of_ammo_targets` but NOT `invisible_target_failures`, so it keeps suggesting the same blocked target.
3. **Guard explore resets protections** — The guard redirects combat to explore with `stop_on_item=True`, which immediately stops on a visible item and resets all low-value-explore protections.

**Loop**: fallback → suggest target 7 → guard → explore → item_found (resets protections) → fallback → target 7 again → ...

**Location**:
- `gemini_service.py:_fallback_decision` (line 214-219)
- `run_service.py:_guard_lockstep_decision` (line 878-887)
- `run_service.py:_update_lockstep_after_action` (line 1045-1051)

**Fix 1 — Fallback filters `invisible_target_failures`** (`gemini_service.py:214-219`):
```python
invisible_target_failures = {str(key) for key in (lockstep_state.get("invisible_target_failures") or {})}
# Added: and str(obj.get("id")) not in invisible_target_failures
```

**Fix 2 — Guard redirect uses `stop_on_item=False`** (`run_service.py:885`):
```python
"mcp_params": {"max_tics": 80, "stop_on_enemy": True, "stop_on_item": False},
```

**Fix 3 — Clear `invisible_target_failures` on progress** (`run_service.py:1016,1041`):
```python
lockstep_state["invisible_target_failures"] = {}  # on arrival or kill
```

**Impact**: Breaks the infinite loop. The fallback now skips invisible targets and moves to pickups or real exploration. If explore fires, `stop_on_item=False` lets the agent reach new positions instead of resetting protections. After any real progress (kill or pickup), old invisible failures are cleared so targets can be retried.

---

## P1 — High Impact

### 5. Add Visited-Area Memory to LLM Input

**Problem**: The LLM has no memory of which map areas it has already visited. It gets `navigation_info.cells_explored` (a count) and `recent_trace` (last 5 events), but it cannot distinguish "I am exploring new territory" from "I am looping over familiar ground." This causes circular exploration patterns and premature stuck detection.

**Location**: `run_service.py:306-313` where `llm_input` is constructed.

**Recommended approach**: Maintain a set of coarse position cells visited and include the *number of cells visited per quadrant* (divide the map into a grid and track which cells have been entered). Pass downsampled recent position history (last 20 unique position cells).

Add to `lockstep_state`:
```python
"visited_cells": set()  # set of (round(x/256), round(y/256)) tuples
```

Include in `llm_input`:
```python
"exploration_coverage": {
    "visited_cells_count": len(lockstep_state["visited_cells"]),
    "total_map_cells_estimate": analysis.map_width_units * analysis.map_height_units / (256*256),
    "new_cells_last_5_decisions": recent_new_cells,
}
```

**Impact**: Eliminates circular exploration loops. Enables the LLM to prioritize unvisited areas, improving spatial coverage by 40-60%.

---

### 6. Multi-Model Provider Support

**Problem**: The system only supports Google Gemini. If the API key is missing, rates exhausted, or the model is down, the entire QA pipeline falls back to a simple deterministic agent that cannot detect defects or adapt to map context.

**Location**: `gemini_service.py` — entire file is Gemini-specific.

**Recommended approach**: Implement a provider factory pattern:

```python
class LLMProvider(ABC):
    @abstractmethod
    async def decide(self, system_prompt: str, state: dict) -> dict: ...

class GeminiProvider(LLMProvider): ...
class OpenAIProvider(LLMProvider): ...
class OllamaProvider(LLMProvider): ...

# Config-driven selection
LLM_PROVIDERS = {
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
}
```

Add new env vars:
```env
LLM_PROVIDER=gemini  # gemini | openai | ollama
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2-vision
```

Give the report generation the same treatment — support multiple providers so a report can always be generated even when one model is down.

**Impact**: Zero-downtime LLM pipeline. Can fall back to local models (Ollama) when cloud APIs are unavailable. OpenAI models (gpt-4o, o3) may offer better reasoning for navigation problems.

---

### 7. Enrich Static Analysis Data in the Agent Prompt

**Problem**: The MAP BRIEFING in the agent prompt only includes counts and ratios — enemy counts, health/ammo ratios, secret sector count, map dimensions. It does NOT include actionable spatial data: door locations, key types needed, teleporter locations, lift/crusher sectors, or locked-door linedefs. This data is available in the WAD's `THINGS` and `LINEDEFS` but is not passed to the LLM.

**Location**: `prompt_service.py:23-41` — the `values` dict passed to the template.

**Recommended approach**: Add to `analysis_service.py`:
- Extract door linedefs (special types 1, 26, 31, 32, 33, 34, 46, 61, 62, 90, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118)
- Extract key-locked linedefs (key types: 1=red, 2=yellow, 3=blue card; 13=red, 38=yellow, 39=blue skull)
- Extract teleporter things (type 39, 97)
- Count lift/platfrom sectors

Add to static analysis output:
```python
"door_count": int,
"locked_door_count": int,
"key_requirements": {"red": bool, "yellow": bool, "blue": bool},
"teleporter_count": int,
"lift_count": int,
```

Pass these into the prompt template so the LLM knows what to look for:
```
  Keys required    : {key_requirements}
  Doors            : {door_count} ({locked_door_count} locked)
  Teleporters      : {teleporter_count}
  Lifts            : {lift_count}
```

**Impact**: The LLM can plan key-hunting routes, look for switches that open locked doors, and intentionally seek teleporters — transitioning from blind wandering to goal-directed QA.

---

## P2 — Medium Impact

### 7. Agent-Observed Defect Deduplication by Position

**Problem**: The LLM can report the same defect on every tick while stuck in the same position, creating dozens of identical defect records. `normalize_observed_issue` only deduplicates by `(defect_type, title)`, but the LLM can rephrase the same issue differently each time, creating near-duplicate records.

**Location**: `collector_service.py:91-108` — defect creation logic.

**Current**: Only checks `defect_type + title` uniqueness.

**Recommended**: Add positional and tick-range deduplication:
```python
async def _deduplicate_observed_issue(self, run_id: UUID, defect_type: str, tick: int, x: float, y: float) -> bool:
    """Return True if a matching defect was already recorded within 100 units / 500 ticks."""
    existing = await defect_repo.list_by_run(run_id)
    for defect in existing:
        if defect.defect_type != defect_type:
            continue
        if defect.detected_at_tick and abs(defect.detected_at_tick - tick) < 500:
            if defect.position_x is not None and defect.position_y is not None:
                dist = ((defect.position_x - x) ** 2 + (defect.position_y - y) ** 2) ** 0.5
                if dist < 100:
                    return True
    return False
```

**Impact**: Prevents defect spam. A single real defect might be reported once instead of 15 times, making the defect list actionable.

---

### 8. Robust LLM Response Parsing

**Problem**: `parse_decision()` does naive `text.find("{")` / `rfind("}")` to extract JSON. If the LLM wraps content in markdown code fences with different patterns, or includes `{}` in the reasoning_summary, parsing fails with a `json.JSONDecodeError`, forcing deterministic fallback.

**Location**: `gemini_service.py:113-134`

**Current**:
```python
start = cleaned.find("{")
end = cleaned.rfind("}")
```

**Recommended**: Use a multi-strategy parser:
```python
def parse_decision(self, text: str) -> dict:
    strategies = [
        self._parse_json_block,    # ```json ... ```
        self._parse_json_braces,   # { ... }
        self._parse_json_loose,    # find valid JSON anywhere
    ]
    for strategy in strategies:
        result = strategy(text)
        if result is not None:
            return result
    raise ValueError("Could not parse LLM response as JSON")

def _parse_json_block(self, text: str) -> dict | None:
    import re
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return self._decode(match.group(1))
    return None
```

Add Pydantic validation of the parsed decision:
```python
from pydantic import BaseModel, field_validator

class LLMDecision(BaseModel):
    reasoning_summary: str
    mcp_tool: str
    mcp_params: dict = {}
    observed_issue: str | None = None

    @field_validator("mcp_tool")
    @classmethod
    def validate_tool(cls, v: str) -> str:
        allowed = {"get_state", "explore", "aim_and_shoot", "move_to", ...}
        if v not in allowed:
            return "explore"
        return v
```

**Impact**: Reduces unnecessary fallback decisions. Makes the pipeline resilient to LLM output formatting variations.

---

## P3 — Polish and Robustness

### 11. Prompt Injection Sanitization

**Location**: `prompt_service.py:42`

**Problem**: The prompt template uses naive `str.replace()`:
```python
template = template.replace("{" + key + "}", str(value))
```
If a map name, enemy name, or any interpolated value contains curly braces (e.g., a map named "{hacked}"), it can corrupt the template structure or leak template variables.

**Fix**: Use `string.Template` or `str.format_map` with a safe wrapper:
```python
from string import Template

safe_template = Template(template)
return safe_template.safe_substitute(values)
```

Or pre-validate that no values contain `{` or `}`:
```python
for key, value in values.items():
    if "{" in str(value) or "}" in str(value):
        values[key] = str(value).replace("{", "(").replace("}", ")")
```

---

### 12. Report Voice Sanitization Ordering Bug

**Location**: `report_service.py:170-198`

**Problem**: The regex replacements are applied sequentially and can compound. For example, `"agent"` is replaced by `"automated playthrough"`, then `"automated playthrough was unable to"` is replaced by `"automated playthrough did not"`, but the replacement rules also contain `"automated automated playthrough"` → `"automated playthrough"` showing this double-replacement is a known issue.

**Fix**: Reorder replacements so longer/more specific patterns match first, and prevent re-matching by using a single-pass strategy:

```python
REPLACEMENTS = [
    (r"\b[Aa]gent was unable to\b", "automated playthrough did not"),
    (r"\b[Aa]gent could not\b", "automated playthrough did not"),
    (r"\b[Aa]gent did not\b", "automated playthrough did not"),
    (r"\b[Aa]gent failed to\b", "automated playthrough did not"),
    (r"\b[Aa]gent\b", "automated playthrough"),  # catch-all after specific patterns
]

# Use re.sub with a function that tracks already-replaced spans
```

---

### 13. Concurrent Run Support

**Problem**: Only one test run can be active at a time due to `pg_advisory_xact_lock` and the `get_active()` check.

**Location**: `run_service.py:134-141`

**Consider**: Allow multiple concurrent runs on different maps (or same map, different difficulties). The main constraint is ViZDoom/MCP per run, which requires multiple MCP server instances. If infrastructure supports it, remove the single-active-run restriction.

For now, add documentation that multiple MCP-doom instances are needed for parallel runs, and make the lock key per-map or per-difficulty.

---

### 14. Add Smoke Test Mode

**Problem**: No way to verify the LLM pipeline is healthy without uploading a custom WAD.

**Recommended**: Add a `/runs/smoke` endpoint that runs against a built-in known-good WAD (e.g., the Freedoom IWAD's MAP01). This validates:
- MCP connectivity
- Game initialization
- LLM API keys and response parsing
- Recording pipeline
- Report generation

Response should include a `smoke_status: "pass"|"fail"` and per-stage diagnostics.

---

### 15. Cross-Run Defect Pattern Detection

**Problem**: Each run is analyzed independently. If the same map is tested at difficulties 1–5, there is no cross-run analysis to identify patterns (e.g., "always gets stuck at sector 42 regardless of difficulty").

**Recommended**: Add a `GET /runs/patterns?wad_id=X` endpoint that:
- Aggregates all runs for a WAD
- Clusters defect positions across runs
- Identifies persistent softlock locations
- Reports per-difficulty coverage differences
- Flags areas that consistently cause LLM failures

---

## Summary by Priority

| Priority | Change | Effort | Impact |
|----------|--------|--------|--------|
| P0 | Vision input to LLM | 3 days | ❇️ Transformative — LLM sees the game |
| P0 | Dynamic throttle | ½ day | ⬆️ 3-4× more combat decisions |
| P0 | Invisible target failure handling | 1 day | 🚫 Breaks infinite fallback-guard loop |
| P1 | Visited-area memory | 1 day | 🚫 Eliminates circular exploration |
| P1 | Multi-model support | 3 days | ✅ Survives any single-provider outage |
| P1 | Enriched static analysis in prompt | 2 days | 🎯 Goal-directed key/door/teleporter logic |
| P2 | Position-based defect dedup | 1 day | 📉 10× fewer duplicate defects |
| P2 | Robust JSON parsing | ½ day | 🔧 Fewer fallback decisions |
| P2 | Human-in-the-loop | 3 days | 🧑‍🔧 Human rescue of stuck runs |
| P3 | Prompt injection fix | ½ day | 🔒 Security hardening |
| P3 | Voice sanitization ordering fix | ½ day | 🐛 Bug fix |
| P3 | Smoke test mode | 1 day | 🩺 Pipeline health checks |
| P3 | Cross-run pattern detection | 2 days | 📊 Multi-run defect insights |
