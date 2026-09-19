src = open("p3r_editor.pyw", encoding="utf-8").read()

old = '''            for label, _arcana, index in fields.SOCIAL_LINKS:
                var = self.link_vars[str(index)]
                text = var.get().strip()
                if not text:
                    continue
                rank = int(text, 0)
                if not 0 <= rank <= 10:
                    raise ValueError(f"{label} rank must be between 0 and 10")
                old = self.doc.word_map()[index + base].value
                self.doc.set_word(index + base, (old & 0xFFFFFF00) | rank)
            if self.diff_var.get().strip():
                wanted = int(self.diff_var.get(), 0)
                entry = next((d for d in fields.DIFFICULTIES if d[0] == wanted), None)
                if entry is None:
                    raise ValueError("Difficulty must be 0-4")
                word_index = view.find_difficulty_index(self.doc.version)
                if word_index is None:
                    raise ValueError("Could not locate the difficulty word in this save")
                old = self.doc.word_map()[word_index].value
                self.doc.set_word(word_index, (old & ~fields.DIFFICULTY_FLAG_MASK) | entry[2])
'''

new = '''            for label, _arcana, index in fields.SOCIAL_LINKS:
                var = self.link_vars[str(index)]
                text = var.get().strip()
                if not text:
                    continue
                rank = int(text, 0)
                if not 0 <= rank <= 10:
                    raise ValueError(f"{label} rank must be between 0 and 10")
                word_index = index + base
                prop = self.doc.word_map().get(word_index)
                old = prop.value if prop is not None else 0
                self.doc.set_word(word_index, (old & 0xFFFFFF00) | rank)
            if self.diff_var.get().strip():
                wanted = int(self.diff_var.get(), 0)
                entry = next((d for d in fields.DIFFICULTIES if d[0] == wanted), None)
                if entry is None:
                    raise ValueError("Difficulty must be 0-4")
                word_index = self.doc.area_view().find_difficulty_index(self.doc.version)
                if word_index is None:
                    raise ValueError("Could not locate the difficulty word in this save")
                prop = self.doc.word_map().get(word_index)
                old = prop.value if prop is not None else 0
                self.doc.set_word(word_index, (old & ~fields.DIFFICULTY_FLAG_MASK) | entry[2])
'''
assert old in src, "blocks not found"
src = src.replace(old, new)

# Make the error message point at the offending field for the core/stat/link loops.
old_core = '''            for key, label, index, low, high in fields.CORE_FIELDS:
                text = self.core_vars[key].get().strip()
                if not text:
                    continue
                value = int(text, 0)
                if key == "playTime":
                    value *= fields.PLAY_TIME_TICKS_PER_SECOND
                if not low <= value <= high:
                    raise ValueError(f"{label} must be between {low} and {high}")
                self.doc.set_word(index + base, value)'''
new_core = '''            for key, label, index, low, high in fields.CORE_FIELDS:
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
                self.doc.set_word(index + base, value)'''
assert old_core in src
src = src.replace(old_core, new_core)

old_stat = '''            for key, label, index, _levels in fields.SOCIAL_STATS:
                text = self.stat_vars[key].get().strip()
                if not text:
                    continue
                value = int(text, 0)
                if not 0 <= value <= 255:
                    raise ValueError(f"{label} must be between 0 and 255")
                self.doc.set_word(index + base, value)'''
new_stat = '''            for key, label, index, _levels in fields.SOCIAL_STATS:
                text = self.stat_vars[key].get().strip()
                if not text:
                    continue
                try:
                    value = int(text, 0)
                except ValueError:
                    raise ValueError(f"{label}: '{text}' is not a whole number")
                if not 0 <= value <= 255:
                    raise ValueError(f"{label} must be between 0 and 255")
                self.doc.set_word(index + base, value)'''
assert old_stat in src
src = src.replace(old_stat, new_stat)

old_link = '''                rank = int(text, 0)
                if not 0 <= rank <= 10:
                    raise ValueError(f"{label} rank must be between 0 and 10")'''
new_link = '''                try:
                    rank = int(text, 0)
                except ValueError:
                    raise ValueError(f"{label}: '{text}' is not a whole number")
                if not 0 <= rank <= 10:
                    raise ValueError(f"{label} rank must be between 0 and 10")'''
assert old_link in src
src = src.replace(old_link, new_link)

# difficulty parse guard
old_diff = '''            if self.diff_var.get().strip():
                wanted = int(self.diff_var.get(), 0)
                entry = next((d for d in fields.DIFFICULTIES if d[0] == wanted), None)'''
new_diff = '''            if self.diff_var.get().strip():
                try:
                    wanted = int(self.diff_var.get(), 0)
                except ValueError:
                    raise ValueError(f"Difficulty: '{self.diff_var.get()}' is not a whole number")
                entry = next((d for d in fields.DIFFICULTIES if d[0] == wanted), None)'''
assert old_diff in src
src = src.replace(old_diff, new_diff)

# also give the header-row errors the field name
old_row = '''        for row in self.rows:
            try:
                row.apply()
            except ValueError as exc:
                messagebox.showerror("Invalid value", f"{row.prop.name}: {exc}")
                return'''
new_row = '''        for row in self.rows:
            try:
                row.apply()
            except ValueError as exc:
                index = getattr(row.prop, "index", None)
                where = f"{row.prop.name}[{index}]" if index is not None else row.prop.name
                messagebox.showerror("Invalid value", f"{where}: {exc}")
                return'''
assert old_row in src
src = src.replace(old_row, new_row)

open("p3r_editor.pyw", "w", encoding="utf-8").write(src)
print("on_apply fixed")
