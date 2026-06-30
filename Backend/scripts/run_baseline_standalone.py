#!/usr/bin/env python3
"""Standalone baseline agent comparison — directly drives MCP game loop."""

import asyncio
import json
import random
import sys
import time
from datetime import datetime

sys.path.insert(0, "/media/steven/MaD/matznysh-hna/Agentic-PWAD-QA-Doom/Backend")

from app.services.mcp_client_service import McpDoomClient, normalize_mcp_state
from app.services.baseline_agents import RandomAgent, GuardOnlyAgent

API_BASE = "http://127.0.0.1:8000/v1"
TICKS = 500
DIFFICULTY = 3

WADS = {
    "antony": {
        "wad_id": "18e5310b-ab5d-4e44-a901-8c8f5df2277f",
        "iwad": "freedoom2",
        "map": "MAP01",
        "label": "antony.wad MAP01 (12e)",
    },
    "hallways": {
        "wad_id": "fc2a223b-eb86-4416-9d6b-4b83231a09f0",
        "iwad": "freedoom1",
        "map": "E1M1",
        "label": "thelonghallways E1M1 (8e)",
    },
    "map02": {
        "wad_id": "acc96700-09a1-4ada-b4aa-7b68d5528ace",
        "iwad": "freedoom2",
        "map": "MAP01",
        "label": "MAP02.wad MAP01 (2e)",
    },
}

import httpx


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _get_wad_stored_path(wad_id: str) -> str | None:
    """Get the stored WAD path from the DB via API (or construct from known pattern)."""
    # stored_path is /app/storage/wads/<uuid>.wad inside Docker
    return f"/app/storage/wads/{wad_id}.wad"


async def run_baseline_on_wad(
    baseline_name: str,
    wad_key: str,
    wad_info: dict,
    max_ticks: int = TICKS,
) -> dict:
    """Run a single baseline agent on a single WAD/map."""
    log(f"  [{baseline_name}] starting on {wad_info['label']}")

    agent = None
    if baseline_name == "random":
        agent = RandomAgent(seed=42)
    elif baseline_name == "guard_only":
        agent = GuardOnlyAgent()
    elif baseline_name == "bojack":
        # BoJack uses the API run loop — skip standalone, record as N/A
        return {
            "baseline": "bojack",
            "wad": wad_key,
            "outcome": "use_api",
            "coverage": 0,
            "actions": 0,
            "defects": 0,
            "time_s": 0,
            "kills": 0,
        }
    else:
        raise ValueError(f"Unknown baseline: {baseline_name}")

    stored_path = _get_wad_stored_path(wad_info["wad_id"])
    log(f"  [{baseline_name}] stored_path={stored_path}")

    lockstep_state = {}
    actions = 0
    defects = 0
    t0 = time.monotonic()

    try:
        async with McpDoomClient() as mcp:
            await mcp.start_game(
                wad=wad_info["iwad"],
                scenario_wad=stored_path,
                map_name=wad_info["map"],
                difficulty=DIFFICULTY,
                episode_timeout=max_ticks,
                seed=42,
            )
            log(f"  [{baseline_name}] game started")

            while time.monotonic() - t0 < 250:
                elapsed_ticks = int(time.monotonic() - t0)

                # Get game state
                state, screenshot = await mcp.get_state()
                game_vars = state.get("game_variables", {})
                current_tick = game_vars.get("GAME_TIC", 0)
                done = state.get("done", False)
                player_dead = game_vars.get("DEAD", False)

                if done or player_dead or current_tick >= max_ticks:
                    log(f"  [{baseline_name}] game over: done={done} dead={player_dead} tick={current_tick}")
                    break

                # Get agent decision
                decision = agent.decide(state, lockstep_state, current_tick)
                tool = decision.get("mcp_tool", "explore")
                params = decision.get("mcp_params", {})

                # Execute on MCP
                try:
                    result = await mcp.call_tool(tool, params)
                except Exception as e:
                    log(f"  [{baseline_name}] tool {tool} failed: {e}")
                    break

                actions += 1

                # Count kills from state
                new_kills = game_vars.get("KILLCOUNT", 0)

                # Update lockstep state
                lockstep_state["consecutive_get_state"] = lockstep_state.get("consecutive_get_state", 0) + 1
                if tool != "get_state":
                    lockstep_state["consecutive_get_state"] = 0

                if actions % 5 == 0:
                    log(f"  [{baseline_name}] tick={current_tick} actions={actions} tool={tool}")

            # Try to finish
            try:
                await mcp.call_tool("finish", {"summary": f"Baseline {baseline_name} run", "outcome": "qa_completed"})
            except Exception:
                pass

    except Exception as e:
        log(f"  [{baseline_name}] ERROR: {e}")
        return {
            "baseline": baseline_name,
            "wad": wad_key,
            "outcome": "error",
            "coverage": 0,
            "actions": actions,
            "defects": 0,
            "time_s": int(time.monotonic() - t0),
            "kills": 0,
            "error": str(e)[:200],
        }

    elapsed = int(time.monotonic() - t0)

    # Get final state for metrics
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            runs = (await client.get(f"{API_BASE}/runs?limit=1")).json().get("items", [])
            if runs:
                last_run = runs[0]
                pm = last_run.get("progress_metrics") or {}
                coverage = float(pm.get("coverage_percent", 0) or 0)
                defects = last_run.get("defects_detected", 0) or 0
            else:
                coverage = 0
    except Exception:
        coverage = 0

    result = {
        "baseline": baseline_name,
        "wad": wad_key,
        "outcome": "completed",
        "coverage": coverage,
        "actions": actions,
        "defects": defects,
        "time_s": elapsed,
        "kills": game_vars.get("KILLCOUNT", 0) if "game_vars" in dir() else 0,
    }
    log(f"  [{baseline_name}] DONE: {result}")
    return result


async def main():
    log("=" * 70)
    log("BOJACK BASELINE AGENT COMPARISON (standalone MCP)")
    log("=" * 70)

    all_results = []
    baselines = ["random", "guard_only"]

    for wad_key, wad_info in WADS.items():
        log(f"\n=== {wad_info['label']} ===")
        for bl in baselines:
            r = await run_baseline_on_wad(bl, wad_key, wad_info)
            all_results.append(r)

    # Print table
    log("\n" + "=" * 90)
    log("BASELINE COMPARISON RESULTS")
    log("=" * 90)
    header = f"{'WAD':<30} {'Baseline':<18} {'Outcome':<14} {'Actions':>8} {'Time':>6}"
    log(header)
    log("-" * len(header))
    for r in all_results:
        wad_label = WADS.get(r["wad"], {}).get("label", r["wad"])[:29]
        oc = str(r.get("outcome", "?"))[:13]
        log(f"{wad_label:<30} {r['baseline']:<18} {oc:<14} {r['actions']:>8} {r['time_s']:>5}s")

    # Save
    output = {"results": all_results, "metadata": {"wads": {k: v["label"] for k, v in WADS.items()}, "baselines": baselines, "max_ticks": TICKS, "date": datetime.now().isoformat()}}
    path = "/tmp/bojack_baseline_standalone.json"
    with open(path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    log(f"\nSaved to {path}")


asyncio.run(main())
