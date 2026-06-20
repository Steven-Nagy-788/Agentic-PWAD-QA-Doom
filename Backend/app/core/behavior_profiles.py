from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


BehaviorProfileName = Literal["thorough", "fast", "exploit_focused"]


@dataclass
class BehaviorProfile:
    name: BehaviorProfileName
    description: str
    system_prompt_addendum: str
    throttle_delays: dict[str, float]
    allowlist_overrides: list[str] | None = None


# ── Thorough ──────────────────────────────────────────────
# Focus: methodical, every room, every corner, maximum coverage
THOROUGH = BehaviorProfile(
    name="thorough",
    description="Slow, methodical exploration. Checks every room, every corner. Maximum coverage.",
    system_prompt_addendum=(
        "You are a senior QA tester. Your primary goal is 100% coverage. "
        "Move slowly and check every room, corridor, and interactable element. "
        "After each move, verify you can see new geometry. "
        "If you find a door, try opening it. If you find a lift, step on it. "
        "Look for HOM effects, misaligned textures, missing geometry, and softlocks. "
        "Report every anomaly you find with precise position coordinates. "
        "NEVER call finish() until coverage >= 90% and all enemies are killed."
    ),
    throttle_delays={
        "combat": 0.5,
        "low_health": 0.75,
        "stuck": 2.0,
        "default": 1.5,
    },
)

# ── Fast ──────────────────────────────────────────────
# Focus: cover ground quickly, prioritise breadth over depth
FAST = BehaviorProfile(
    name="fast",
    description="Covers ground quickly. Prioritises breadth over exhaustive single-room inspection.",
    system_prompt_addendum=(
        "You are a senior QA tester. Your primary goal is 100% coverage. "
        "Move briskly through accessible areas to cover as much of the map as possible. "
        "Engage visible enemies, collect visible pickups, and probe doors/switches as you pass. "
        "Do not spend excessive ticks in a single room — if nothing blocks progress, move on. "
        "Report any doors, lifts, or teleporters that block your path as defects. "
        "Prioritise covering new cells over re-examining areas you have already seen. "
        "NEVER call finish() until coverage >= 90% and all enemies are killed."
    ),
    throttle_delays={
        "combat": 0.1,
        "low_health": 0.25,
        "stuck": 0.8,
        "default": 0.4,
    },
)

# ── Exploit-Focused ───────────────────────────────────
# Focus: find crash bugs, softlocks, out-of-bounds, broken mechanics
EXPLOIT_FOCUSED = BehaviorProfile(
    name="exploit_focused",
    description="Aggressively tests boundaries. Tries to break the map. Jumps, wall-hugs, spam-uses.",
    system_prompt_addendum=(
        "You are a senior QA tester. Your primary goal is finding crash bugs. "
        "Stress-test every interactable you find. Try these techniques: "
        "walk into walls, spam 'use' on lines repeatedly, "
        "try to walk off ledges, hug walls and turn, interact with everything multiple times. "
        "Report crashes, freezes, stuck states, visual glitches, and out-of-bounds positions. "
        "Be aggressive — if something works once, do it five more times to check for instability. "
        "NEVER call finish() until coverage >= 90% and all enemies are killed."
    ),
    throttle_delays={
        "combat": 0.05,
        "low_health": 0.1,
        "stuck": 0.2,
        "default": 0.1,
    },
)

PROFILES: dict[BehaviorProfileName, BehaviorProfile] = {
    "thorough": THOROUGH,
    "fast": FAST,
    "exploit_focused": EXPLOIT_FOCUSED,
}


def get_profile(name: BehaviorProfileName) -> BehaviorProfile:
    return PROFILES[name]
