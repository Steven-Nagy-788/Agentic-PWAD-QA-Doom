from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


BehaviorProfileName = Literal["speedrunner", "safety", "exploit_hunter"]


@dataclass
class BehaviorProfile:
    name: BehaviorProfileName
    description: str
    system_prompt_addendum: str
    default_stride: int
    combat_stride: int
    stuck_stride: int
    throttle_delays: dict[str, float]
    allowlist_overrides: list[str] | None = None


# ── Speedrunner ──────────────────────────────────────────────
# Focus: reach the exit as fast as possible, minimal exploration
SPEEDRUNNER = BehaviorProfile(
    name="speedrunner",
    description="Moves fast toward the exit. Skips non-essential rooms. High stride at all times.",
    system_prompt_addendum=(
        "You are a SPEEDRUNNER. Your goal is to reach the exit as fast as possible. "
        "Focus on forward movement, ignore side rooms unless blocked. "
        "Call 'check_position' every 3-4 ticks instead of every tick. "
        "Report any doors, lifts, or teleporters that block your path as defects. "
        "Do NOT backtrack or explore side areas."
    ),
    default_stride=5,
    combat_stride=2,
    stuck_stride=10,
    throttle_delays={
        "move": 0.1,
        "turn": 0.1,
        "use": 0.3,
        "check_position": 0.8,
    },
)

# ── Safety ───────────────────────────────────────────────────
# Focus: thorough testing, slow and careful, report every anomaly
SAFETY = BehaviorProfile(
    name="safety",
    description="Slow, methodical exploration. Checks every room, every corner. Maximum coverage.",
    system_prompt_addendum=(
        "You are a SAFETY inspector. Your goal is to thoroughly test every room, corridor, "
        "and interactable element in the map. Move slowly, check your position after every step. "
        "If you find a door, try opening it. If you find a lift, step on it. "
        "Look for HOM effects, misaligned textures, missing geometry, and softlocks. "
        "Report every anomaly you find with precise position coordinates."
    ),
    default_stride=1,
    combat_stride=1,
    stuck_stride=2,
    throttle_delays={
        "move": 0.5,
        "turn": 0.3,
        "use": 0.5,
        "check_position": 0.3,
    },
)

# ── Exploit Hunter ───────────────────────────────────────────
# Focus: find crash bugs, softlocks, out-of-bounds, and broken mechanics
EXPLOIT_HUNTER = BehaviorProfile(
    name="exploit_hunter",
    description="Aggressively tests boundaries. Tries to break the map. Jumps, wall-hugs, spam-uses.",
    system_prompt_addendum=(
        "You are an EXPLOIT HUNTER. Your goal is to crash, break, or softlock the map. "
        "Try these techniques: walk into walls, spam 'use' on lines repeatedly, "
        "try to walk off ledges, hug walls and turn, interact with everything multiple times. "
        "Report crashes, freezes, stuck states, visual glitches, and out-of-bounds positions. "
        "Be aggressive — if something works once, do it five more times to check for instability."
    ),
    default_stride=1,
    combat_stride=1,
    stuck_stride=1,
    throttle_delays={
        "move": 0.05,
        "turn": 0.05,
        "use": 0.05,
        "check_position": 0.1,
    },
)

PROFILES: dict[BehaviorProfileName, BehaviorProfile] = {
    "speedrunner": SPEEDRUNNER,
    "safety": SAFETY,
    "exploit_hunter": EXPLOIT_HUNTER,
}


def get_profile(name: BehaviorProfileName) -> BehaviorProfile:
    return PROFILES[name]
