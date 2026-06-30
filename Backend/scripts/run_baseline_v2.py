#!/usr/bin/env python3
"""Standalone baseline agent comparison — drives MCP directly."""

import asyncio
import json
import random
import sys
import time
from datetime import datetime

sys.path.insert(0, "/media/steven/MaD/matznysh-hna/Agentic-PWAD-QA-Doom/Backend")

from app.services.mcp_client_service import McpDoomClient, normalize_mcp_state

TICKS = 500
DIFFICULTY = 3

WADS = {
    "antony": {"iwad": "freedoom2", "map": "MAP01", "stored": "/app/storage/wads/18e5310b-ab5d-4e44-a901-8c8f5df2277f.wad", "label": "antony MAP01 (12e)", "enemies": 12},
    "hallways": {"iwad": "freedoom1", "map": "E1M1", "stored": "/app/storage/wads/fc2a223b-eb86-4416-9d6b-4b83231a09f0.wad", "label": "hallways E1M1 (8e)", "enemies": 8},
    "map02": {"iwad": "freedoom2", "map": "MAP01", "stored": "/app/storage/wads/acc96700-09a1-4ada-b4aa-7b68d5528ace.wad", "label": "MAP02 MAP01 (2e)", "enemies": 2},
}

# Safe tools with all required params
SAFE_EXPLORE = {"max_tics": 60, "stop_on_enemy": True, "stop_on_item": True, "turn_before": 0}
SAFE_SHOOT = {"max_tics": 30, "object_id": None}  # will be set per-tool
SAFE_TOOLS = {
    "explore": SAFE_EXPLORE,
    "select_weapon": {"weapon_slot": 3},
    "retreat": {"tics": 30},
}


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


class RandomBaseline:
    def __init__(self, seed=42):
        self.rng = random.Random(seed)

    def decide(self, state, lockstep, tick):
        tool = self.rng.choice(list(SAFE_TOOLS.keys()))
        params = dict(SAFE_TOOLS[tool])
        if tool == "explore":
            params["turn_before"] = self.rng.uniform(-180, 180)
            params["max_tics"] = self.rng.randint(20, 80)
        elif tool == "retreat":
            params["tics"] = self.rng.randint(10, 50)
        return {"tool": tool, "params": params, "reasoning": f"random -> {tool}"}


class GuardOnlyBaseline:
    def decide(self, state, lockstep, tick):
        stuck = lockstep.get("stuck_count", 0)
        consecutive = lockstep.get("consecutive_explore", 0)

        if consecutive >= 3:
            return {"tool": "explore", "params": {"max_tics": 80, "stop_on_enemy": False, "stop_on_item": True, "turn_before": 180.0 if consecutive % 2 == 0 else -180.0}, "reasoning": f"guard: rotate after {consecutive} explores"}
        if stuck >= 2:
            return {"tool": "explore", "params": {"max_tics": 80, "stop_on_enemy": False, "stop_on_item": True, "turn_before": 180.0}, "reasoning": "guard: unstuck"}
        return {"tool": "explore", "params": {"max_tics": 50, "stop_on_enemy": True, "stop_on_item": True}, "reasoning": "guard: default explore"}


class BoJackViaAPI:
    """Runs BoJack through the backend API."""
    pass  # handled separately


def _extract_tick(state):
    """Extract game tic from MCP state."""
    if "tic" in state:
        return int(state["tic"])
    gv = state.get("game_variables") or {}
    if isinstance(gv, dict) and "GAME_TIC" in gv:
        return int(gv["GAME_TIC"])
    return 0


def _extract_done(state):
    """Check if game is done."""
    if state.get("episode_finished"):
        return True, "episode_finished"
    gv = state.get("game_variables") or {}
    if isinstance(gv, dict) and gv.get("DEAD"):
        return True, "player_died"
    return False, None


def _extract_kills(state):
    gv = state.get("game_variables") or {}
    if isinstance(gv, dict):
        for k in ("KILLCOUNT", "killcount", "kills"):
            if k in gv:
                return int(gv[k])
    return 0


async def run_baseline(name, agent, wad_key, wad_info, max_ticks=TICKS):
    log(f"  [{name}] {wad_info['label']}")
    actions = 0
    kills = 0
    t0 = time.monotonic()
    lockstep = {"stuck_count": 0, "consecutive_explore": 0, "last_tool": None}
    last_pos = None
    error = None

    try:
        async with McpDoomClient() as mcp:
            await mcp.start_game(
                wad=wad_info["iwad"], scenario_wad=wad_info["stored"],
                map_name=wad_info["map"], difficulty=DIFFICULTY,
                episode_timeout=max_ticks, seed=42,
            )
            log(f"  [{name}] game started, running...")

            while time.monotonic() - t0 < 200:
                state, screenshot = await mcp.get_state()
                tick = _extract_tick(state)
                done, reason = _extract_done(state)

                if done:
                    log(f"  [{name}] game over at tick={tick}: {reason}")
                    break
                if tick >= max_ticks:
                    log(f"  [{name}] tick limit reached: {tick}")
                    break

                # Detect stuck
                gv = state.get("game_variables") or {}
                if isinstance(gv, dict):
                    px = gv.get("POSITION_X", 0)
                    py = gv.get("POSITION_Y", 0)
                    cur_pos = (round(px, -1), round(py, -1))
                    if last_pos and cur_pos == last_pos:
                        lockstep["stuck_count"] = lockstep.get("stuck_count", 0) + 1
                    else:
                        lockstep["stuck_count"] = 0
                    last_pos = cur_pos

                # Track consecutive explores
                decision = agent.decide(state, lockstep, tick)
                tool = decision["tool"]
                if tool == "explore" and lockstep.get("last_tool") == "explore":
                    lockstep["consecutive_explore"] = lockstep.get("consecutive_explore", 0) + 1
                else:
                    lockstep["consecutive_explore"] = 0
                lockstep["last_tool"] = tool

                # Execute
                try:
                    await mcp.call_tool(tool, decision["params"])
                    actions += 1
                except Exception as e:
                    if "Episode is finished" in str(e):
                        log(f"  [{name}] episode finished at tick={tick}")
                        break
                    log(f"  [{name}] tool {tool} error: {str(e)[:80]}")
                    error = str(e)[:100]
                    break

                kills = _extract_kills(state)

                if actions % 10 == 0:
                    log(f"  [{name}] tick={tick} actions={actions} kills={kills}")

            try:
                await mcp.call_tool("finish", {"summary": f"baseline {name}", "outcome": "qa_completed"})
            except Exception:
                pass

    except Exception as e:
        log(f"  [{name}] FATAL: {e}")
        error = str(e)[:200]

    elapsed = int(time.monotonic() - t0)
    result = {
        "baseline": name, "wad": wad_key, "label": wad_info["label"],
        "outcome": "error" if error else "completed",
        "actions": actions, "time_s": elapsed, "kills": kills,
        "error": error,
    }
    log(f"  [{name}] DONE: acts={actions} kills={kills} time={elapsed}s err={bool(error)}")
    return result


async def run_bojack_via_api(wad_key, wad_info, max_ticks=TICKS):
    """Run BoJack through the backend API as the reference baseline."""
    import httpx
    API = "http://127.0.0.1:8000/v1"
    log(f"  [bojack] {wad_info['label']}")

    r = (await httpx.AsyncClient(timeout=600).post(f"{API}/runs", json={
        "wad_file_id": wad_info["wad_id"], "map_name": wad_info["map"],
        "difficulty_level": DIFFICULTY, "max_ticks": max_ticks,
    })).json()
    rid = r["id"]
    log(f"  [bojack] run {rid[:8]}")

    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=300) as c:
        while time.monotonic() - t0 < 250:
            run = (await c.get(f"{API}/runs/{rid}")).json()
            if run.get("status") in {"completed", "failed", "cancelled"}:
                pm = run.get("progress_metrics") or {}
                defects = (await c.get(f"{API}/runs/{rid}/defects")).json()
                result = {
                    "baseline": "bojack", "wad": wad_key, "label": wad_info["label"],
                    "outcome": run.get("outcome") or "?",
                    "coverage": float(pm.get("coverage_percent", 0) or 0),
                    "actions": run.get("total_actions_taken") or 0,
                    "defects": len(defects),
                    "time_s": run.get("duration_seconds") or int(time.monotonic() - t0),
                    "kills": run.get("total_kills") or 0,
                }
                log(f"  [bojack] {result['outcome']} | acts={result['actions']} | kills={result['kills']} | {result['time_s']}s")
                return result
            await asyncio.sleep(3)

    return {"baseline": "bojack", "wad": wad_key, "outcome": "timeout", "actions": 0, "time_s": 250, "kills": 0}


WAD_IDS = {
    "antony": "18e5310b-ab5d-4e44-a901-8c8f5df2277f",
    "hallways": "fc2a223b-eb86-4416-9d6b-4b83231a09f0",
    "map02": "acc96700-09a1-4ada-b4aa-7b68d5528ace",
}
for k in WADS:
    WADS[k]["wad_id"] = WAD_IDS[k]


async def main():
    log("=" * 70)
    log("BASELINE AGENT COMPARISON (3 WADs × 3 agents)")
    log("=" * 70)

    all_results = []

    for wad_key, wad_info in WADS.items():
        log(f"\n{'='*50}")
        log(f"WAD: {wad_info['label']}")
        log(f"{'='*50}")

        # 1. BoJack via API
        r = await run_bojack_via_api(wad_key, wad_info)
        all_results.append(r)

        # 2. Random agent
        r = await run_baseline("random", RandomBaseline(seed=42), wad_key, wad_info)
        all_results.append(r)

        # 3. Guard-only agent
        r = await run_baseline("guard_only", GuardOnlyBaseline(), wad_key, wad_info)
        all_results.append(r)

    # Summary
    log("\n" + "=" * 95)
    log("COMBINED BASELINE RESULTS")
    log("=" * 95)
    hdr = f"{'WAD':<28} {'Agent':<12} {'Outcome':<14} {'Acts':>5} {'Kills':>5} {'Time':>5}"
    log(hdr)
    log("-" * len(hdr))
    for r in all_results:
        lbl = r.get("label", r["wad"])[:27]
        oc = str(r.get("outcome", "?"))[:13]
        log(f"{lbl:<28} {r['baseline']:<12} {oc:<14} {r.get('actions',0):>5} {r.get('kills',0):>5} {r.get('time_s',0):>4}s")

    path = "/tmp/bojack_baseline_comparison.json"
    with open(path, "w") as f:
        json.dump({"results": all_results, "metadata": {"wads": {k: v["label"] for k, v in WADS.items()}, "ticks": TICKS}}, f, indent=2, default=str)
    log(f"\nSaved to {path}")


asyncio.run(main())
