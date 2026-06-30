#!/usr/bin/env python3
"""Multi-WAD ablation study for BoJack thesis."""

import asyncio, httpx, json, time
from datetime import datetime

API = "http://127.0.0.1:8000/v1"
TICKS = 500
DIFFICULTY = 3

WADS = {
    "antony": {"id": "18e5310b-ab5d-4e44-a901-8c8f5df2277f", "map": "MAP01", "enemies": 12, "label": "antony.wad MAP01 (12 enemies)"},
    "hallways": {"id": "fc2a223b-eb86-4416-9d6b-4b83231a09f0", "map": "E1M1", "enemies": 8, "label": "thelonghallways.wad E1M1 (8 enemies)"},
    "map02": {"id": "acc96700-09a1-4ada-b4aa-7b68d5528ace", "map": "MAP01", "enemies": 2, "label": "MAP02.wad MAP01 (2 enemies)"},
}

CONFIGS = ["full_system", "no_guards", "no_cross_run_memory"]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

async def run_one(c, wad_id, map_name, config_name, run_num, total):
    log(f"  [{run_num}/{total}] {config_name} ... ", )
    # Apply config
    await c.post(f"{API}/settings/ablation/reset")
    await c.post(f"{API}/settings/ablation/apply", json={"config_name": config_name})

    # Create run
    r = (await c.post(f"{API}/runs", json={
        "wad_file_id": wad_id, "map_name": map_name,
        "difficulty_level": DIFFICULTY, "max_ticks": TICKS
    })).json()
    rid = r["id"]
    log(f"  [{run_num}/{total}] {config_name} -> run {rid[:8]}")

    t0 = time.monotonic()
    while time.monotonic() - t0 < 300:
        run = (await c.get(f"{API}/runs/{rid}")).json()
        if run.get("status") in {"completed", "failed", "cancelled"}:
            elapsed = int(time.monotonic() - t0)
            pm = run.get("progress_metrics") or {}
            defects = (await c.get(f"{API}/runs/{rid}/defects")).json()
            result = {
                "config": config_name,
                "outcome": run.get("outcome") or "unknown",
                "coverage": float(pm.get("coverage_percent", 0) or 0),
                "actions": run.get("total_actions_taken") or 0,
                "defects": len(defects),
                "time_s": run.get("duration_seconds") or elapsed,
                "kills": run.get("total_kills") or 0,
                "error": run.get("error_message"),
            }
            status_icon = "OK" if result["outcome"] == "qa_completed" else result["outcome"][:6]
            log(f"  [{run_num}/{total}] {config_name} -> {status_icon} | cov={result['coverage']:.0f}% | acts={result['actions']} | def={result['defects']} | {result['time_s']}s")
            return result
        await asyncio.sleep(3)
    log(f"  [{run_num}/{total}] {config_name} -> TIMEOUT")
    return {"config": config_name, "outcome": "timeout", "coverage": 0, "actions": 0, "defects": 0, "time_s": 300, "kills": 0}

async def main():
    log("=" * 70)
    log("BOJACK MULTI-WAD ABLATION STUDY")
    log("=" * 70)

    all_results = {}
    total_runs = len(WADS) * len(CONFIGS)
    run_num = 0

    async with httpx.AsyncClient(timeout=600.0) as c:
        (await c.get(f"{API}/runs?limit=1")).raise_for_status()
        log("API OK\n")

        for wad_key, wad in WADS.items():
            log(f"--- {wad['label']} ---")
            wad_results = []
            for cfg in CONFIGS:
                run_num += 1
                r = await run_one(c, wad["id"], wad["map"], cfg, run_num, total_runs)
                r["wad"] = wad_key
                r["wad_label"] = wad["label"]
                r["map"] = wad["map"]
                r["enemies"] = wad["enemies"]
                wad_results.append(r)
            all_results[wad_key] = wad_results
            log("")

        # Reset config
        await c.post(f"{API}/settings/ablation/reset")

    # Print combined table
    log("=" * 100)
    log("COMBINED RESULTS")
    log("=" * 100)
    header = f"{'WAD':<30} {'Config':<22} {'Outcome':<16} {'Cov%':>5} {'Acts':>5} {'Def':>4} {'Kills':>5} {'Time':>5}"
    log(header)
    log("-" * len(header))
    for wad_key in WADS:
        for r in all_results[wad_key]:
            oc = str(r.get("outcome","?"))[:15]
            log(f"{r['wad_label'][:29]:<30} {r['config']:<22} {oc:<16} {r['coverage']:>4.0f}% {r['actions']:>5} {r['defects']:>4} {r['kills']:>5} {r['time_s']:>4}s")
        log("")

    # Save
    output = {
        "results": all_results,
        "metadata": {"wads": {k: {"id": v["id"], "map": v["map"], "enemies": v["enemies"]} for k, v in WADS.items()}, "configs": CONFIGS, "max_ticks": TICKS, "difficulty": DIFFICULTY, "date": datetime.now().isoformat()},
    }
    path = "/tmp/bojack_multiwad_results.json"
    with open(path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    log(f"\nSaved to {path}")

asyncio.run(main())
