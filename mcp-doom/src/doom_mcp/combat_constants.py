"""Shared combat classification constants for threat scoring."""

THREAT_WEIGHTS: dict[str, int] = {"none": 0, "low": 1, "medium": 2, "high": 3}
ATTACK_URGENCY: dict[str, int] = {"hitscan": 3, "projectile": 2, "melee": 1, "none": 0}
