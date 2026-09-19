src = open("p3r_editor.pyw", encoding="utf-8").read()

old = '''    def apply(self) -> None:
        prop = self.prop
        text = self.var.get()
        if isinstance(prop, gvas.EnumProperty):
            prop.value = text
        elif isinstance(prop, (gvas.StrProperty, gvas.NameProperty)):
            prop.value = text
        elif isinstance(prop, gvas.FloatProperty):
            prop.value = float(text)
        elif isinstance(prop, gvas.BoolProperty):
            prop.value = text.strip().lower() in ("1", "true", "yes", "on")
        else:
            prop.value = int(text, 0)
'''

new = '''    def apply(self) -> None:
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
'''
assert old in src
src = src.replace(old, new)

# add the tolerant integer parser helper right before PropertyRow
anchor = "class PropertyRow:"
helper = '''def _parse_int(text: str) -> int:
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


'''
src = src.replace(anchor, helper + anchor, 1)

open("p3r_editor.pyw", "w", encoding="utf-8").write(src)
print("PropertyRow.apply hardened")
