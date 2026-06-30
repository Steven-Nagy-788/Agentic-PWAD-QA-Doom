#!/usr/bin/env python3
"""Ablation study runner for BoJack.

Runs the same WAD+map through each ablation configuration,
collects results, and outputs a comparison table.

Usage:
    python scripts/run_ablation_study.py --wad-id <UUID> --map MAP01 [--runs 1] [--ticks 1000]
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
) -> dict:
    """Create a test run via the API."""
    payload = {
        "wad_file_id": wad_file_id,
        "map_name": map_name,
        "difficulty_level": difficulty,
        "max_ticks": max_ticks,
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


async def run_ablation_config(
    client: httpx.AsyncClient,
    config_name: str,
    wad_file_id: str,
    map_name: str,
    max_ticks: int,
    apply_config_url: str,
    reset_config_url: str,
) -> dict:
    """Run a single ablation configuration."""
    print(f"\n{'='*60}")
    print(f"Running config: {config_name}")
    print(f"{'='*60}")

    # Apply config
    resp = await client.post(
        apply_config_url, json={"config_name": config_name}
    )
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
        "config_name": config_name,
        "run_id": run_id,
        "outcome": result.get("outcome", "unknown"),
        "coverage_percent": coverage,
        "defects_detected": len(defects),
        "total_actions": result.get("total_actions_taken", 0),
        "duration_seconds": result.get("duration_seconds", int(elapsed)),
        "guard_interventions": sum(
            1 for d in defects
            if "guard" in (d.get("defect_type") or "").lower()
        ),
    }


def format_table(results: list[dict]) -> str:
    """Format results as a markdown table."""
    header = "| Config | Outcome | Coverage% | Defects | Actions | Time(s) |"
    separator = "|--------|---------|-----------|---------|---------|---------|"
    rows = [header, separator]
    for r in results:
        row = (
            f"| {r['config_name']:<25s} "
            f"| {r['outcome']:<9s} "
            f"| {r['coverage_percent']:>7.1f}% "
            f"| {r['defects_detected']:>7d} "
            f"| {r['total_actions']:>7d} "
            f"| {r['duration_seconds']:>7d} |"
        )
        rows.append(row)
    return "\n".join(rows)


def format_deltas(results: list[dict]) -> str:
    """Compute deltas vs baseline and format."""
    baseline = next((r for r in results if r["config_name"] == "full_system"), None)
    if not baseline:
        return "No full_system baseline found."

    lines = [
        "\n## Component Contributions (vs full_system baseline)\n",
        f"Baseline: coverage={baseline['coverage_percent']:.1f}%, "
        f"defects={baseline['defects_detected']}, "
        f"actions={baseline['total_actions']}",
        "",
        "| Config | Coverage Δ | Defects Δ | Actions Δ |",
        "|--------|-----------|-----------|-----------|",
    ]
    for r in results:
        if r["config_name"] == "full_system":
            continue
        cov_delta = r["coverage_percent"] - baseline["coverage_percent"]
        def_delta = r["defects_detected"] - baseline["defects_detected"]
        act_delta = r["total_actions"] - baseline["total_actions"]
        lines.append(
            f"| {r['config_name']:<25s} "
            f"| {cov_delta:>+7.1f}% "
            f"| {def_delta:>+7d} "
            f"| {act_delta:>+7d} |"
        )
    return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser(description="Run ablation study")
    parser.add_argument("--wad-id", required=True, help="WAD file UUID")
    parser.add_argument("--map", required=True, help="Map name (e.g., MAP01)")
    parser.add_argument("--ticks", type=int, default=1000, help="Max ticks per run")
    parser.add_argument(
        "--configs",
        nargs="*",
        default=None,
        help="Specific configs to run (default: all)",
    )
    parser.add_argument("--output", default=None, help="Output JSON file path")
    args = parser.parse_args()

    configs_to_run = args.configs or [
        "full_system",
        "no_guards",
        "no_cross_run_memory",
    ]

    async with httpx.AsyncClient(timeout=600.0) as client:
        # Check API is up
        try:
            resp = await client.get(f"{API_BASE}/runs?limit=1")
            resp.raise_for_status()
        except Exception as e:
            print(f"ERROR: Cannot reach API at {API_BASE}: {e}")
            print("Make sure the backend is running: docker compose up")
            sys.exit(1)

        results = []
        for config_name in configs_to_run:
            result = await run_ablation_config(
                client,
                config_name,
                args.wad_id,
                args.map,
                args.ticks,
                f"{API_BASE}/settings/ablation/apply",
                f"{API_BASE}/settings/ablation/reset",
            )
            results.append(result)
            print(f"  Result: {json.dumps(result, indent=2)}")

        # Print summary
        print("\n" + "=" * 60)
        print("ABLATION STUDY RESULTS")
        print("=" * 60)
        print(format_table(results))
        print(format_deltas(results))

        # Save JSON if requested
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(json.dumps(results, indent=2))
            print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
