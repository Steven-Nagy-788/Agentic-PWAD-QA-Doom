# Diagram Placeholders for Thesis

This file contains text-based representations of all diagrams needed for the thesis. Each section maps to a specific chapter and figure number. These can be converted to proper figures using draw.io, Lucidchart, or Mermaid CLI.

---

## Figure 1: Use Case Diagram (Ch 3.3)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    BoJack: Agentic Game QA System                   │
│                                                                     │
│  ┌──────────────────┐                                               │
│  │     User          │                                              │
│  │  (QA Engineer)    │                                              │
│  └──────┬───────────┘                                              │
│         │                                                           │
│         ├─── uploads ──────────────> [Upload WAD File]              │
│         │                                                           │
│         ├─── initiates ────────────> [Start Test Run]               │
│         │                                                           │
│         ├─── configures ───────────> [Set Run Parameters]           │
│         │                          (difficulty, tick limit)          │
│         │                                                           │
│         ├─── views ────────────────> [View Live Run Progress]       │
│         │                          (WebSocket stream)               │
│         │                                                           │
│         ├─── reviews ──────────────> [Review Past Runs]             │
│         │                          (history, recordings)            │
│         │                                                           │
│         ├─── downloads ────────────> [Download PDF Report]          │
│         │                                                           │
│         └─── monitors ────────────> [Check System Health]           │
│                                    (health endpoints)               │
│                                                                     │
│  ┌──────────────────┐                                              │
│  │   AI Agent        │                                             │
│  │  (Gemini LLM)    │                                              │
│  └──────┬───────────┘                                              │
│         │                                                           │
│         ├─── receives ─────────────> [Receive Game State]           │
│         │                                                           │
│         ├─── decides ──────────────> [Make Action Decision]         │
│         │                                                           │
│         ├─── executes ─────────────> [Execute MCP Tool Call]        │
│         │                                                           │
│         └─── reasons ─────────────> [Generate Reasoning Log]        │
│                                                                     │
│  ┌──────────────────┐                                              │
│  │  ViZDoom Engine   │                                             │
│  │  (Game Server)    │                                             │
│  └──────┬───────────┘                                              │
│         │                                                           │
│         ├─── simulates ────────────> [Simulate Gameplay]            │
│         │                                                           │
│         ├─── produces ─────────────> [Produce Game State]           │
│         │                          (variables, screenshot, map)     │
│         │                                                           │
│         └─── records ─────────────> [Record Video Playback]         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Note for conversion:** This should be drawn as a standard UML use case diagram with three actors (User, AI Agent, ViZDoom Engine) and oval use cases connected by association lines. The system boundary rectangle should contain all use cases.

---

## Figure 2: Entity-Relationship Diagram (Ch 5.2)

```
┌──────────────┐       ┌──────────────────────────┐
│   WadFile     │       │  StaticAnalysisResult     │
├──────────────┤       ├──────────────────────────┤
│ id (PK)      │──1:N──│ wad_file_id (FK)          │
│ original_    │       │ map_name                  │
│   filename   │       │ thing_count_enemies       │
│ sha256_hash  │       │ door_count                │
│ storage_path │       │ secret_sector_count       │
│ created_at   │       │ total_linedefs            │
└──────┬───────┘       │ total_sectors             │
       │               └──────────────────────────┘
       │
       │──1:N──┌──────────────────────────┐
       │       │       TestRun             │
       │       ├──────────────────────────┤
       │       │ id (PK)                  │
       │       │ wad_file_id (FK)         │
       │       │ map_name                 │
       │       │ status                   │
       │       │ outcome                  │
       │       │ llm_model                │
       │       │ difficulty_level         │
       │       │ total_ticks              │
       │       │ coverage_percent         │
       │       │ player_kills             │
       │       │ created_at               │
       │       └──────┬───────────────────┘
       │              │
       │              │──1:N──┌──────────────────────┐
       │              │       │   AgentDecision       │
       │              │       ├──────────────────────┤
       │              │       │ id (PK)              │
       │              │       │ run_id (FK)          │
       │              │       │ sequence_number      │
       │              │       │ mcp_tool             │
       │              │       │ mcp_input            │
       │              │       │ mcp_output           │
       │              │       │ reasoning_summary    │
       │              │       │ decision_source      │
       │              │       │ tick_before/after    │
       │              │       └──────────────────────┘
       │              │
       │              │──1:N──┌──────────────────────┐
       │              │       │     GameEvent         │
       │              │       ├──────────────────────┤
       │              │       │ id (PK)              │
       │              │       │ run_id (FK)          │
       │              │       │ event_type           │
       │              │       │ tick_number          │
       │              │       │ screenshot_b64       │
       │              │       │ metadata (JSON)      │
       │              │       └──────────────────────┘
       │              │
       │              │──1:N──┌──────────────────────┐
       │              │       │      Defect           │
       │              │       ├──────────────────────┤
       │              │       │ id (PK)              │
       │              │       │ run_id (FK)          │
       │              │       │ defect_type          │
       │              │       │ severity             │
       │              │       │ priority             │
       │              │       │ description          │
       │              │       │ recommendation       │
       │              │       │ fingerprint          │
       │              │       │ map_x, map_y         │
       │              │       │ screenshot_path      │
       │              │       └──────────────────────┘
       │              │
       │              │──1:N──┌──────────────────────┐
       │              │       │ AgentPositionTrail    │
       │              │       ├──────────────────────┤
       │              │       │ id (PK)              │
       │              │       │ run_id (FK)          │
       │              │       │ tick_number          │
       │              │       │ player_x, player_y   │
       │              │       │ cell_x, cell_y       │
       │              │       └──────────────────────┘
       │              │
       │              │──1:N──┌──────────────────────┐
       │              │       │NotableEventScreenshot│
       │              │       ├──────────────────────┤
       │              │       │ id (PK)              │
       │              │       │ run_id (FK)          │
       │              │       │ screenshot_path      │
       │              │       │ event_type           │
       │              │       └──────────────────────┘
       │              │
       │              │──1:1──┌──────────────────────┐
       │              │       │    TestReport         │
       │              │       ├──────────────────────┤
       │              │       │ id (PK)              │
       │              │       │ run_id (FK, UQ)      │
       │              │       │ pdf_path             │
       │              │       │ verdict              │
       │              │       │ generated_at         │
       │              │       └──────────────────────┘
       │
       │──1:N──┌──────────────────────┐
       │       │   WadHypothesis       │
       │       ├──────────────────────┤
       │       │ id (PK)              │
       │       │ wad_file_id (FK)     │
       │       │ map_name             │
       │       │ tag                  │
       │       │ content              │
       │       │ confidence           │
       │       └──────────────────────┘
       │
       │──1:N──┌──────────────────────┐
       │       │  WadSpatialMemory     │
       │       ├──────────────────────┤
       │       │ id (PK)              │
       │       │ wad_file_id (FK)     │
       │       │ map_name             │
       │       │ cell_x, cell_y       │
       │       │ event_type           │
       │       │ occurrence_count     │
       │       └──────────────────────┘

┌──────────────────────┐
│    ConfigEntry        │
├──────────────────────┤
│ id (PK)              │
│ key (UQ)             │
│ value (JSON)         │
│ updated_at           │
└──────────────────────┘
```

**Note for conversion:** Draw as a standard ER diagram with Chen or Crow's Foot notation. Use rectangles for entities, diamonds for relationships, and ovals for attributes. Primary keys (PK) underlined, foreign keys (FK) marked.

---

## Figure 3: Sequence Diagram — Lockstep Iteration (Ch 5.4.2)

```
User          Frontend        Backend           MCP-Doom        ViZDoom         Gemini LLM
  │               │               │                 │               │               │
  │──start run──>│               │                 │               │               │
  │               │──POST /runs──>│                 │               │               │
  │               │               │──start_game───>│               │               │
  │               │               │                 │──init game──>│               │
  │               │               │<──game started──│               │               │
  │               │<──run id─────│                 │               │               │
  │               │               │                 │               │               │
  │               │               │  ╔═══════════════════════════╗  │               │
  │               │               │  ║   LOCKSTEP LOOP (repeat)  ║  │               │
  │               │               │  ╚═══════════════════════════╝  │               │
  │               │               │                 │               │               │
  │               │               │──get_state────>│               │               │
  │               │               │                 │──query vars─>│               │
  │               │               │                 │<──state──────│               │
  │               │               │<──state+screen──│               │               │
  │               │               │                 │               │               │
  │               │               │──build prompt──────────────────────────────────>│
  │               │               │                 │               │               │
  │               │               │<──JSON decision────────────────────────────────│
  │               │               │                 │               │               │
  │               │               │──apply guards──│               │               │
  │               │               │  (override if   │               │               │
  │               │               │   stuck/loop)   │               │               │
  │               │               │                 │               │               │
  │               │               │──take_action──>│               │               │
  │               │               │                 │──execute────>│               │
  │               │               │                 │<──new state───│               │
  │               │               │<──result────────│               │               │
  │               │               │                 │               │               │
  │               │               │──record decision + event       │               │
  │               │               │──WS broadcast──>│               │               │
  │               │<──live update──│                │               │               │
  │<──dashboard──│               │                 │               │               │
  │               │               │                 │               │               │
  │               │               │──check stop conditions          │               │
  │               │               │  (ticks, finish, crash)         │               │
  │               │               │                 │               │               │
  │               │               │  ╔═══════════════════════════╗  │               │
  │               │               │  ║   END LOOP (when done)     ║  │               │
  │               │               │  ╚═══════════════════════════╝  │               │
  │               │               │                 │               │               │
  │               │               │──finalize run──│               │               │
  │               │               │  (recording,    │               │               │
  │               │               │   defects,      │               │               │
  │               │               │   report PDF)   │               │               │
```

**Note for conversion:** Draw as a standard UML sequence diagram with lifelines (vertical dashed boxes) for each participant. Messages are horizontal arrows. The loop fragment should use a UML loop operator rectangle with "loop" label.

---

## Figure 4: Activity Diagram — Run Lifecycle (Ch 5.4.3)

```
                    ┌───────────┐
                    │  Start     │
                    └─────┬─────┘
                          │
                    ┌─────▼─────┐
                    │ Upload     │
                    │ WAD File   │
                    └─────┬─────┘
                          │
                    ┌─────▼─────┐
                    │  Static    │
                    │  Analysis  │──── parse geometry,
                    │  (omgifol) │     count things,
                    └─────┬─────┘     identify sectors
                          │
                    ┌─────▼─────┐
                    │  Create    │
                    │  TestRun   │──── insert DB record,
                    │  Record    │     set status=pending
                    └─────┬─────┘
                          │
                    ┌─────▼─────────┐
                    │  Acquire       │──── pg_advisory_xact_lock
                    │  Advisory Lock │     (prevents concurrent runs)
                    └─────┬─────────┘
                          │
                    ┌─────▼─────────┐
                    │  Start MCP     │──── start_game(WAD, map,
                    │  Game          │     difficulty, resolution)
                    └─────┬─────────┘
                          │
                    ╔═════▼═══════════════════════════╗
                    ║     LOCKSTEP LOOP                ║
                    ║  ┌───────────────────────────┐  ║
                    ║  │  Get State (MCP)           │  ║
                    ║  └───────────┬───────────────┘  ║
                    ║              │                    ║
                    ║  ┌───────────▼───────────────┐  ║
                    ║  │  Build LLM Prompt          │  ║
                    ║  │  (map + history + state)    │  ║
                    ║  └───────────┬───────────────┘  ║
                    ║              │                    ║
                    ║  ┌───────────▼───────────────┐  ║
                    ║  │  Gemini Decision           │  ║
                    ║  │  (JSON action + reasoning)  │  ║
                    ║  └───────────┬───────────────┘  ║
                    ║              │                    ║
                    ║  ┌───────────▼───────────────┐  ║
                    ║  │  Apply Guards               │  ║
                    ║  │  ◆ stuck? → force explore   │  ║
                    ║  │  ◆ looping? → diversity     │  ║
                    ║  │  ◆ premature finish? → block │ ║
                    ║  └───────────┬───────────────┘  ║
                    ║              │                    ║
                    ║  ┌───────────▼───────────────┐  ║
                    ║  │  Execute MCP Tool           │  ║
                    ║  └───────────┬───────────────┘  ║
                    ║              │                    ║
                    ║  ┌───────────▼───────────────┐  ║
                    ║  │  Record Decision + Event    │  ║
                    ║  └───────────┬───────────────┘  ║
                    ║              │                    ║
                    ║  ┌───────────▼───────────────┐  ║
                    ║  │  Broadcast WebSocket        │  ║
                    ║  └───────────┬───────────────┘  ║
                    ║              │                    ║
                    ║  ◇───────────◇────────────────  ║
                    ║  │ Stop conditions met?         ║
                    ║  │ • tick limit reached         ║
                    ║  │ • agent called finish        ║
                    ║  │ • PWAD crash detected        ║
                    ║  ◇─────Yes──────────No────────  ║
                    ╚══════════╤═══════════╤══════════╝
                               │           │
                               │     ┌─────▼─────┐
                               │     │  Continue  │──┐
                               │     │  Loop      │  │
                               │     └───────────┘  │
                               │           ▲         │
                               │           └─────────┘
                    ┌──────────▼──────────┐
                    │  Finalize Run        │
                    │  • Encode recording  │
                    │  • Detect defects    │
                    │  • Generate PDF      │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Release Advisory    │
                    │  Lock                │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Run Complete        │
                    └─────────────────────┘
```

**Note for conversion:** Draw as a UML activity diagram with swimlanes for Backend, MCP-Doom, and Gemini. Use diamond shapes for decision nodes, rounded rectangles for activities, and solid bars for fork/join (loop start/end).

---

## Figure 5: UI/UX Wireframes (Ch 5.5)

### 5a. Dashboard (WAD Library)

```
┌─────────────────────────────────────────────────────────┐
│  BoJack QA     Dashboard  History  Settings    [Health] │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Upload WAD File                    [+ Upload]  │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  WAD Library (3 files)                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │ MAP01    │  │ MAP02    │  │ E1M1     │             │
│  │ ┌──────┐ │  │ ┌──────┐ │  │ ┌──────┐ │             │
│  │ │thumb │ │  │ │thumb │ │  │ │thumb │ │             │
│  │ └──────┘ │  │ └──────┘ │  │ └──────┘ │             │
│  │ 3 maps   │  │ 5 maps   │  │ 1 map    │             │
│  │ 2 runs   │  │ 0 runs   │  │ 4 runs   │             │
│  │ 1 defect │  │          │  │ 3 defects│             │
│  └──────────┘  └──────────┘  └──────────┘             │
│                                                         │
│  Recent Runs                                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │ MAP01  completed  68% coverage  3 defects  2m30s│   │
│  │ MAP01  completed  45% coverage  1 defect   1m45s│   │
│  │ E1M1   running    23% coverage  ...        0m30s│   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 5b. Live Run View

```
┌─────────────────────────────────────────────────────────┐
│  ← Back to Dashboard     Run #12     [Cancel]  [PDF]   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌───────────────────────────┐  ┌───────────────────┐  │
│  │                           │  │  LLM Calls: 47    │  │
│  │      GAME SCREENSHOT      │  │  Ticks: 1240      │  │
│  │      (live frame)         │  │  Coverage: 62%    │  │
│  │                           │  │  Defects: 2       │  │
│  │                           │  │  Cost: $0.12      │  │
│  └───────────────────────────┘  └───────────────────┘  │
│                                                         │
│  ┌───────────────────────────┐  ┌───────────────────┐  │
│  │      MAP CANVAS           │  │  ASCII GRID       │  │
│  │  (SVG with position       │  │  (21x21 text      │  │
│  │   trail + event markers)  │  │   map from LLM)   │  │
│  └───────────────────────────┘  └───────────────────┘  │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ [Reasoning] [MCP Inspector] [Memory] [Defects]  │   │
│  ├─────────────────────────────────────────────────┤   │
│  │  Decision #47: explore                           │   │
│  │  "Moving toward unexplored corridor on the       │   │
│  │   east side. Detected door ahead at sector 14."  │   │
│  │  Source: gemini | Tick: 1240 | Duration: 1.2s    │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Trail: 234  Events: 18  Tick: 1240  Status: RUN │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 5c. WAD Detail Page

```
┌─────────────────────────────────────────────────────────┐
│  ← Back      WAD: test_map_v2.wad                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Maps (3)                                               │
│  ┌─────────────────────────────────────────────────┐   │
│  │ MAP01  12 enemies  4 doors  2 secrets  [Run ▶] │   │
│  │ MAP02  8 enemies   2 doors  0 secrets  [Run ▶] │   │
│  │ MAP03  15 enemies  6 doors  1 secret   [Run ▶] │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  Skill Heatmap (MAP01)                                  │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Hitscanner: ████████░░ 72%                      │   │
│  │  Melee:      ███░░░░░░░ 30%                      │   │
│  │  Health:     ██████░░░░ 55%                      │   │
│  │  Ammo:       ████████░░ 80%                      │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  Recurring Defects (2+ runs)                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │ softlock_navigation  MAP01  3/4 runs  [High]    │   │
│  │ unreachable_secret   MAP01  2/4 runs  [Medium]  │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  Run Configuration                                      │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Difficulty: [I'm Too Young to Die ▼]            │   │
│  │ Tick Limit: [3000]                              │   │
│  │ Behavior:  [Thorough ▼]                         │   │
│  │                          [Start Test Run]        │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**Note for conversion:** These wireframes should be redrawn as proper UI mockups using Figma, Sketch, or draw.io. The text-based versions show the layout structure and key elements.
