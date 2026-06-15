# Object Database

Enriched metadata for 70+ Doom entity types used by both the LLM prompt and compound actions. Located in `mcp-doom/src/doom_mcp/objects.py` (~688 lines).

## Schema

Each entity entry:

| Field | Type | Description |
|-------|------|-------------|
| `type` | str | Category: monster/weapon/ammo/health/armor/key/powerup/projectile/decor/player |
| `threat` | str | Threat level: extreme/high/medium/low/none |
| `attack` | str | Attack type: melee/ranged/projectile/hitscan/none |
| `speed` | int | Movement speed (game units) |
| `typical_hp` | int | Typical hit points |
| `description` | str | Gameplay-relevant description |

## Monsters (20)

| Doom Name | Threat | Attack | HP | Notes |
|-----------|--------|--------|----|-------|
| ZombieMan | low | hitscan | 20 | Pistol zombie |
| ShotgunGuy | low | hitscan | 30 | Shotgun soldier |
| ChaingunGuy | medium | hitscan | 70 | Chaingun soldier |
| DoomImp | medium | projectile | 60 | Fireball thrower |
| Demon | medium | melee | 150 | Pinky, closes fast |
| Spectre | medium | melee | 150 | Invisible pinky |
| LostSoul | medium | melee | 100 | Flying skull |
| Cacodemon | high | projectile | 400 | Floating eye |
| PainElemental | high | projectile | 400 | Spawns Lost Souls |
| HellKnight | high | melee | 500 | Green baron |
| BaronOfHell | extreme | projectile | 1000 | Pink baron |
| Revenant | high | projectile | 300 | Homing missiles |
| Arachnotron | high | hitscan | 500 | Plasma spider |
| Fatso (Mancubus) | high | projectile | 600 | Dual fireballer |
| Archvile | extreme | ranged | 700 | Resurrection + flame attack |
| Cyberdemon | extreme | projectile | 4000 | Rocket launcher boss |
| SpiderMastermind | extreme | hitscan | 3000 | Chaingun boss |
| MarineChainsawVzd | medium | melee | 100 | ViZDoom custom marine |

## Projectiles (9)

DoomImpBall, BaronBall, CacodemonBall, RevenantTracer, ArachnotronPlasma, FatShot, Rocket, PlasmaBall, BFGBall.

## Health Items (8)

| Type | HP Restore | Notes |
|------|-----------|-------|
| HealthBonus | +1 | Small green cross |
| Stimpack | +10 | Green cross |
| Medikit | +25 | Red cross |
| Soulsphere | +100 | Max 200 |
| Megasphere | +200 | Full health+armor |
| Berserk | +100 | + fist damage |

## Armor (3)

ArmorBonus (+1), GreenArmor (+100), BlueArmor (+200).

## Ammo (8)

Clip (10 bullets), ClipBox (50), Shell (4), ShellBox (20), RocketAmmo (1), RocketBox (5), Cell (20), CellPack (100).

## Weapons (7)

| Weapon | Slot | Ammo Type | Priority |
|--------|------|-----------|----------|
| Chainsaw | 1 | None | 7 (melee) |
| Shotgun | 3 | Shells | 4 |
| SuperShotgun | 3 | Shells | 3 |
| Chaingun | 4 | Bullets | 5 |
| RocketLauncher | 5 | Rockets | 2 |
| PlasmaRifle | 6 | Cells | 1 |
| BFG9000 | 7 | Cells | 0 (highest) |

## Keys (6)

BlueCard, RedCard, YellowCard, BlueSkull, RedSkull, YellowSkull.

## Powerups (6)

Backpack (ammo capacity +2x), Allmap (full automap), Infrared (night vision), BlurSphere (partial invisibility), RadSuit (radiation suit), InvulnerabilitySphere (invulnerable).

## Other

- **DoomPlayer**: type=player, threat=none
- **ExplosiveBarrel**: type=decor, threat=none (but explosive!)

## Decorations (30+)

All mapped to a shared `_DECORATION` template: type=decor, threat=none, attack=none, speed=0, typical_hp=999999, description="Decorative/ambient".

## Lookup

`get_object_info(name) -> dict`:
- Exact match by Doom class name
- ViZDoom `PLAYER` → DoomPlayer
- Unknown names → generic fallback entry
