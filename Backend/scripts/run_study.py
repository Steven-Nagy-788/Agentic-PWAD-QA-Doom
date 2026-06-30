#!/usr/bin/env python3
"""Ablation + Baseline runner with logging."""

import asyncio
import httpx
import json
import time
import sys
from datetime import datetime

API_BASE = "http://127.0.0.1:8000/v1"
WAD_ID = "acc96700-09a1-4ada-b4aa-7b68d5528ace"  # MAP02.wad
MAP_NAME = "MAP01"
MAX_TICKS = 500
LOG_FILE = "/tmp/bojack_study.log"


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


async def create_run(client, config_label=""):
    payload = {
        "wad_file_id": WAD_ID,
        "map_name": MAP_NAME,
        "difficulty_level": 3,
        "max_ticks": MAX_TICKS,
    }
    log(f"  Creating run for {config_label}...")
    resp = await client.post(f"{API_BASE}/runs", json=payload)
    resp.raise_for_status()
    run = resp.json()
    log(f"  Run created: {run['id']}")
    return run


async def wait_for_run(client, run_id, timeout=300.0):
    start = time.monotonic()
    polls = 0
    while time.monotonic() - start < timeout:
        resp = await client.get(f"{API_BASE}/runs/{run_id}")
        resp.raise_for_status()
        run = resp.json()
        status = run.get("status")
        polls += 1
        if polls % 6 == 0:
            elapsed = time.monotonic() - start
            log(f"  ... polling ({int(elapsed)}s elapsed, status={status})")
        if status in {"completed", "failed", "cancelled"}:
            log(f"  Run finished: status={status} outcome={run.get('outcome')}")
            return run
        await asyncio.sleep(5)
    log(f"  TIMEOUT after {timeout}s")
    raise TimeoutError(f"Run {run_id} timed out")


async def get_defects(client, run_id):
    resp = await client.get(f"{API_BASE}/runs/{run_id}/defects")
    resp.raise_for_status()
    return resp.json()


async def run_single_config(client, config_name):
    log(f"\n{'='*60}")
    log(f"CONFIG: {config_name}")
    log(f"{'='*60}")

    # Apply config
    resp = await client.post(f"{API_BASE}/settings/ablation/apply", json={"config_name": config_name})
    applied = resp.json()
    log(f"  Applied overrides: {json.dumps(applied.get('overrides', {}))}")

    # Create and run
    run = await create_run(client, config_name)
    run_id = run["id"]

    start_time = time.monotonic()
    try:
        result = await wait_for_run(client, run_id, timeout=300)
    except TimeoutError:
        log(f"  Run {run_id} timed out, cancelling...")
        try:
            await client.post(f"{API_BASE}/runs/{run_id}/force-stop")
        except Exception:
            pass
        return {
            "config_name": config_name,
            "run_id": run_id,
            "outcome": "timeout",
            "coverage_percent": 0.0,
            "defects_detected": 0,
            "total_actions": 0,
            "duration_seconds": 300,
        }

    elapsed = time.monotonic() - start_time

    # Get defects
    defects = await get_defects(client, run_id)
    log(f"  Defects found: {len(defects)}")

    # Extract metrics
    progress_metrics = result.get("progress_metrics") or {}
    coverage = 0.0
    if isinstance(progress_metrics, dict):
        coverage = float(progress_metrics.get("coverage_percent", 0) or 0)

    r = {
        "config_name": config_name,
        "run_id": run_id,
        "outcome": result.get("outcome", "unknown"),
        "coverage_percent": coverage,
        "defects_detected": len(defects),
        "total_actions": result.get("total_actions_taken", 0),
        "duration_seconds": result.get("duration_seconds", int(elapsed)),
    }
    log(f"  Coverage: {coverage:.1f}%, Actions: {r['total_actions']}, Outcome: {r['outcome']}")
    return r


async def main():
    # Clear log
    open(LOG_FILE, "w").close()
    log("Starting ablation + baseline study")
    log(f"WAD: {WAD_ID}, Map: {MAP_NAME}, Max ticks: {MAX_TICKS}")

    async with httpx.AsyncClient(timeout=600.0) as client:
        # Check API
        try:
            resp = await client.get(f"{API_BASE}/runs?limit=1")
            resp.raise_for_status()
            log("API is reachable")
        except Exception as e:
            log(f"ERROR: Cannot reach API: {e}")
            sys.exit(1)

        # Reset
        await client.post(f"{API_BASE}/settings/ablation/reset")
        log("Reset config to defaults")

        # === ABLATION STUDY ===
        ablation_configs = ["full_system", "no_guards", "no_cross_run_memory"]
        ablation_results = []

        for config in ablation_configs:
            r = await run_single_config(client, config)
            ablation_results.append(r)
            await client.post(f"{API_BASE}/settings/ablation/reset")

        # Print ablation table
        log("\n" + "=" * 60)
        log("ABLATION STUDY RESULTS")
        log("=" * 60)
        log(f"{'Config':<28s} | {'Outcome':<12s} | {'Coverage':>8s} | {'Defects':>8s} | {'Actions':>8s}")
        log("-" * 80)
        for r in ablation_results:
            log(f"{r['config_name']:<28s} | {r['outcome']:<12s} | {r['coverage_percent']:>7.1f}% | {r['defects_detected']:>8d} | {r['total_actions']:>8d}")

        # === BASELINE COMPARISON ===
        log("\n\n" + "=" * 60)
        log("BASELINE COMPARISON")
        log("=" * 60)

        baseline_configs = ["full_system", "no_guards", "no_cross_run_memory"]
        baseline_results = []

        for config in baseline_configs:
            r = await run_single_config(client, config)
            baseline_results.append(r)
            await client.post(f"{API_BASE}/settings/ablation/reset")

        # Print baseline table
        log("\n" + "=" * 60)
        log("BASELINE COMPARISON RESULTS")
        log("=" * 60)
        log(f"{'Baseline':<28s} | {'Outcome':<12s} | {'Coverage':>8s} | {'Defects':>8s} | {'Actions':>8s}")
        log("-" * 80)
        for r in baseline_results:
            log(f"{r['config_name']:<28s} | {r['outcome']:<12s} | {r['coverage_percent']:>7.1f}% | {r['defects_detected']:>8d} | {r['total_actions']:>8d}")

        # Save results
        output = {
            "ablation_study": ablation_results,
            "baseline_comparison": baseline_results,
            "wad_id": WAD_ID,
            "map_name": MAP_NAME,
            "max_ticks": MAX_TICKS,
        }
        output_path = "/tmp/bojack_study_results.json"
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)
        log(f"\nResults saved to {output_path}")
        log("Study complete!")


if __name__ == "__main__":
    asyncio.run(main())
