src = open("p3r_editor.pyw", encoding="utf-8").read()

old = '''        for link in links:
            self.link_vars[str(link["index"] - fields.shift(version))].set(str(link["rank"]))'''
new = '''        for link in links:
            rank = link["rank"]
            self.link_vars[str(link["index"] - fields.shift(version))].set(
                "" if rank is None else str(rank))'''
assert old in src
src = src.replace(old, new)

# also guard social stats and core fields against a None value
old2 = '''        for field in view.core(version):
            self.core_vars[field["key"]].set(str(field["value"]))'''
new2 = '''        for field in view.core(version):
            value = field["value"]
            self.core_vars[field["key"]].set("" if value is None else str(value))'''
assert old2 in src
src = src.replace(old2, new2)

old3 = '''        for stat in stats:
            self.stat_vars[stat["key"]].set(str(stat["value"]))'''
new3 = '''        for stat in stats:
            value = stat["value"]
            self.stat_vars[stat["key"]].set("" if value is None else str(value))'''
assert old3 in src
src = src.replace(old3, new3)

# party rows: show blanks instead of None
old4 = '''            self.party_tree.insert("", "end", iid=member["key"],
                                   values=(member["name"], member["level"], member["hp"],
                                           member["sp"], member["experience"]))'''
new4 = '''            self.party_tree.insert("", "end", iid=member["key"],
                                   values=(member["name"],
                                           *_or_blank(member["level"]),
                                           *_or_blank(member["hp"]),
                                           *_or_blank(member["sp"]),
                                           *_or_blank(member["experience"])))'''
assert old4 in src
src = src.replace(old4, new4)

# helper for None-safe display
anchor = "def _parse_int(text: str) -> int:"
helper = '''def _or_blank(value):
    """Tuples stay tuples: Treeview values must be a flat sequence."""
    return ("",) if value is None else (value,)


'''
src = src.replace(anchor, helper + anchor, 1)

open("p3r_editor.pyw", "w", encoding="utf-8").write(src)
print("None handling fixed")
