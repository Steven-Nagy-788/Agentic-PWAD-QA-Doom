TOOL REFERENCE — DETAILED INTERNALS

Each tool's internal behavior is documented so you know EXACTLY what will
happen when you call it. This is not speculation — this is how the code works.

────────────────────────────────────────────────────────────
explore
────────────────────────────────────────────────────────────
  {"max_tics": 20-200, "stop_on_enemy": true, "stop_on_item": true,
   "ignore_object_ids": [], "turn_before": 0.0}

  WHAT HAPPENS INTERNALLY:
  - The agent walks forward at speed 25 Doom units/tic
  - Depth buffer is checked each tic: if center is < 15 units (wall close),
    it turns 25 degrees left or right. If < 40 units (wall near), it turns
    10 degrees and moves slowly. If clear, it moves forward at full speed.
  - All objects are scanned each tic. Monsters within 800 units that are
    visible trigger a stop (if stop_on_enemy=true). Items trigger stop
    (if stop_on_item=true). ignore_object_ids bypasses specific enemies.
  - Stuck detection: after 20 position samples, if bounding-box diagonal
    of all positions is < 15 units, the agent is stuck. It turns 30 degrees
    (alternating left/right) and pushes forward. After 3 failed recoveries,
    returns "stuck".
  - If turn_before != 0, rotates that many degrees BEFORE exploring.
  - Auto-opens nearby doors via USE when it detects them.

  RETURNS:
  - distance_moved: total units traveled (0 = completely stuck)
  - direction_changes: how many turns were made
  - enemies_seen: [{id, name, distance}] monsters spotted
  - items_seen: [{id, name, distance}] items/ammo spotted
  - stop_reason: "enemy_spotted" | "item_found" | "stuck" |
                  "player_died" | "episode_finished" | "max_tics"

  USE WHEN: coverage is low, you need to find new areas, or you're lost.
  TIPS:
  - Set stop_on_enemy=false to ignore enemies and explore faster
  - Set max_tics=200 for long exploration runs through open areas
  - Use turn_before after a guard override to face a new direction
  - This is your MOST IMPORTANT tool — use it more than combat

────────────────────────────────────────────────────────────
aim_and_shoot
────────────────────────────────────────────────────────────
  {"object_id": <visible monster id>, "shots": 1-8, "max_tics": 10-120}

  WHAT HAPPENS INTERNALLY:
  - Finds the target by object_id in the current object list
  - If target is None: returns "target_lost" or "target_killed"
  - If target is not visible: returns "target_not_visible"
  - Auto-selects best weapon for the distance (BFG > plasma > rocket >
    chaingun > shotgun > pistol > melee if close)
  - Aim phase: turns toward target using angle_to_aim (clamped to +/-45°)
  - If angle > 3°: turns only (no fire). If within tolerance: fires.
  - Each shot: sends ATTACK=1 with small re-aim correction
  - Waits up to 4 tics for weapon cooldown between shots
  - Tracks kills (KILLCOUNT delta), hits (HITCOUNT delta), ammo spent

  RETURNS:
  - shots_fired, hits_landed, kills, ammo_spent
  - target_name, weapon_state, weapon_switch info
  - stop_reason: "shots_complete" | "target_killed" | "target_lost" |
                  "target_not_visible" | "player_died" |
                  "selected_weapon_empty" | "no_usable_weapon" |
                  "weapon_switch_failed" | "max_tics"

  USE WHEN: single visible enemy blocking your path.
  TIPS:
  - Only works on VISIBLE enemies (in threat_summary visible list)
  - If target_lost, the enemy is behind a wall — reposition, don't retry
  - shots=3 is usually enough for most enemies
  - max_tics=60 gives enough time for 3-4 shots with cooldown

────────────────────────────────────────────────────────────
strafe_and_shoot
────────────────────────────────────────────────────────────
  {"object_id": <visible monster id>, "direction": "auto|left|right",
   "shots": 1-8, "max_tics": 10-120}

  WHAT HAPPENS INTERNALLY:
  - Same target-finding and weapon selection as aim_and_shoot
  - Key difference: STRAFES while shooting (moves sideways)
  - If direction="auto": alternates left/right every 15 tics
  - Each tic sends: TURN + STRAFE (speed 20) + ATTACK (when weapon ready)
  - Always fires when weapon is ready — does NOT wait for precise aim
  - Trades accuracy for damage output and dodging
  - Tracks damage_taken via DAMAGE_TAKEN delta

  RETURNS: Same as aim_and_shoot plus strafe_direction and damage_taken.

  USE WHEN: multiple enemies, hitscanner enemies, or you need to dodge.
  TIPS:
  - Better than aim_and_shoot against hitscanners (dodges their shots)
  - direction="auto" is usually best — alternates unpredictably
  - shots=5 for groups, shots=3 for single targets
  - This is your PRIMARY combat tool — use it more than aim_and_shoot

────────────────────────────────────────────────────────────
move_to
────────────────────────────────────────────────────────────
  {"object_id": <nearby object id>, "max_tics": 20-180,
   "use": false, "stop_on_enemy": true}

  WHAT HAPPENS INTERNALLY:
  - Finds target by object_id. If None: returns "arrived" (pickup) or
    "target_lost" (non-pickup)
  - If distance < 64: for pickups, walks forward 8 tics to collect; for
    non-pickups, presses USE if use=true
  - Each tic: turns toward target (clamped +/-30°), then moves forward
    at speed 25. If angle > 15°, turns only (avoids walking into walls)
  - Stuck detection: same 20-position window as explore. After 3 failed
    recoveries, returns "stuck"
  - If stop_on_enemy=true and a monster appears within 800 units: returns
    "enemy_nearby"

  RETURNS:
  - distance_moved, distance_remaining, target_name
  - used_object (if USE was pressed)
  - threat_object (if enemy spotted)
  - stop_reason: "arrived" | "target_lost" | "enemy_nearby" | "stuck" |
                  "player_died" | "episode_finished" | "max_tics" |
                  "pickup_not_collected"

  USE WHEN: approaching a specific item, key, door, or switch.
  TIPS:
  - Use move_to to approach doors, then take_action with USE=1 to open
  - If target_lost for a pickup, it was already collected — move on
  - stop_on_enemy=false lets you rush through to reach objectives

────────────────────────────────────────────────────────────
retreat
────────────────────────────────────────────────────────────
  {"tics": 8-70, "backpedal": false}

  WHAT HAPPENS INTERNALLY:
  - If backpedal=false (default): turns 180° over 6 tics (30°/tic), then
    sprints forward at speed 25+SPEED flag for remaining tics
  - If backpedal=true: moves backward at speed 25 while keeping current
    facing (slower but maintains line of sight)
  - Total duration: min(tics, 200) game tics

  RETURNS:
  - distance_moved, mode ("backpedal" or "turn_and_run")
  - stop_reason: "completed" | "player_died" | "episode_finished"

  USE WHEN: You need to REPOSITION before a fight, not to escape death.
  CRITICAL WARNING: Retreat moves you BACKWARD into unknown territory.
  It turns 180° and runs — you may retreat into a wall, corner, or more
  enemies. RETREAT IS NOT A SURVIVAL STRATEGY.
  DO NOT USE RETREAT IF:
  - You are already in a corner or narrow corridor (you will hit a wall)
  - You have used retreat in the last 3 decisions (you are in a loop)
  - You are surrounded on multiple sides (retreat won't help)
  IF YOU MUST RETREAT: After retreating, you MUST immediately choose a
  target and fight. Do NOT retreat and then explore — that is the loop
  that kills you. Retreat → Fight is valid. Retreat → Explore → Retreat
  is a death spiral.
  TIPS:
  - backpedal=false is faster (turn and sprint) but you lose sight of enemies
  - backpedal=true keeps enemies in sight (good for kiting to fight)
  - 35 tics = ~1 second of retreat, usually enough to create space
  - If you retreated and are now in a corner: STOP RETREATING. Pick the
    nearest enemy and strafe_and_shoot. Dying while fighting is better
    than dying in a corner having accomplished nothing.

────────────────────────────────────────────────────────────
select_weapon
────────────────────────────────────────────────────────────
  {"weapon_slot": <0-9>, "max_tics": 1-20}

  WHAT HAPPENS INTERNALLY:
  - Switches to the specified weapon slot number
  - Waits up to max_tics for the switch to complete
  - Returns weapon_state after switch

  RETURNS:
  - weapon_state with updated selected weapon and usable weapons list
  - stop_reason: "selected" | "weapon_switch_failed"

  USE WHEN: current weapon has no ammo or wrong weapon for the situation.
  TIPS:
  - Slot 1: Chainsaw (melee, 0 ammo) — last resort
  - Slot 2: Pistol (unlimited ammo, weak)
  - Slot 3: Shotgun (good to 512 units)
  - Slot 4: Chaingun (good to 1024 units)
  - Slot 5: Rocket Launcher (splash, dangerous close)
  - Slot 6: Plasma Rifle (fast, high DPS)
  - Slot 7: BFG9000 (80 ammo, devastating)

────────────────────────────────────────────────────────────
take_action
────────────────────────────────────────────────────────────
  {"actions": {"TURN_LEFT_RIGHT_DELTA": <degrees>,
               "MOVE_FORWARD_BACKWARD_DELTA": <speed>,
               "MOVE_LEFT_RIGHT_DELTA": <speed>,
               "ATTACK": 0|1, "USE": 0|1, "SPEED": 0|1,
               "SELECT_WEAPON0..SELECT_WEAPON9": 0|1},
   "tics": 1-8}

  WHAT HAPPENS INTERNALLY:
  - Executes raw Doom inputs for 1-8 tics
  - Each button is held for the specified number of tics
  - Delta values are MULTIPLIED by tics (use tics=1 for precision)
  - ATTACK=1 fires the current weapon
  - USE=1 opens doors, presses switches, activates lifts
  - SPEED=1 runs (faster movement but less control)

  RETURNS: Full game state screenshot + variables.

  USE WHEN: precise movement, pressing USE on doors/switches, or
  fine-tuned aiming that compound tools can't handle.
  TIPS:
  - USE=1 for 1 tic is enough to open a door or press a switch
  - TURN_LEFT_RIGHT_DELTA with tics=1 for precise aiming
  - This is a LOW-LEVEL tool — prefer compound tools when possible

────────────────────────────────────────────────────────────
get_state
────────────────────────────────────────────────────────────
  {"include_sectors": false, "include_depth": true}

  WHAT HAPPENS INTERNALLY:
  - Returns screenshot + full game state dict
  - game_variables: ~40 Doom variables (health, armor, ammo, position, etc.)
  - objects: filtered nearby objects with distance, angle, type, threat
  - weapon_state: current weapon + inventory analysis
  - depth: depth buffer stats (wall distances in 6 screen regions)

  RETURNS: [screenshot_png, state_dict]

  USE WHEN: you need to assess the situation before deciding.
  HARD RULE: Never call this more than once consecutively. If you have
  nothing useful to do, call explore instead. The guard will override
  repeated get_state calls.

────────────────────────────────────────────────────────────
get_threat_assessment
────────────────────────────────────────────────────────────
  {"no params — zero tics consumed"}

  WHAT HAPPENS INTERNALLY:
  - Analyzes all objects without consuming game tics
  - Computes priority_score for each monster:
    score = threat_weight*10 + attack_urgency*5 + (1000/distance) + visibility
  - Arch-Vile gets +100 bonus (always top priority)
  - Returns sorted threat list with tactical advice
  - Threat level: critical (>=50), high (>=30), medium (>=15), low

  RETURNS:
  - threat_level, threats (sorted by priority), incoming_projectiles
  - tactical_advice (string list with recommendations)
  - player_health, player_armor, selected_weapon_ammo

  USE WHEN: deciding whether to fight or flee, choosing targets.
  TIPS: Call this freely between actions — it costs zero tics.

────────────────────────────────────────────────────────────
get_navigation_info
────────────────────────────────────────────────────────────
  {"no params — zero tics consumed"}

  WHAT HAPPENS INTERNALLY:
  - Tracks exploration across calls using 128-unit grid cells
  - Counts visited cells, identifies unexplored directions
  - Detects keys picked up and keys still on map
  - Detects doors within 512 units via sector geometry analysis

  RETURNS:
  - cells_explored: count of unique grid cells visited
  - explored_directions / unexplored_directions: N/S/E/W
  - suggested_direction: best unexplored direction
  - keys_found / known_key_locations
  - nearby_doors / total_doors_found

  USE WHEN: planning which direction to explore next.
  TIPS: Call freely — zero tics consumed.

────────────────────────────────────────────────────────────
get_map_graph
────────────────────────────────────────────────────────────
  {"no params — zero tics consumed"}

  WHAT HAPPENS INTERNALLY:
  - Builds sector connectivity graph from linedef adjacency
  - BFS reachability analysis from current position
  - Identifies sink_sectors (areas that can't reach the exit)
  - A* pathfinding to exit if exit sector is known

  RETURNS:
  - total_sectors, total_edges
  - exit_reachable_from_spawn: bool
  - sink_sectors: list of unreachable sectors
  - reachable_from_spawn_count

  USE WHEN: detecting softlocks, checking if map is completable.
  TIPS: If sink_sectors > 0, those areas may be softlocked.

────────────────────────────────────────────────────────────
finish
────────────────────────────────────────────────────────────
  {"summary": "brief findings", "outcome": "qa_completed|timeout|softlock|player_died"}

  WHAT HAPPENS INTERNALLY:
  - Returns confirmation dict: {"status": "finishing", ...}
  - The backend loop BREAKS and generates the report
  - This is a one-way door — you cannot undo this

  FINISH CONDITIONS (you MUST check these before calling):
  1. coverage.coverage_percent >= 90
  2. player.kills >= spawned enemy count
  3. All reachable items collected (scene_objects has no reachable items)
  4. All doors tested (navigation.total_doors_found tested)
  5. All secrets checked (if secret_sector_count > 0)

  ALLOWED OUTCOMES:
  - "qa_completed": ALL 5 conditions above are true
  - "timeout": ticks_remaining < 200 and you cannot progress
  - "softlock": get_map_graph shows sink_sectors with no exit path
  - "player_died": health <= 0

  NEVER call finish with outcome="qa_completed" unless ALL conditions
  are met. The guard WILL block premature finish calls.
