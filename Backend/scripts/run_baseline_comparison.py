#!/usr/bin/env python3
"""Baseline comparison runner for BoJack.

Runs the same WAD+map through different baseline agents (random, guard_only, pure_llm)
and compares them against the full BoJack system.

Usage:
    python scripts/run_baseline_comparison.py --wad-id <UUID> --map MAP01 [--ticks 1000]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

API_BASE = "http://127.0.0.1:8000/v1"


async def create_run(
    client: httpx.AsyncClient,
    wad_file_id: str,
    map_name: str,
    max_ticks: int = 1000,
    difficulty: int = 3,
    behavior_profile: str = "thorough",
) -> dict:
    """Create a test run via the API."""
    payload = {
        "wad_file_id": wad_file_id,
        "map_name": map_name,
        "difficulty_level": difficulty,
        "max_ticks": max_ticks,
        "behavior_profile": behavior_profile,
    }
    resp = await client.post(f"{API_BASE}/runs", json=payload)
    resp.raise_for_status()
    return resp.json()


async def wait_for_run(
    client: httpx.AsyncClient, run_id: str, timeout: float = 600.0
) -> dict:
    """Poll run status until completed."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        resp = await client.get(f"{API_BASE}/runs/{run_id}")
        resp.raise_for_status()
        run = resp.json()
        status = run.get("status")
        if status in {"completed", "failed", "cancelled"}:
            return run
        await asyncio.sleep(5)
    raise TimeoutError(f"Run {run_id} did not complete within {timeout}s")


async def get_defects(client: httpx.AsyncClient, run_id: str) -> list[dict]:
    """Get defects for a run."""
    resp = await client.get(f"{API_BASE}/runs/{run_id}/defects")
    resp.raise_for_status()
    return resp.json()


async def run_baseline(
    client: httpx.AsyncClient,
    baseline_name: str,
    wad_file_id: str,
    map_name: str,
    max_ticks: int,
    config_overrides: dict | None = None,
) -> dict:
    """Run a single baseline configuration."""
    print(f"\n{'='*60}")
    print(f"Running baseline: {baseline_name}")
    print(f"{'='*60}")

    # Apply config overrides if provided
    if config_overrides:
        resp = await client.patch(f"{API_BASE}/settings", json=config_overrides)
        if resp.status_code != 200:
            print(f"  WARNING: Failed to apply config: {resp.text}")

    # Create and wait for run
    run = await create_run(client, wad_file_id, map_name, max_ticks)
    run_id = run["id"]
    print(f"  Run created: {run_id}")

    start_time = time.monotonic()
    result = await wait_for_run(client, run_id)
    elapsed = time.monotonic() - start_time

    # Get defects
    defects = await get_defects(client, run_id)

    # Extract metrics
    progress_metrics = result.get("progress_metrics") or {}
    coverage = 0.0
    if isinstance(progress_metrics, dict):
        coverage = float(progress_metrics.get("coverage_percent", 0) or 0)

    return {
        "baseline_name": baseline_name,
        "run_id": run_id,
        "outcome": result.get("outcome", "unknown"),
        "coverage_percent": coverage,
        "defects_detected": len(defects),
        "total_actions": result.get("total_actions_taken", 0),
        "duration_seconds": result.get("duration_seconds", int(elapsed)),
        "total_llm_calls": result.get("total_llm_calls", 0),
    }


def format_table(results: list[dict]) -> str:
    """Format results as a markdown table."""
    header = "| Baseline | Outcome | Coverage% | Defects | Actions | LLM Calls | Time(s) |"
    separator = "|----------|---------|-----------|---------|---------|-----------|---------|"
    rows = [header, separator]
    for r in results:
        row = (
            f"| {r['baseline_name']:<20s} "
            f"| {r['outcome']:<9s} "
            f"| {r['coverage_percent']:>7.1f}% "
            f"| {r['defects_detected']:>7d} "
            f"| {r['total_actions']:>7d} "
            f"| {r['total_llm_calls']:>9d} "
            f"| {r['duration_seconds']:>7d} |"
        )
        rows.append(row)
    return "\n".join(rows)


async def main():
    parser = argparse.ArgumentParser(description="Run baseline comparison study")
    parser.add_argument("--wad-id", required=True, help="WAD file UUID")
    parser.add_argument("--map", required=True, help="Map name (e.g., MAP01)")
    parser.add_argument("--ticks", type=int, default=1000, help="Max ticks per run")
    parser.add_argument("--output", default=None, help="Output JSON file path")
    args = parser.parse_args()

    async with httpx.AsyncClient(timeout=600.0) as client:
        # Check API is up
        try:
            resp = await client.get(f"{API_BASE}/runs?limit=1")
            resp.raise_for_status()
        except Exception as e:
            print(f"ERROR: Cannot reach API at {API_BASE}: {e}")
            print("Make sure the backend is running: docker compose up")
            sys.exit(1)

        # Reset any overrides first
        await client.post(f"{API_BASE}/settings/ablation/reset")

        results = []

        # 1. Full system (guard_enabled=True, cross_run_memory=True)
        result = await run_baseline(
            client, "full_system (BoJack)", args.wad_id, args.map, args.ticks,
            config_overrides={"guard_enabled": True, "cross_run_memory_enabled": True},
        )
        results.append(result)
        print(f"  Result: {json.dumps(result, indent=2)}")

        # Reset between runs
        await client.post(f"{API_BASE}/settings/ablation/reset")

        # 2. No guards (guard_enabled=False)
        result = await run_baseline(
            client, "no_guards (pure LLM)", args.wad_id, args.map, args.ticks,
            config_overrides={"guard_enabled": False, "cross_run_memory_enabled": True},
        )
        results.append(result)
        print(f"  Result: {json.dumps(result, indent=2)}")

        # Reset between runs
        await client.post(f"{API_BASE}/settings/ablation/reset")

        # 3. No cross-run memory
        result = await run_baseline(
            client, "no_memory (no cross-run)", args.wad_id, args.map, args.ticks,
            config_overrides={"guard_enabled": True, "cross_run_memory_enabled": False},
        )
        results.append(result)
        print(f"  Result: {json.dumps(result, indent=2)}")

        # Reset at end
        await client.post(f"{API_BASE}/settings/ablation/reset")

        # Print summary
        print("\n" + "=" * 60)
        print("BASELINE COMPARISON RESULTS")
        print("=" * 60)
        print(format_table(results))

        # Save JSON if requested
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(json.dumps(results, indent=2))
            print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
