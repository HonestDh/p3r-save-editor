"""Inventory, Persona stock and party formation access for P3R saves.

Layouts were derived from the public ``Luckyseer/p3r-save-editor`` tables:

* Item bag: byte array at ``ITEM_BAG_ARRAY_BASE[version]``, four bytes per word.
  An item ID packs its category in the high nibble and a local index below it.
* Persona stock: ``PERSONA_SLOT_COUNT`` records of ``PERSONA_ENTRY_WORDS`` words
  starting at ``PERSONA_STOCK_BASE``.
* Compendium: 464 persona records starting at ``COMPENDIUM_BASE``.
* Party formation: five words of packed u16 character IDs at
  ``PARTY_FORMATION_BASE``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from p3r_fields import shift

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

ITEM_BAG_ARRAY_BASE = {1: 5368, 2: 5372}
RECENT_ITEMS_OFFSET = 0x1D00
RECENT_ITEMS_COUNT = 30

ITEM_CATEGORIES = [
    (0, "Weapons", 0x0000, 1024),
    (1, "Armor", 0x0400, 1024),
    (2, "Footwear", 0x0800, 1024),
    (3, "Accessories", 0x0C00, 512),
    (4, "Items", 0x0E00, 1024),
    (5, "Event Items", 0x1200, 256),
    (6, "Materials", 0x1300, 1024),
    (7, "Skill Cards", 0x1700, 1024),
    (8, "Costumes", 0x1B00, 512),
]

PERSONA_STOCK_BASE = 13086
PERSONA_ENTRY_WORDS = 12
PERSONA_SLOT_COUNT = 12
PERSONA_SKILL_SLOT_COUNT = 8
PERSONA_VALID_FLAG = 0x0001

COMPENDIUM_BASE = 7261
COMPENDIUM_ENTRY_COUNT = 464

PARTY_FORMATION_BASE = 5360
PARTY_FORMATION_WORD_COUNT = 5
MAX_PARTY_ALLIES = 3

MONEY_INDEX = 7257
PLAY_TIME_INDEX = 12832

PERSONA_STAT_NAMES = ("Strength", "Magic", "Endurance", "Agility", "Luck")


class DataError(Exception):
    pass


def _load(name: str):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


_items = None
_personas = None
_skills = None


def items() -> list:
    global _items
    if _items is None:
        _items = _load("items.json")
    return _items


def personas() -> list:
    global _personas
    if _personas is None:
        _personas = _load("personas.json")
    return _personas


def skills() -> list:
    global _skills
    if _skills is None:
        _skills = _load("skills.json")
    return _skills


def persona_by_id(persona_id: int):
    for entry in personas():
        if entry["id"] == persona_id:
            return entry
    return None


def skill_name(skill_id: int) -> str:
    for entry in skills():
        if entry["id"] == skill_id:
            return entry["name"]
    return f"Skill {skill_id}"


def item_name(item_id: int) -> str:
    category = item_id >> 12
    local = item_id & 0x0FFF
    for entry in items():
        if entry.get("category") == category and (entry.get("id", 0) & 0x0FFF) == local:
            return entry["name"]
    return f"Item 0x{item_id:04X}"


def items_in_category(category: int) -> list:
    return [entry for entry in items()
            if entry.get("category") == category and not entry.get("unused")]


@dataclass
class Inventory:
    words: dict
    version: int

    @property
    def base(self) -> int:
        return ITEM_BAG_ARRAY_BASE.get(self.version, ITEM_BAG_ARRAY_BASE[2])

    def _location(self, item_id: int):
        category = item_id >> 12
        local = item_id & 0x0FFF
        definition = next((c for c in ITEM_CATEGORIES if c[0] == category), None)
        if definition is None or local >= definition[3]:
            raise DataError(f"unsupported item id 0x{item_id:04X}")
        byte_offset = definition[2] + local
        return self.base + byte_offset // 4, byte_offset % 4

    def quantity(self, item_id: int) -> int:
        index, lane = self._location(item_id)
        return (self.words.get(index, 0) >> (lane * 8)) & 0xFF

    def set_quantity(self, item_id: int, quantity: int) -> None:
        if not 0 <= quantity <= 99:
            raise DataError("quantity must be 0-99")
        index, lane = self._location(item_id)
        old = self.words.get(index, 0)
        mask = ~(0xFF << (lane * 8)) & 0xFFFFFFFF
        self.words[index] = (old & mask) | (quantity << (lane * 8))

    def owned(self) -> list:
        out = []
        for category, name, _offset, size in ITEM_CATEGORIES:
            for local in range(size):
                item_id = (category << 12) | local
                quantity = self.quantity(item_id)
                if quantity:
                    out.append({"id": item_id, "category": name,
                                "name": item_name(item_id), "quantity": quantity})
        return out

    def recent(self) -> list:
        start = self.base + RECENT_ITEMS_OFFSET // 4
        out = []
        for i in range(RECENT_ITEMS_COUNT):
            word = self.words.get(start + i, 0)
            item_id = word & 0xFFFF
            if item_id:
                out.append({"id": item_id, "name": item_name(item_id)})
        return out


@dataclass
class PersonaSlot:
    slot: int
    flags: int = 0
    id: int = 0
    level: int = 0
    experience: int = 0
    skills: list = field(default_factory=list)
    stats: list = field(default_factory=lambda: [0, 0, 0, 0, 0])

    @property
    def name(self) -> str:
        if not self.id:
            return ""
        entry = persona_by_id(self.id)
        return entry["name"] if entry else f"Persona {self.id}"


@dataclass
class PersonaStock:
    words: dict
    version: int

    @property
    def base(self) -> int:
        return PERSONA_STOCK_BASE + shift(self.version)

    def slot_base(self, slot: int) -> int:
        if not 0 <= slot < PERSONA_SLOT_COUNT:
            raise DataError("invalid persona slot")
        return self.base + slot * PERSONA_ENTRY_WORDS

    def read(self, slot: int) -> PersonaSlot:
        base = self.slot_base(slot)
        identity = self.words.get(base, 0)
        skills = []
        for i in range(PERSONA_SKILL_SLOT_COUNT // 2):
            word = self.words.get(base + 3 + i, 0)
            skills.extend([word & 0xFFFF, (word >> 16) & 0xFFFF])
        word7 = self.words.get(base + 7, 0)
        return PersonaSlot(
            slot=slot,
            flags=identity & 0xFFFF,
            id=(identity >> 16) & 0xFFFF,
            level=self.words.get(base + 1, 0) & 0xFFFF,
            experience=self.words.get(base + 2, 0),
            skills=[s for s in skills if s],
            stats=[word7 & 0xFF, (word7 >> 8) & 0xFF, (word7 >> 16) & 0xFF,
                   (word7 >> 24) & 0xFF, self.words.get(base + 8, 0) & 0xFF],
        )

    def all_slots(self) -> list:
        return [self.read(slot) for slot in range(PERSONA_SLOT_COUNT)]

    def set_level(self, slot: int, level: int) -> None:
        if not 1 <= level <= 99:
            raise DataError("persona level must be 1-99")
        base = self.slot_base(slot)
        word = self.words.get(base + 1, 0)
        self.words[base + 1] = (word & 0xFFFF0000) | level

    def set_experience(self, slot: int, experience: int) -> None:
        if not 0 <= experience <= 9_999_999:
            raise DataError("persona experience must be 0-9,999,999")
        self.words[self.slot_base(slot) + 2] = experience

    def set_stat(self, slot: int, stat: int, value: int) -> None:
        if not 1 <= value <= 99:
            raise DataError("persona stats must be 1-99")
        base = self.slot_base(slot)
        if stat < 4:
            word = self.words.get(base + 7, 0)
            mask = ~(0xFF << (stat * 8)) & 0xFFFFFFFF
            self.words[base + 7] = (word & mask) | (value << (stat * 8))
        else:
            word = self.words.get(base + 8, 0)
            self.words[base + 8] = (word & 0xFFFFFF00) | value

    def clear(self, slot: int) -> None:
        base = self.slot_base(slot)
        for i in range(PERSONA_ENTRY_WORDS):
            self.words[base + i] = 0

    def initialize(self, slot: int, persona: dict, level: int | None = None) -> None:
        """Write a full Persona record into ``slot``."""
        base = self.slot_base(slot)
        stats = list(persona.get("stats") or [1, 1, 1, 1, 1])[:5]
        while len(stats) < 5:
            stats.append(1)
        skill_ids = []
        for entry in (persona.get("skills") or []):
            skill_ids.append(entry["id"] if isinstance(entry, dict) else entry)
        skill_ids = skill_ids[:PERSONA_SKILL_SLOT_COUNT]
        words = [0] * PERSONA_ENTRY_WORDS
        words[0] = ((persona["id"] & 0xFFFF) << 16) | PERSONA_VALID_FLAG
        words[1] = int(level if level is not None else persona.get("level", 1)) & 0xFFFF
        for i in range(4):
            low = skill_ids[i * 2] if i * 2 < len(skill_ids) else 0
            high = skill_ids[i * 2 + 1] if i * 2 + 1 < len(skill_ids) else 0
            words[3 + i] = ((high & 0xFFFF) << 16) | (low & 0xFFFF)
        words[7] = (stats[0] | (stats[1] << 8) | (stats[2] << 16) | (stats[3] << 24)) & 0xFFFFFFFF
        words[8] = stats[4] & 0xFF
        for i, value in enumerate(words):
            self.words[base + i] = value

    def set_persona(self, slot: int, persona: dict, level: int | None = None) -> None:
        """Place ``persona`` into ``slot`` and register it in the Compendium.

        The Persona menu expects every carried Persona to have a matching
        Compendium entry, otherwise the list can fail to load.
        """
        self.initialize(slot, persona, level)

    def set_skill(self, slot: int, skill_slot: int, skill_id: int) -> None:
        if not 0 <= skill_slot < PERSONA_SKILL_SLOT_COUNT:
            raise DataError("skill slot must be 0-7")
        if not 0 <= skill_id <= 0xFFFF:
            raise DataError("unsupported skill id")
        base = self.slot_base(slot)
        word_index = base + 3 + skill_slot // 2
        word = self.words.get(word_index, 0)
        if skill_slot % 2 == 0:
            self.words[word_index] = (word & 0xFFFF0000) | skill_id
        else:
            self.words[word_index] = (word & 0x0000FFFF) | (skill_id << 16)


@dataclass
class Compendium:
    words: dict
    version: int

    @property
    def base(self) -> int:
        return COMPENDIUM_BASE + shift(self.version)

    def entry_base(self, persona_id: int) -> int:
        if not 0 <= persona_id < COMPENDIUM_ENTRY_COUNT:
            raise DataError("persona id outside compendium range")
        return self.base + persona_id * PERSONA_ENTRY_WORDS

    def is_unlocked(self, persona_id: int) -> bool:
        identity = self.words.get(self.entry_base(persona_id), 0)
        flags = identity & 0xFFFF
        return ((identity >> 16) & 0xFFFF) == persona_id and bool(flags & PERSONA_VALID_FLAG)

    def set_unlocked(self, persona: dict, unlocked: bool) -> None:
        base = self.entry_base(persona["id"])
        if not unlocked:
            for i in range(PERSONA_ENTRY_WORDS):
                self.words[base + i] = 0
            return
        stats = list(persona.get("stats") or persona.get("baseStats") or [1, 1, 1, 1, 1])[:5]
        while len(stats) < 5:
            stats.append(1)
        skill_ids = [s["id"] if isinstance(s, dict) else s
                     for s in (persona.get("skills") or [])][:8]
        words = [0] * PERSONA_ENTRY_WORDS
        words[0] = ((persona["id"] & 0xFFFF) << 16) | PERSONA_VALID_FLAG
        words[1] = int(persona.get("level", 1)) & 0xFFFF
        for i in range(4):
            low = skill_ids[i * 2] if i * 2 < len(skill_ids) else 0
            high = skill_ids[i * 2 + 1] if i * 2 + 1 < len(skill_ids) else 0
            words[3 + i] = ((high & 0xFFFF) << 16) | (low & 0xFFFF)
        words[7] = (stats[0] | (stats[1] << 8) | (stats[2] << 16) | (stats[3] << 24)) & 0xFFFFFFFF
        words[8] = stats[4] & 0xFF
        for i, value in enumerate(words):
            self.words[base + i] = value


@dataclass
class PartyFormation:
    words: dict
    version: int

    @property
    def base(self) -> int:
        return PARTY_FORMATION_BASE + shift(self.version)

    def ids(self) -> list:
        out = []
        for i in range(PARTY_FORMATION_WORD_COUNT):
            word = self.words.get(self.base + i, 0)
            out.extend([word & 0xFFFF, (word >> 16) & 0xFFFF])
        first_empty = out.index(0) if 0 in out else len(out)
        return out[:first_empty]

    def set_ids(self, ids: list) -> None:
        ids = [int(i) & 0xFFFF for i in ids][:10]
        ids += [0] * (10 - len(ids))
        for i in range(PARTY_FORMATION_WORD_COUNT):
            self.words[self.base + i] = (ids[i * 2] | (ids[i * 2 + 1] << 16)) & 0xFFFFFFFF
