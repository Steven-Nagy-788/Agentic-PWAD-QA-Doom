ENEMY_TYPES: dict[int, tuple[str, int, bool]] = {
    3004: ("ZOMBIEMAN", 20, True),
    9: ("SHOTGUN_GUY", 30, True),
    65: ("CHAINGUNNER", 70, True),
    3001: ("IMP", 60, False),
    3002: ("DEMON", 150, False),
    58: ("SPECTRE", 150, False),
    3006: ("LOST_SOUL", 100, False),
    3005: ("CACODEMON", 400, False),
    69: ("HELL_KNIGHT", 500, False),
    3003: ("BARON_OF_HELL", 1000, False),
    68: ("ARACHNOTRON", 500, False),
    71: ("PAIN_ELEMENTAL", 400, False),
    66: ("REVENANT", 300, False),
    67: ("MANCUBUS", 600, False),
    64: ("ARCHVILE", 700, False),
    7: ("SPIDER_MASTERMIND", 3000, True),
    16: ("CYBERDEMON", 4000, False),
}

ITEM_TYPES: dict[int, tuple[str, int, str]] = {
    2014: ("HEALTH_BONUS", 1, "health"),
    2011: ("STIMPACK", 10, "health"),
    2012: ("MEDIKIT", 25, "health"),
    2015: ("ARMOR_BONUS", 1, "armor"),
    2018: ("GREEN_ARMOR", 100, "armor"),
    2019: ("BLUE_ARMOR", 200, "armor"),
    8: ("BACKPACK", 20, "ammo"),
    2007: ("CLIP", 10, "ammo"),
    2008: ("SHELLS", 4, "ammo"),
    2010: ("ROCKET", 1, "ammo"),
    2047: ("CELL", 20, "ammo"),
    2002: ("CHAINGUN", 40, "weapon"),
    2003: ("ROCKET_LAUNCHER", 2, "weapon"),
    2004: ("PLASMA_RIFLE", 40, "weapon"),
    2005: ("CHAINSAW", 0, "weapon"),
    2006: ("BFG9000", 40, "weapon"),
    2001: ("SHOTGUN", 8, "weapon"),
    82: ("SUPER_SHOTGUN", 8, "weapon"),
}

KEY_TYPES = {5, 13, 6, 39, 38, 40}
WEAPON_TYPES = {2001, 2002, 2003, 2004, 2005, 2006, 82}
