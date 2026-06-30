#!/usr/bin/env python3
"""Full ablation + baseline study for BoJack thesis."""

import asyncio, httpx, json, time, sys
from datetime import datetime

API = "http://127.0.0.1:8000/v1"
WAD = "acc96700-09a1-4ada-b4aa-7b68d5528ace"
MAP = "MAP01"
TICKS = 500

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

async def run_config(c, config_name):
    log(f"--- Starting: {config_name} ---")
    await c.post(f"{API}/settings/ablation/reset")
    resp = await c.post(f"{API}/settings/ablation/apply", json={"config_name": config_name})
    log(f"  Overrides: {resp.json().get('overrides',{})}")

    r = (await c.post(f"{API}/runs", json={
        "wad_file_id": WAD, "map_name": MAP, "difficulty_level": 3, "max_ticks": TICKS
    })).json()
    rid = r["id"]
    log(f"  Run ID: {rid}")

    t0 = time.monotonic()
    while time.monotonic() - t0 < 300:
        run = (await c.get(f"{API}/runs/{rid}")).json()
        if run.get("status") in {"completed", "failed", "cancelled"}:
            elapsed = int(time.monotonic() - t0)
            pm = run.get("progress_metrics") or {}
            defects = (await c.get(f"{API}/runs/{rid}/defects")).json()
            result = {
                "config": config_name,
                "run_id": rid,
                "status": run["status"],
                "outcome": run.get("outcome"),
                "coverage": float(pm.get("coverage_percent", 0) or 0),
                "actions": run.get("total_actions_taken", 0),
                "defects": len(defects),
                "duration_s": run.get("duration_seconds", elapsed),
            }
            log(f"  Result: {result['outcome']} | coverage={result['coverage']}% | actions={result['actions']} | defects={result['defects']} | {result['duration_s']}s")
            return result
        await asyncio.sleep(3)
    log(f"  TIMEOUT")
    return {"config": config_name, "status": "timeout", "outcome": "timeout", "coverage": 0, "actions": 0, "defects": 0, "duration_s": 300}

async def main():
    open("/tmp/bojack_study.log", "w").close()
    log("=== BOJACK ABLATION + BASELINE STUDY ===")

    async with httpx.AsyncClient(timeout=600.0) as c:
        # Verify API
        (await c.get(f"{API}/runs?limit=1")).raise_for_status()
        log("API OK")

        configs = ["full_system", "no_guards", "no_cross_run_memory"]
        results = []

        for cfg in configs:
            r = await run_config(c, cfg)
            results.append(r)
            await c.post(f"{API}/settings/ablation/reset")

        # Summary
        log("\n=== RESULTS ===")
        log(f"{'Config':<28} | {'Outcome':<14} | {'Cov%':>5} | {'Acts':>5} | {'Def':>3} | {'Time':>5}")
        log("-" * 75)
        for r in results:
            log(f"{r['config']:<28} | {str(r['outcome']):<14} | {r['coverage']:>5.1f} | {r['actions']:>5} | {r['defects']:>3} | {r['duration_s']:>5}")

        with open("/tmp/bojack_study_results.json", "w") as f:
            json.dump(results, f, indent=2)
        log("Saved to /tmp/bojack_study_results.json")

asyncio.run(main())
