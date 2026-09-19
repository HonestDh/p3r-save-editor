"""Persona 3 Reload save editor (GUI).

* Opens the game's obfuscated ``SaveDataNNN.sav`` files.
* Decodes them into a plain Unreal GVAS tree.
* Lets you edit numeric values, strings and enums.
* Writes the result back in the exact on-disk format.

The ``SaveDataArea`` block is a flat list of 10176 unnamed index/value pairs;
it is exposed as a hex grid so the raw game state stays reachable.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import p3r_codec
import p3r_data as data
import p3r_fields as fields
import p3r_gvas as gvas


class _WordProxy(dict):
    """index->value map that mirrors the live ``UInt32Property`` objects.

    The ``p3r_data`` helpers mutate whatever mapping they are handed, so this
    proxy funnels every write into the real save tree, creating records that a
    sparse ``SaveDataArea`` array does not contain yet.
    """

    def __init__(self, doc):
        super().__init__({i: p.value for i, p in doc.word_map().items()})
        self._doc = doc

    def __setitem__(self, key, value):
        value &= 0xFFFFFFFF
        dict.__setitem__(self, key, value)
        self._doc.ensure_word(key).value = value


class SaveDocument:
    def __init__(self, path: str):
        self.path = path
        with open(path, "rb") as fh:
            self.raw = fh.read()
        self.gvas = p3r_codec.decode(self.raw)
        self.save = gvas.SaveFile.loads(self.gvas)

    @property
    def header_struct(self) -> gvas.StructProperty:
        for prop in self.save.root:
            if isinstance(prop, gvas.StructProperty) and prop.name == "SaveDataHeadder":
                return prop
        raise gvas.GvasError("SaveDataHeadder not found")

    @property
    def areas(self) -> list[gvas.UInt32Property]:
        return [p for p in self.save.root if isinstance(p, gvas.UInt32Property)]

    @property
    def version(self) -> int:
        return self.save.header.save_game_version

    def word_map(self) -> dict:
        return {p.index: p for p in self.areas}

    def area_view(self) -> fields.AreaView:
        return fields.AreaView({i: p.value for i, p in self.word_map().items()})

    def inventory(self) -> data.Inventory:
        return data.Inventory(self._raw_words(), self.version)

    def persona_stock(self) -> data.PersonaStock:
        return data.PersonaStock(self._raw_words(), self.version)

    def compendium(self) -> data.Compendium:
        return data.Compendium(self._raw_words(), self.version)

    def formation(self) -> data.PartyFormation:
        return data.PartyFormation(self._raw_words(), self.version)

    def _raw_words(self) -> dict:
        """A plain index->int map that mirrors the live property objects."""
        return self._word_proxy()

    def set_word(self, index: int, value: int) -> None:
        prop = self.ensure_word(index)
        prop.value = value & 0xFFFFFFFF

    def ensure_word(self, index: int):
        """Return the live property for ``index``, creating the record if the
        SaveDataArea array is sparse (missing indexes) for this save."""
        prop = self.word_map().get(index)
        if prop is not None:
            return prop
        area_props = [p for p in self.save.root if isinstance(p, gvas.UInt32Property)]
        new_prop = gvas.UInt32Property("SaveDataArea", "UInt32Property", size=4, index=index, value=0)
        # keep the flat array sorted by index before the closing None record
        insert_before = area_props[-1] if area_props else None
        for prop in area_props:
            if prop.index > index:
                insert_before = prop
                break
        pos = self.save.root.index(insert_before) if insert_before else len(self.save.root) - 1
        self.save.root.insert(pos, new_prop)
        # keep the cached proxy in sync so later reads see the new entry
        cache = getattr(self, "_word_proxy_cache", None)
        if isinstance(cache, dict):
            dict.__setitem__(cache, index, 0)
        return new_prop

    def _word_proxy(self) -> _WordProxy:
        if getattr(self, "_word_proxy_cache", None) is None:
            self._word_proxy_cache = _WordProxy(self)
        return self._word_proxy_cache

    def save_to(self, path: str, backup: bool = True) -> None:
        data = p3r_codec.encode(self.save.dumps())
        if backup and os.path.exists(path) and os.path.abspath(path) != os.path.abspath(self.path):
            pass
        if os.path.abspath(path) == os.path.abspath(self.path):
            stamp = time.strftime("%Y%m%d-%H%M%S")
            backup_dir = os.path.join(os.path.dirname(path), "backup")
            os.makedirs(backup_dir, exist_ok=True)
            shutil.copy2(path, os.path.join(backup_dir, f"{stamp}_{os.path.basename(path)}"))
        with open(path, "wb") as fh:
            fh.write(data)


def decode_name(values: list[int]) -> str:
    """Reassemble a name that the game stored as a run of Int8 slots."""
    raw = bytes(v & 0xFF for v in values).rstrip(b"\x00")
    if not raw:
        return ""
    for encoding in ("utf-8", "utf-16-le", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.hex()


def encode_name(text: str, slots: int) -> list[int]:
    """Split a name into ``slots`` Int8 values, preferring UTF-8 like the game."""
    raw = text.encode("utf-8")
    if len(raw) > slots:
        raw16 = text.encode("utf-16-le")
        if len(raw16) <= slots:
            raw = raw16
        else:
            raise ValueError(
                f"name does not fit: needs {len(raw)} bytes, only {slots} available "
                f"(about {slots} latin / {slots // 2} non-latin characters)"
            )
    raw = raw.ljust(slots, b"\x00")
    return [b - 256 if b > 127 else b for b in raw]


def _or_blank(value):
    """Tuples stay tuples: Treeview values must be a flat sequence."""
    return ("",) if value is None else (value,)


def _parse_int(text: str) -> int:
    """Parse an integer the way a user expects.

    Accepts decimal, ``0x`` hex, and tolerates a leading zero (``08``) which
    ``int(text, 0)`` rejects.
    """
    body = text.strip()
    sign = 1
    if body[:1] in "+-":
        if body[0] == "-":
            sign = -1
        body = body[1:]
    if not body:
        raise ValueError(text)
    if body[:2].lower() in ("0x", "0b", "0o"):
        return sign * int(body, 0)
    if body.isdigit():
        return sign * int(body, 10)
    return sign * int(body, 0)


class PropertyRow:
    """One editable row in the field table."""

    def __init__(self, container, prop: gvas.Property):
        self.prop = prop
        self.var = tk.StringVar()
        if isinstance(prop, gvas.EnumProperty):
            self.var.set(prop.value)
        elif isinstance(prop, (gvas.StrProperty, gvas.NameProperty)):
            self.var.set(prop.value)
        elif isinstance(prop, gvas.FloatProperty):
            self.var.set(repr(prop.value))
        else:
            self.var.set(str(prop.value))

    def apply(self) -> None:
        prop = self.prop
        text = self.var.get().strip()
        if isinstance(prop, gvas.EnumProperty):
            prop.value = text
            return
        if isinstance(prop, (gvas.StrProperty, gvas.NameProperty)):
            prop.value = text
            return
        if isinstance(prop, gvas.BoolProperty):
            prop.value = text.lower() in ("1", "true", "yes", "on")
            return
        if text == "":
            raise ValueError(f"{prop.name} cannot be empty")
        try:
            if isinstance(prop, gvas.FloatProperty):
                prop.value = float(text)
            else:
                prop.value = _parse_int(text)
        except ValueError:
            raise ValueError(f"{prop.name}: '{text}' is not a valid number") from None

        limits = {
            "Int8Property": (-128, 127),
            "IntProperty": (-2_147_483_648, 2_147_483_647),
            "Int64Property": (-2**63, 2**63 - 1),
            "UInt16Property": (0, 65_535),
            "UInt32Property": (0, 4_294_967_295),
        }
        low_high = limits.get(prop.type)
        if low_high is not None and not low_high[0] <= prop.value <= low_high[1]:
            raise ValueError(f"{prop.name}: {prop.value} is outside {low_high[0]}..{low_high[1]}")


class EditorApp(tk.Tk):
    def __init__(self, path: str | None = None):
        super().__init__()
        self.title("Persona 3 Reload - Save Editor")
        self.geometry("980x680")
        self.doc: SaveDocument | None = None
        self.rows: list[PropertyRow] = []
        self.name_rows: dict[str, list[PropertyRow]] = {}
        self.name_slots: dict[str, int] = {}

        self._build_menu()
        self._build_widgets()
        if path:
            self.load(path)

    # ------------------------------------------------------------- interface
    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label="Open .sav...", command=self.on_open, accelerator="Ctrl+O")
        file_menu.add_command(label="Save", command=self.on_save, accelerator="Ctrl+S")
        file_menu.add_command(label="Save as...", command=self.on_save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menu.add_cascade(label="File", menu=file_menu)

        tools = tk.Menu(menu, tearoff=0)
        tools.add_command(label="Export decoded GVAS...", command=self.on_export_gvas)
        tools.add_command(label="Dump JSON...", command=self.on_dump_json)
        menu.add_cascade(label="Tools", menu=tools)
        self.config(menu=menu)
        self.bind_all("<Control-o>", lambda _e: self.on_open())
        self.bind_all("<Control-s>", lambda _e: self.on_save())

    def _build_widgets(self) -> None:
        top = ttk.Frame(self, padding=6)
        top.pack(fill="x")
        ttk.Button(top, text="Open", command=self.on_open).pack(side="left")
        ttk.Button(top, text="Apply changes", command=self.on_apply).pack(side="left", padx=4)
        ttk.Button(top, text="Save", command=self.on_save).pack(side="left")
        self.status = tk.StringVar(value="Open a SaveDataNNN.sav file to begin.")
        ttk.Label(top, textvariable=self.status).pack(side="left", padx=12)

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=6, pady=6)

        self.fields_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.fields_tab, text="Fields")
        self._build_fields_tab()

        self.gameplay_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.gameplay_tab, text="Gameplay")
        self._build_gameplay_tab(  # populated on load
        )

        self.party_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.party_tab, text="Party")
        self._build_party_tab()

        self.items_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.items_tab, text="Items")
        self._build_items_tab()

        self.personas_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.personas_tab, text="Personas")
        self._build_personas_tab()

        self.compendium_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.compendium_tab, text="Compendium")
        self._build_compendium_tab()

        self.raw_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.raw_tab, text="Raw area")
        self._build_raw_tab()

    def _build_fields_tab(self) -> None:
        self.fields_canvas = tk.Canvas(self.fields_tab, highlightthickness=0)
        bar = ttk.Scrollbar(self.fields_tab, orient="vertical", command=self.fields_canvas.yview)
        self.fields_frame = ttk.Frame(self.fields_canvas)
        self.fields_frame.bind(
            "<Configure>",
            lambda _e: self.fields_canvas.configure(scrollregion=self.fields_canvas.bbox("all")),
        )
        self.fields_canvas.create_window((0, 0), window=self.fields_frame, anchor="nw")
        self.fields_canvas.configure(yscrollcommand=bar.set)
        self.fields_canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

    # ------------------------------------------------------------ gameplay tab
    def _build_gameplay_tab(self) -> None:
        wrapper = ttk.Frame(self.gameplay_tab, padding=8)
        wrapper.pack(fill="both", expand=True)
        self.core_vars: dict[str, tk.StringVar] = {}
        self.stat_vars: dict[str, tk.StringVar] = {}
        self.link_vars: dict[str, tk.StringVar] = {}

        box = ttk.LabelFrame(wrapper, text="Core", padding=8)
        box.pack(fill="x")
        self._row(box, "Yen", "money", self.core_vars, width=24)
        self._row(box, "Play time (s)", "playTime", self.core_vars, width=24)

        box = ttk.LabelFrame(wrapper, text="Social stats", padding=8)
        box.pack(fill="x", pady=(10, 0))
        for key, label, _index, _levels in fields.SOCIAL_STATS:
            row = ttk.Frame(box)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=label, width=14, anchor="w").pack(side="left")
            var = tk.StringVar()
            ttk.Entry(row, textvariable=var, width=10).pack(side="left")
            ttk.Label(row, textvariable=var).pack_forget()
            self.stat_vars[key] = var
            rank_label = ttk.Label(row, text="", foreground="#666")
            rank_label.pack(side="left", padx=8)
            self.stat_vars[key + "__rank"] = rank_label  # type: ignore[assignment]

        box = ttk.LabelFrame(wrapper, text="Social links (rank 0-10)", padding=8)
        box.pack(fill="both", expand=True, pady=(10, 0))
        grid = ttk.Frame(box)
        grid.pack(fill="both", expand=True)
        for i, (label, arcana, _index) in enumerate(fields.SOCIAL_LINKS):
            col = i % 2
            row_i = i // 2
            cell = ttk.Frame(grid)
            cell.grid(row=row_i, column=col, sticky="ew", padx=4, pady=1)
            grid.columnconfigure(col, weight=1)
            ttk.Label(cell, text=f"{label} ({arcana})", width=28, anchor="w").pack(side="left")
            var = tk.StringVar()
            ttk.Entry(cell, textvariable=var, width=6).pack(side="left")
            self.link_vars[str(_index)] = var

    def _row(self, parent, label, key, store, width=24):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=1)
        ttk.Label(row, text=label, width=14, anchor="w").pack(side="left")
        var = tk.StringVar()
        ttk.Entry(row, textvariable=var, width=width).pack(side="left")
        store[key] = var
        return var

    # --------------------------------------------------------------- party tab
    def _build_party_tab(self) -> None:
        wrapper = ttk.Frame(self.party_tab, padding=8)
        wrapper.pack(fill="both", expand=True)
        self.party_vars: dict[tuple, tk.StringVar] = {}
        columns = ("name", "level", "hp", "sp", "experience")
        self.party_tree = ttk.Treeview(wrapper, columns=columns, show="headings", height=12)
        for col, title, width in (("name", "Member", 140), ("level", "Level", 80),
                                  ("hp", "HP", 90), ("sp", "SP", 90), ("experience", "EXP", 120)):
            self.party_tree.heading(col, text=title)
            self.party_tree.column(col, width=width, anchor="center" if col != "name" else "w")
        self.party_tree.pack(fill="both", expand=True)
        self.party_tree.bind("<Double-1>", self.on_party_edit)

        self.diff_var = tk.StringVar()
        diff_row = ttk.Frame(wrapper)
        diff_row.pack(fill="x", pady=8)
        ttk.Label(diff_row, text="Difficulty", width=14, anchor="w").pack(side="left")
        ttk.Entry(diff_row, textvariable=self.diff_var, width=20).pack(side="left")
        ttk.Label(diff_row, text="(0 Peaceful, 1 Easy, 2 Normal, 3 Hard, 4 Merciless)",
                  foreground="#666").pack(side="left", padx=8)

    # --------------------------------------------------------------- items tab
    def _build_items_tab(self) -> None:
        wrapper = ttk.Frame(self.items_tab, padding=6)
        wrapper.pack(fill="both", expand=True)

        top = ttk.Frame(wrapper)
        top.pack(fill="x", pady=(0, 4))
        ttk.Label(top, text="Category").pack(side="left")
        self.item_category = tk.StringVar(value="All")
        values = ["All", "Owned only"] + [name for _c, name, _o, _s in data.ITEM_CATEGORIES]
        combo = ttk.Combobox(top, textvariable=self.item_category, values=values, state="readonly", width=18)
        combo.pack(side="left", padx=6)
        combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_items())
        self.item_search = tk.StringVar()
        ttk.Label(top, text="Search").pack(side="left", padx=(12, 0))
        search = ttk.Entry(top, textvariable=self.item_search, width=22)
        search.pack(side="left", padx=6)
        search.bind("<KeyRelease>", lambda _e: self.refresh_items())
        ttk.Label(top, text="Double-click a row to change the quantity.",
                  foreground="#666").pack(side="left", padx=12)

        columns = ("id", "name", "category", "quantity")
        self.items_tree = ttk.Treeview(wrapper, columns=columns, show="headings", height=20)
        for col, title, width, anchor in (("id", "ID", 80, "center"), ("name", "Item", 280, "w"),
                                          ("category", "Category", 130, "w"), ("quantity", "Qty", 70, "center")):
            self.items_tree.heading(col, text=title)
            self.items_tree.column(col, width=width, anchor=anchor)
        bar = ttk.Scrollbar(wrapper, orient="vertical", command=self.items_tree.yview)
        self.items_tree.configure(yscrollcommand=bar.set)
        self.items_tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.items_tree.bind("<Double-1>", self.on_item_edit)

    # ------------------------------------------------------------ personas tab
    def _build_personas_tab(self) -> None:
        wrapper = ttk.Frame(self.personas_tab, padding=6)
        wrapper.pack(fill="both", expand=True)

        panes = ttk.PanedWindow(wrapper, orient="horizontal")
        panes.pack(fill="both", expand=True)

        left = ttk.Frame(panes)
        panes.add(left, weight=3)
        ttk.Label(left, text="Persona stock (double-click a field to edit)").pack(anchor="w")
        columns = ("slot", "name", "level", "strength", "magic", "endurance", "agility", "luck")
        self.persona_tree = ttk.Treeview(left, columns=columns, show="headings", height=16)
        titles = ("Slot", "Persona", "Lv", "Str", "Mag", "End", "Agl", "Luk")
        widths = (50, 170, 50, 50, 50, 50, 50, 50)
        for col, title, width in zip(columns, titles, widths):
            self.persona_tree.heading(col, text=title)
            self.persona_tree.column(col, width=width, anchor="center" if col != "name" else "w")
        self.persona_tree.pack(fill="both", expand=True)
        self.persona_tree.bind("<Double-1>", self.on_persona_edit)

        actions = ttk.Frame(left)
        actions.pack(fill="x", pady=4)
        ttk.Button(actions, text="Set Persona...", command=self.on_set_persona).pack(side="left")
        ttk.Button(actions, text="Clear slot", command=self.on_clear_persona).pack(side="left", padx=4)

        right = ttk.Frame(panes)
        panes.add(right, weight=2)
        ttk.Label(right, text="Skills of the selected Persona").pack(anchor="w")
        self.skill_tree = ttk.Treeview(right, columns=("slot", "skill"), show="headings", height=10)
        self.skill_tree.heading("slot", text="#")
        self.skill_tree.heading("skill", text="Skill")
        self.skill_tree.column("slot", width=40, anchor="center")
        self.skill_tree.column("skill", width=180, anchor="w")
        self.skill_tree.pack(fill="both", expand=True)
        self.skill_tree.bind("<Double-1>", self.on_skill_edit)
        self.persona_tree.bind("<<TreeviewSelect>>", lambda _e: self.refresh_skills())

        formation = ttk.LabelFrame(wrapper, text="Party formation (protagonist + up to 3 allies)", padding=6)
        formation.pack(fill="x", pady=(8, 0))
        self.formation_var = tk.StringVar()
        ttk.Entry(formation, textvariable=self.formation_var, width=40).pack(side="left", padx=(0, 8))
        ttk.Label(formation, text="e.g. 1, 2, 5, 4  (1=Protagonist, 2=Yukari, 3=Junpei, 4=Akihiko, "
                                  "5=Mitsuru, 6=Fuuka, 7=Aigis, 8=Koromaru, 9=Ken, 10=Shinjiro)",
                  foreground="#666").pack(side="left")

    # ------------------------------------------- persona placement handlers
    def on_set_persona(self) -> None:
        if self.doc is None:
            return
        selection = self.persona_tree.selection()
        if not selection:
            messagebox.showinfo("No slot", "Select a Persona slot first.")
            return
        slot_index = int(selection[0])
        dialog = tk.Toplevel(self)
        dialog.title(f"Set Persona in slot {slot_index + 1}")
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog, text="Persona").grid(row=0, column=0, padx=8, pady=6, sticky="w")
        ttk.Label(dialog, text="Level (blank = default)").grid(row=1, column=0, padx=8, pady=6, sticky="w")
        names = [f"{p['name']}  (id {p['id']}, lv {p.get('level', 1)})" for p in data.personas()]
        name_var = tk.StringVar(value=names[0])
        level_var = tk.StringVar()
        combo = ttk.Combobox(dialog, textvariable=name_var, values=names, width=42, state="readonly")
        combo.grid(row=0, column=1, padx=8, pady=6)
        ttk.Entry(dialog, textvariable=level_var, width=12).grid(row=1, column=1, padx=8, pady=6, sticky="w")

        def ok() -> None:
            index = names.index(name_var.get())
            persona = data.personas()[index]
            level = None
            if level_var.get().strip():
                try:
                    level = int(level_var.get(), 0)
                except ValueError:
                    messagebox.showerror("Invalid level", "Level must be a number.")
                    return
                if not 1 <= level <= 99:
                    messagebox.showerror("Invalid level", "Level must be between 1 and 99.")
                    return
            self.doc.persona_stock().set_persona(slot_index, persona, level)
            self.doc.compendium().set_unlocked(persona, True)
            dialog.destroy()
            self.refresh_personas()
            self.refresh_compendium()
            self.status.set(f"{persona['name']} placed in slot {slot_index + 1} and registered in the Compendium.")

        ttk.Button(dialog, text="OK", command=ok).grid(row=2, column=0, columnspan=2, pady=(4, 12))

    def on_clear_persona(self) -> None:
        if self.doc is None:
            return
        selection = self.persona_tree.selection()
        if not selection:
            return
        slot_index = int(selection[0])
        slot = self.doc.persona_stock().read(slot_index)
        if not slot.id:
            return
        if not messagebox.askyesno("Clear slot", f"Remove {slot.name} from slot {slot_index + 1}?"):
            return
        self.doc.persona_stock().clear(slot_index)
        self.refresh_personas()

    # ------------------------------------------------ compendium handlers
    def refresh_compendium(self) -> None:
        if self.doc is None:
            return
        compendium = self.doc.compendium()
        needle = self.compendium_search.get().strip().lower()
        owned_only = self.compendium_owned_only.get()
        tree = self.compendium_tree
        tree.delete(*tree.get_children())
        for persona in data.personas():
            unlocked = compendium.is_unlocked(persona["id"])
            if owned_only and not unlocked:
                continue
            if needle and needle not in persona["name"].lower() and needle not in str(persona["id"]):
                continue
            tree.insert("", "end", iid=str(persona["id"]),
                        values=(persona["id"], persona["name"], persona.get("arcana", ""),
                                persona.get("level", ""), "registered" if unlocked else "not registered"),
                        tags=("unlocked" if unlocked else "locked",))

    def on_compendium_toggle(self, event) -> None:
        item = self.compendium_tree.identify_row(event.y)
        if not item:
            return
        persona_id = int(item)
        persona = data.persona_by_id(persona_id)
        if persona is None:
            return
        compendium = self.doc.compendium()
        unlocked = compendium.is_unlocked(persona_id)
        compendium.set_unlocked(persona, not unlocked)
        self.refresh_compendium()

    # ------------------------------------------------------- items handlers
    def refresh_items(self) -> None:
        if self.doc is None:
            return
        inventory = self.doc.inventory()
        category = self.item_category.get()
        needle = self.item_search.get().strip().lower()
        tree = self.items_tree
        tree.delete(*tree.get_children())
        if category == "Owned only":
            rows = inventory.owned()
        else:
            rows = []
            for category_id, name, _offset, size in data.ITEM_CATEGORIES:
                if category not in ("All", name):
                    continue
                for local in range(size):
                    item_id = (category_id << 12) | local
                    row = data.item_name(item_id)
                    if row.startswith("Item 0x"):
                        continue  # skip ids with no reference name
                    rows.append({"id": item_id, "category": name, "name": row,
                                 "quantity": inventory.quantity(item_id)})
        for row in rows:
            if needle and needle not in row["name"].lower() and needle not in f"0x{row['id']:04x}":
                continue
            tree.insert("", "end", iid=str(row["id"]),
                        values=(f"0x{row['id']:04X}", row["name"], row["category"], row["quantity"]))

    def on_item_edit(self, event) -> None:
        item = self.items_tree.identify_row(event.y)
        if not item or self.items_tree.identify_column(event.x) != "#4":
            return
        item_id = int(item)
        current = self.items_tree.set(item, "quantity")

        def commit(value: int) -> None:
            self.doc.inventory().set_quantity(item_id, value)
            self.items_tree.set(item, "quantity", value)

        self._edit_value(data.item_name(item_id), current, commit)

    # ---------------------------------------------------- personas handlers
    def refresh_personas(self) -> None:
        if self.doc is None:
            return
        stock = self.doc.persona_stock()
        tree = self.persona_tree
        tree.delete(*tree.get_children())
        for slot in stock.all_slots():
            label = slot.name if slot.id else "- empty -"
            tree.insert("", "end", iid=str(slot.slot),
                        values=(slot.slot + 1, label, slot.level, *slot.stats))
        if tree.get_children() and not tree.selection():
            tree.selection_set(tree.get_children()[0])
        self.refresh_skills()
        formation = self.doc.formation()
        self.formation_var.set(", ".join(str(i) for i in formation.ids()))

    def refresh_skills(self) -> None:
        if self.doc is None:
            return
        selection = self.persona_tree.selection()
        tree = self.skill_tree
        tree.delete(*tree.get_children())
        if not selection:
            return
        slot_index = int(selection[0])
        slot = self.doc.persona_stock().read(slot_index)
        if not slot.id:
            return
        for i, skill_id in enumerate(slot.skills):
            tree.insert("", "end", iid=str(i),
                        values=(i + 1, f"{data.skill_name(skill_id)}  (id {skill_id})"))

    def on_persona_edit(self, event) -> None:
        item = self.persona_tree.identify_row(event.y)
        column = self.persona_tree.identify_column(event.x)
        if not item:
            return
        slot_index = int(item)
        slot = self.doc.persona_stock().read(slot_index)
        if not slot.id:
            messagebox.showinfo("Empty slot", "This Persona slot is empty.")
            return
        field = {"#3": "level", "#4": "strength", "#5": "magic",
                 "#6": "endurance", "#7": "agility", "#8": "luck"}.get(column)
        if field is None:
            return
        current = slot.level if field == "level" else slot.stats[data.PERSONA_STAT_NAMES.index(
            {"strength": "Strength", "magic": "Magic", "endurance": "Endurance",
             "agility": "Agility", "luck": "Luck"}[field])]

        def commit(value: int) -> None:
            stock = self.doc.persona_stock()
            if field == "level":
                stock.set_level(slot_index, value)
            else:
                stock.set_stat(slot_index, data.PERSONA_STAT_NAMES.index(
                    {"strength": "Strength", "magic": "Magic", "endurance": "Endurance",
                     "agility": "Agility", "luck": "Luck"}[field]), value)
            self.refresh_personas()

        self._edit_value(f"{slot.name} - {field}", current, commit)

    def on_skill_edit(self, event) -> None:
        item = self.skill_tree.identify_row(event.y)
        selection = self.persona_tree.selection()
        if not item or not selection:
            return
        slot_index = int(selection[0])
        skill_slot = int(item)
        slot = self.doc.persona_stock().read(slot_index)
        current = slot.skills[skill_slot] if skill_slot < len(slot.skills) else 0

        def commit(value: int) -> None:
            self.doc.persona_stock().set_skill(slot_index, skill_slot, value)
            self.refresh_skills()

        self._edit_value(f"Skill slot {skill_slot + 1} (id, 0 clears)", current, commit)

    # ---------------------------------------------------------- compendium tab
    def _build_compendium_tab(self) -> None:
        wrapper = ttk.Frame(self.compendium_tab, padding=6)
        wrapper.pack(fill="both", expand=True)
        top = ttk.Frame(wrapper)
        top.pack(fill="x", pady=(0, 4))
        self.compendium_search = tk.StringVar()
        ttk.Label(top, text="Search").pack(side="left")
        entry = ttk.Entry(top, textvariable=self.compendium_search, width=24)
        entry.pack(side="left", padx=6)
        entry.bind("<KeyRelease>", lambda _e: self.refresh_compendium())
        self.compendium_owned_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Registered only", variable=self.compendium_owned_only,
                        command=self.refresh_compendium).pack(side="left", padx=8)
        ttk.Label(top, text="Double-click a row to toggle registration.",
                  foreground="#666").pack(side="left", padx=12)

        columns = ("id", "name", "arcana", "level", "state")
        self.compendium_tree = ttk.Treeview(wrapper, columns=columns, show="headings", height=20)
        for col, title, width, anchor in (("id", "ID", 70, "center"), ("name", "Persona", 220, "w"),
                                          ("arcana", "Arcana", 130, "w"), ("level", "Lv", 60, "center"),
                                          ("state", "Compendium", 120, "center")):
            self.compendium_tree.heading(col, text=title)
            self.compendium_tree.column(col, width=width, anchor=anchor)
        bar = ttk.Scrollbar(wrapper, orient="vertical", command=self.compendium_tree.yview)
        self.compendium_tree.configure(yscrollcommand=bar.set)
        self.compendium_tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.compendium_tree.bind("<Double-1>", self.on_compendium_toggle)
        self.compendium_tree.tag_configure("unlocked", foreground="#1a7f37")
        self.compendium_tree.tag_configure("locked", foreground="#999999")

    # --------------------------------------------------------------- raw tab
    def _build_raw_tab(self) -> None:
        wrapper = ttk.Frame(self.raw_tab)
        wrapper.pack(fill="both", expand=True)
        top = ttk.Frame(wrapper)
        top.pack(fill="x", padx=6, pady=4)
        ttk.Label(top, text="Filter index:").pack(side="left")
        self.raw_filter = tk.StringVar()
        ttk.Entry(top, textvariable=self.raw_filter, width=14).pack(side="left", padx=4)
        ttk.Button(top, text="Apply filter", command=self.refresh_raw).pack(side="left")
        ttk.Button(top, text="Show all", command=self.show_all_raw).pack(side="left", padx=4)
        self.raw_tree = ttk.Treeview(wrapper, columns=("index", "value"), show="headings", height=20)
        self.raw_tree.heading("index", text="#")
        self.raw_tree.heading("value", text="Value")
        self.raw_tree.column("index", width=110, anchor="e")
        self.raw_tree.column("value", width=200, anchor="e")
        bar = ttk.Scrollbar(wrapper, orient="vertical", command=self.raw_tree.yview)
        self.raw_tree.configure(yscrollcommand=bar.set)
        self.raw_tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        bar.pack(side="right", fill="y", pady=6)
        self.raw_tree.bind("<Double-1>", self.on_raw_edit)

    # ---------------------------------------------------------------- actions
    def load(self, path: str) -> None:
        try:
            self.doc = SaveDocument(path)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            messagebox.showerror("Cannot open save", str(exc))
            return
        for child in self.fields_frame.winfo_children():
            child.destroy()
        self.rows.clear()
        self.name_rows.clear()
        self.name_slots.clear()

        head = self.doc.header_struct
        group_rows = 0
        for prop in head.inner:
            row_frame = ttk.Frame(self.fields_frame)
            row_frame.pack(fill="x", pady=1)
            ttk.Label(row_frame, text=f"{prop.name}", width=16, anchor="w").pack(side="left")
            ttk.Label(row_frame, text=prop.type, width=16, anchor="w", foreground="#666").pack(side="left")
            row = PropertyRow(row_frame, prop)
            entry = ttk.Entry(row_frame, textvariable=row.var, width=48)
            entry.pack(side="left", fill="x", expand=True)
            self.rows.append(row)
            if prop.name in ("FirstName", "LastName"):
                self.name_rows.setdefault(prop.name, []).append(row)
                self.name_slots[prop.name] = self.name_slots.get(prop.name, 0) + 1
            group_rows += 1

        # show decoded player name (UTF-16 split across Int8 slots)
        if self.name_rows:
            full = ttk.Frame(self.fields_frame)
            full.pack(fill="x", pady=(10, 2))
            ttk.Label(full, text="Full name", width=33, anchor="w").pack(side="left")
            self.full_name_var = tk.StringVar()
            self.full_name_var.set(self.current_full_name())
            ttk.Entry(full, textvariable=self.full_name_var, width=48).pack(side="left", fill="x", expand=True)
            ttk.Button(full, text="Apply name", command=self.on_apply_name).pack(side="left", padx=4)

        self.refresh_gameplay()
        self.refresh_party()
        self.refresh_items()
        self.refresh_personas()
        self.refresh_compendium()
        self.show_all_raw()

        self.status.set(
            f"Loaded {os.path.basename(path)}  -  {group_rows} header fields, "
            f"{len(self.doc.areas)} area words, format version {self.doc.version}"
        )

    def current_full_name(self) -> str:
        parts = []
        for key in ("FirstName", "LastName"):
            rows = self.name_rows.get(key, [])
            parts.append(decode_name([int(r.var.get(), 0) for r in rows]) if rows else "")
        return " ".join(p for p in parts if p)

    def on_apply_name(self) -> None:
        if self.doc is None:
            return
        first, _, last = self.full_name_var.get().partition(" ")
        try:
            for key, text in (("FirstName", first), ("LastName", last or first)):
                rows = self.name_rows.get(key, [])
                if not rows:
                    continue
                encoded = encode_name(text, len(rows))
                for row, value in zip(rows, encoded):
                    row.var.set(str(value))
        except ValueError as exc:
            messagebox.showerror("Name too long", str(exc))

    def refresh_gameplay(self) -> None:
        if self.doc is None:
            return
        view = self.doc.area_view()
        version = self.doc.version
        for field in view.core(version):
            value = field["value"]
            self.core_vars[field["key"]].set("" if value is None else str(value))
        stats, links = view.social(version)
        for stat in stats:
            value = stat["value"]
            self.stat_vars[stat["key"]].set("" if value is None else str(value))
            label = self.stat_vars.get(stat["key"] + "__rank")
            if isinstance(label, ttk.Label):
                label.config(text=stat["rank"] or "")
        for link in links:
            rank = link["rank"]
            self.link_vars[str(link["index"] - fields.shift(version))].set(
                "" if rank is None else str(rank))

    def refresh_party(self) -> None:
        if self.doc is None:
            return
        view = self.doc.area_view()
        self.party_tree.delete(*self.party_tree.get_children())
        for member in view.party(self.doc.version):
            self.party_tree.insert("", "end", iid=member["key"],
                                   values=(member["name"],
                                           *_or_blank(member["level"]),
                                           *_or_blank(member["hp"]),
                                           *_or_blank(member["sp"]),
                                           *_or_blank(member["experience"])))
        diff = view.difficulty(self.doc.version)
        self.diff_var.set(str(diff["id"]) if diff and diff["id"] is not None else "")

    def show_all_raw(self) -> None:
        if self.doc is None:
            return
        self.raw_filter.set("")
        self._fill_raw(None)

    def refresh_raw(self) -> None:
        if self.doc is None:
            return
        text = self.raw_filter.get().strip()
        wanted = None
        if text:
            try:
                wanted = int(text, 0)
            except ValueError:
                messagebox.showerror("Invalid filter", "Enter an integer (decimal or 0x...).")
                return
        self._fill_raw(wanted)

    def _fill_raw(self, wanted: int | None) -> None:
        tree = self.raw_tree
        tree.delete(*tree.get_children())
        for index, prop in sorted(self.doc.word_map().items()):
            if wanted is not None and index != wanted:
                continue
            tree.insert("", "end", iid=str(index), values=(index, prop.value))

    def on_raw_edit(self, event) -> None:
        item = self.raw_tree.identify_row(event.y)
        if not item or self.raw_tree.identify_column(event.x) != "#2":
            return
        index = int(item)
        self._edit_value(f"SaveDataArea[{index}]", self.raw_tree.set(item, "value"),
                         lambda v: (self.doc.set_word(index, v),
                                    self.raw_tree.set(item, "value", v & 0xFFFFFFFF)))

    def on_party_edit(self, event) -> None:
        item = self.party_tree.identify_row(event.y)
        column = self.party_tree.identify_column(event.x)
        if not item or column == "#1":
            return
        field = {"#2": "level", "#3": "hp", "#4": "sp", "#5": "experience"}.get(column)
        if field is None:
            return
        view = self.doc.area_view()
        member = next(m for m in view.party(self.doc.version) if m["key"] == item)
        values = list(self.party_tree.item(item, "values"))
        current = member[field]

        def commit(value: int) -> None:
            base = fields.shift(self.doc.version)
            hp_index = next(m["hp"] for m in fields.PARTY_MEMBERS if m["key"] == item) + base
            index = hp_index + fields.PARTY_FIELDS[field]
            if field == "level":
                self.doc.set_word(index, (value & 0xFFFF))
            else:
                self.doc.set_word(index, value)
            values[{"level": 1, "hp": 2, "sp": 3, "experience": 4}[field]] = value
            self.party_tree.item(item, values=values)
            self.refresh_gameplay()

        self._edit_value(f"{member['name']} - {field}", current, commit)

    def _edit_value(self, title: str, current, commit) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog, text=title).pack(padx=12, pady=(12, 4))
        var = tk.StringVar(value=str(current))
        entry = ttk.Entry(dialog, textvariable=var, width=30)
        entry.pack(padx=12, pady=4)
        entry.focus_set()
        entry.select_range(0, "end")

        def ok() -> None:
            try:
                value = int(var.get(), 0)
            except ValueError:
                messagebox.showerror("Invalid value", "Enter an integer (decimal or 0x...).")
                return
            commit(value)
            dialog.destroy()

        ttk.Button(dialog, text="OK", command=ok).pack(pady=(4, 12))
        dialog.bind("<Return>", lambda _e: ok())

    def on_open(self) -> None:
        path = filedialog.askopenfilename(
            title="Open Persona 3 Reload save",
            filetypes=[("Persona 3 Reload save", "*.sav"), ("All files", "*.*")],
        )
        if path:
            self.load(path)

    def on_apply(self) -> None:
        if self.doc is None:
            return
        for row in self.rows:
            try:
                row.apply()
            except ValueError as exc:
                index = getattr(row.prop, "index", None)
                where = f"{row.prop.name}[{index}]" if index is not None else row.prop.name
                messagebox.showerror("Invalid value", f"{where}: {exc}")
                return
        base = fields.shift(self.doc.version)
        try:
            for key, label, index, low, high in fields.CORE_FIELDS:
                text = self.core_vars[key].get().strip()
                if not text:
                    continue
                try:
                    value = int(text, 0)
                except ValueError:
                    raise ValueError(f"{label}: '{text}' is not a whole number")
                if key == "playTime":
                    value *= fields.PLAY_TIME_TICKS_PER_SECOND
                    if not low <= value // fields.PLAY_TIME_TICKS_PER_SECOND <= high // fields.PLAY_TIME_TICKS_PER_SECOND:
                        raise ValueError(f"{label} must be between {low // 30} and {high // 30} seconds")
                elif not low <= value <= high:
                    raise ValueError(f"{label} must be between {low} and {high}")
                self.doc.set_word(index + base, value)
            for key, label, index, _levels in fields.SOCIAL_STATS:
                text = self.stat_vars[key].get().strip()
                if not text:
                    continue
                try:
                    value = int(text, 0)
                except ValueError:
                    raise ValueError(f"{label}: '{text}' is not a whole number")
                if not 0 <= value <= 255:
                    raise ValueError(f"{label} must be between 0 and 255")
                self.doc.set_word(index + base, value)
            for label, _arcana, index in fields.SOCIAL_LINKS:
                var = self.link_vars[str(index)]
                text = var.get().strip()
                if not text:
                    continue
                try:
                    rank = int(text, 0)
                except ValueError:
                    raise ValueError(f"{label}: '{text}' is not a whole number")
                if not 0 <= rank <= 10:
                    raise ValueError(f"{label} rank must be between 0 and 10")
                word_index = index + base
                prop = self.doc.word_map().get(word_index)
                old = prop.value if prop is not None else 0
                self.doc.set_word(word_index, (old & 0xFFFFFF00) | rank)
            if self.diff_var.get().strip():
                try:
                    wanted = int(self.diff_var.get(), 0)
                except ValueError:
                    raise ValueError(f"Difficulty: '{self.diff_var.get()}' is not a whole number")
                entry = next((d for d in fields.DIFFICULTIES if d[0] == wanted), None)
                if entry is None:
                    raise ValueError("Difficulty must be 0-4")
                word_index = self.doc.area_view().find_difficulty_index(self.doc.version)
                if word_index is None:
                    raise ValueError("Could not locate the difficulty word in this save")
                prop = self.doc.word_map().get(word_index)
                old = prop.value if prop is not None else 0
                self.doc.set_word(word_index, (old & ~fields.DIFFICULTY_FLAG_MASK) | entry[2])
        except ValueError as exc:
            messagebox.showerror("Invalid value", str(exc))
            return
        if self.formation_var.get().strip():
            try:
                ids = [int(part, 0) for part in self.formation_var.get().replace(";", ",").split(",") if part.strip()]
            except ValueError:
                messagebox.showerror("Invalid formation", "Use comma-separated member IDs, e.g. 1, 2, 5, 4")
                return
            self.doc.formation().set_ids(ids)
        self.refresh_gameplay()
        self.refresh_party()
        self.refresh_personas()
        self.status.set("Changes applied in memory. Use Save to write them to disk.")

    def on_save(self) -> None:
        if self.doc is None:
            return
        self.on_apply()
        try:
            self.doc.save_to(self.doc.path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Save failed", str(exc))
            return
        self.status.set(f"Saved to {self.doc.path} (backup created in ./backup)")

    def on_save_as(self) -> None:
        if self.doc is None:
            return
        self.on_apply()
        path = filedialog.asksaveasfilename(defaultextension=".sav", filetypes=[("Persona 3 Reload save", "*.sav")])
        if not path:
            return
        try:
            self.doc.save_to(path, backup=False)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Save failed", str(exc))
            return
        self.status.set(f"Saved to {path}")

    def on_export_gvas(self) -> None:
        if self.doc is None:
            return
        path = filedialog.asksaveasfilename(defaultextension=".gvas", filetypes=[("GVAS", "*.gvas")])
        if not path:
            return
        with open(path, "wb") as fh:
            fh.write(self.doc.save.dumps())
        self.status.set(f"Exported decoded GVAS to {path}")

    def on_dump_json(self) -> None:
        if self.doc is None:
            return
        import json
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return

        def to_json(prop: gvas.Property):
            if isinstance(prop, gvas.StructProperty):
                inner = prop.inner
                return {"name": prop.name, "type": prop.type, "struct_type": prop.struct_type,
                        "value": to_json(inner) if isinstance(inner, list) else inner.hex()}
            if isinstance(prop, gvas.ArrayProperty):
                return {"name": prop.name, "type": prop.type, "item_type": prop.item_type, "value": prop.items}
            return {"name": prop.name, "type": prop.type, "value": prop.value}

        payload = {
            "engine": self.doc.save.header.engine_version,
            "engine_branch": self.doc.save.header.engine_branch,
            "save_class": self.doc.save.header.save_game_class_name,
            "root": [to_json(p) for p in self.doc.save.root],
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        self.status.set(f"Dumped JSON to {path}")


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    EditorApp(path).mainloop()


if __name__ == "__main__":
    main()

