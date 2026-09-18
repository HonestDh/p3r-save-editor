"""Human-readable index tables for the Persona 3 Reload ``SaveDataArea`` block.

The game keeps almost every gameplay value in one flat array of UInt32 words.
The words have no names, so the mapping below was derived from the public
``Luckyseer/p3r-save-editor`` tables (verified against retail Steam saves) and
from the native type definitions referenced there.

Save format versions differ by a constant index shift: version 1 tables need
``+0`` and version 2 needs ``+4``.
"""

from __future__ import annotations

from dataclasses import dataclass

VERSION_INDEX_OFFSET = {1: 0, 2: 4}

PLAY_TIME_TICKS_PER_SECOND = 30

SOCIAL_STATS = [
    ("academics", "Academics", 5352, [(0, "Slacker"), (20, "Average"), (55, "Above Average"),
                                      (100, "Smart"), (155, "Intelligent"), (230, "Genius")]),
    ("charm", "Charm", 5354, [(0, "Plain"), (15, "Unpolished"), (30, "Confident"),
                              (45, "Smooth"), (70, "Popular"), (100, "Charismatic")]),
    ("courage", "Courage", 5356, [(0, "Timid"), (15, "Ordinary"), (30, "Determined"),
                                  (45, "Tough"), (60, "Fearless"), (80, "Badass")]),
]

SOCIAL_LINKS = [
    ("SEES", "Fool", 5300),
    ("Kenji Tomochika", "Magician", 5302),
    ("Fuuka Yamagishi", "Priestess", 5304),
    ("Mitsuru Kirijo", "Empress", 5306),
    ("Hidetoshi Odagiri", "Emperor", 5308),
    ("Bunkichi & Mitsuko", "Hierophant", 5310),
    ("Yukari Takeba", "Lovers", 5312),
    ("Kazushi Miyamoto", "Chariot", 5314),
    ("Chihiro Fushimi", "Justice", 5316),
    ("Maya", "Hermit", 5318),
    ("Keisuke Hiraga", "Fortune", 5320),
    ("Yuko Nishiwaki", "Strength", 5322),
    ("Maiko Oohashi", "Hanged", 5324),
    ("Pharos", "Death", 5326),
    ("Bebe", "Temperance", 5328),
    ("President Tanaka", "Devil", 5330),
    ("Mutatsu", "Tower", 5332),
    ("Mamoru Hayase", "Star", 5334),
    ("Nozomi Suemitsu", "Moon", 5336),
    ("Akinari Kamiki", "Sun", 5338),
    ("Nyx Annihilation Team", "Judgement", 5340),
    ("Aigis", "Aeon", 5342),
]

PARTY_MEMBERS = [
    {"key": "protagonist", "name": "Protagonist", "id": 1, "hp": 13070},
    {"key": "yukari", "name": "Yukari", "id": 2, "hp": 13246},
    {"key": "junpei", "name": "Junpei", "id": 3, "hp": 13422},
    {"key": "akihiko", "name": "Akihiko", "id": 4, "hp": 13598},
    {"key": "mitsuru", "name": "Mitsuru", "id": 5, "hp": 13774},
    {"key": "fuuka", "name": "Fuuka", "id": 6, "hp": 13950, "navigator": True},
    {"key": "aigis", "name": "Aigis", "id": 7, "hp": 14126},
    {"key": "koromaru", "name": "Koromaru", "id": 8, "hp": 14302},
    {"key": "ken", "name": "Ken", "id": 9, "hp": 14478},
    {"key": "shinjiro", "name": "Shinjiro", "id": 10, "hp": 14654},
]

# Offsets relative to each member's HP word.
PARTY_FIELDS = {"hp": 0, "sp": 1, "level": 17, "experience": 18}

# Percent offsets blocked out by the item bag, relative to ITEM_BAG_ARRAY_BASE.
ITEM_CATEGORIES = [
    ("Weapons", 0x0000, 1024),
    ("Armor", 0x0400, 1024),
    ("Footwear", 0x0800, 1024),
    ("Accessories", 0x0c00, 512),
    ("Items", 0x0e00, 1024),
    ("Event Items", 0x1200, 256),
    ("Materials", 0x1300, 1024),
    ("Skill Cards", 0x1700, 1024),
    ("Costumes", 0x1b00, 512),
]

ITEM_BAG_ARRAY_BASE = {1: 5368, 2: 5372}
DIFFICULTY_WORD_INDEX = 384
DIFFICULTY_FLAG_MASK = 0x0003E000
DIFFICULTIES = [
    (0, "Peaceful", 0x00002000),
    (1, "Easy", 0x00004000),
    (2, "Normal", 0x00008000),
    (3, "Hard", 0x00010000),
    (4, "Merciless", 0x00020000),
]

CORE_FIELDS = [
    ("money", "Yen", 7257, 0, 9_999_999),
    ("playTime", "Play time (s)", 12832, 0, 999 * 3600 + 59 * 60),
]

PERSONA_STOCK_BASE = 13086
PERSONA_ENTRY_WORDS = 12
PERSONA_SLOT_COUNT = 12
COMPENDIUM_BASE = 7261
COMPENDIUM_ENTRY_COUNT = 464
PERSONA_VALID_FLAG = 0x0001


def shift(version: int) -> int:
    return VERSION_INDEX_OFFSET.get(version, 0)


def social_stat_level(levels, points: int) -> str:
    label = levels[0][1]
    for threshold, name in levels:
        if points >= threshold:
            label = name
    return label


@dataclass
class AreaView:
    """Groups the flat SaveDataArea words into labelled buckets."""

    words: dict

    def get(self, index: int):
        return self.words.get(index)

    def core(self, version: int):
        base = shift(version)
        out = []
        for key, label, index, low, high in CORE_FIELDS:
            raw = self.get(index + base)
            value = raw
            if key == "playTime" and raw is not None:
                value = raw // PLAY_TIME_TICKS_PER_SECOND
            out.append({"key": key, "label": label, "index": index + base,
                        "value": value, "min": low, "max": high})
        return out

    def social(self, version: int):
        base = shift(version)
        stats = []
        for key, label, index, levels in SOCIAL_STATS:
            value = self.get(index + base)
            stats.append({"key": key, "label": label, "index": index + base,
                          "value": value,
                          "rank": None if value is None else social_stat_level(levels, value)})
        links = []
        for label, arcana, index in SOCIAL_LINKS:
            value = self.get(index + base)
            links.append({"label": label, "arcana": arcana, "index": index + base,
                          "value": value, "rank": None if value is None else value & 0xFF})
        return stats, links

    def party(self, version: int):
        base = shift(version)
        out = []
        for member in PARTY_MEMBERS:
            hp_index = member["hp"] + base
            entry = {"key": member["key"], "name": member["name"], "id": member["id"]}
            for field, delta in PARTY_FIELDS.items():
                value = self.get(hp_index + delta)
                if field == "level" and value is not None:
                    value &= 0xFFFF
                entry[field] = value
            out.append(entry)
        return out

    def find_difficulty_index(self, version: int) -> int | None:
        """Locate the word holding the difficulty one-hot flag.

        The published tables pin this to index 384 (format version 1), but
        retail version-2 saves omit that word, so fall back to scanning for a
        word whose masked bits are exactly one known difficulty flag.
        """
        base = shift(version)
        candidates = {dflag for _id, _name, dflag in DIFFICULTIES}
        preferred = DIFFICULTY_WORD_INDEX + base
        if self.get(preferred) is not None:
            flag = self.get(preferred) & DIFFICULTY_FLAG_MASK
            if flag in candidates:
                return preferred
        for index, word in sorted(self.words.items()):
            if word is None:
                continue
            flag = word & DIFFICULTY_FLAG_MASK
            if flag in candidates:
                return index
        return None

    def difficulty(self, version: int):
        index = self.find_difficulty_index(version)
        if index is None:
            return None
        word = self.get(index)
        flag = word & DIFFICULTY_FLAG_MASK
        for did, name, dflag in DIFFICULTIES:
            if dflag == flag:
                return {"id": did, "name": name, "index": index}
        return {"id": None, "name": f"unknown (0x{flag:x})", "index": index}
