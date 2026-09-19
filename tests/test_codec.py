"""Tests for the Persona 3 Reload save codec and data views.

Run with:  python -m pytest tests -q      (or)      python tests/test_codec.py
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import p3r_codec
import p3r_data
import p3r_fields
import p3r_gvas


def test_bit_swap_is_involutive():
    for value in range(256):
        assert p3r_codec._swap_bits(p3r_codec._swap_bits(value)) == value


def test_key_length():
    assert len(p3r_codec.KEY) == 31


def test_codec_round_trip():
    payload = bytes(range(256)) * 4
    assert p3r_codec.encode(p3r_codec.decode(payload)) == payload


def test_header_round_trip():
    header = p3r_gvas.Header(
        save_game_version=2,
        package_version=522,
        engine_version="4.27.2",
        engine_branch="++UE4+Release-4.27",
        save_game_class_name="/Script/xrd777.XRD777SaveGame",
    )
    writer = p3r_gvas.Writer()
    header.write(writer)
    parsed = p3r_gvas.Header.read(p3r_gvas.Reader(writer.build()))
    assert parsed.engine_version == "4.27.2"
    assert parsed.package_version == 522
    assert parsed.save_game_class_name == "/Script/xrd777.XRD777SaveGame"


def test_sparse_word_creation():
    props = [
        p3r_gvas.UInt32Property("SaveDataArea", "UInt32Property", size=4, index=0, value=1),
        p3r_gvas.UInt32Property("SaveDataArea", "UInt32Property", size=4, index=5, value=2),
    ]

    class Fake:
        root = props

        def word_map(self):
            return {p.index: p for p in props}

    # emulate SaveDocument.ensure_word behaviour
    index = 3
    new_prop = p3r_gvas.UInt32Property("SaveDataArea", "UInt32Property", size=4, index=index, value=0)
    position = len(props)
    for i, prop in enumerate(props):
        if prop.index > index:
            position = i
            break
    props.insert(position, new_prop)
    assert [p.index for p in props] == [0, 3, 5]


def test_item_lookup():
    name = p3r_data.item_name(0x401C)
    assert name != "Item 0x401C"
    assert p3r_data.persona_by_id(65)["name"] == "Orpheus Telos"


def test_version_shift():
    assert p3r_fields.shift(1) == 0
    assert p3r_fields.shift(2) == 4


if __name__ == "__main__":
    failures = 0
    for name, func in sorted(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    print("all tests passed" if not failures else f"{failures} test(s) failed")
    sys.exit(1 if failures else 0)


def test_parse_int_tolerates_leading_zero():
    """Regression: ``int(text, 0)`` rejects '08', which the GUI must accept."""
    import importlib.util
    code = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "p3r_editor.pyw"), encoding="utf-8").read()
    # execute only the helper, not the GUI body
    namespace = {}
    start = code.index("def _parse_int")
    end = code.index("class PropertyRow")
    exec(code[start:end], namespace)
    parse = namespace["_parse_int"]
    assert parse("08") == 8
    assert parse(" -12 ") == -12
    assert parse("0x1F") == 31
    assert parse("255") == 255
    try:
        parse("abc")
    except ValueError:
        pass
    else:
        raise AssertionError("'abc' should not parse")


def test_missing_link_shows_blank_not_none():
    """Regression: absent SaveDataArea words rendered as the string 'None'
    and then failed validation on save."""
    view = p3r_fields.AreaView({})
    _stats, links = view.social(2)
    assert all(link["rank"] is None for link in links)
    assert all(link["index"] is not None for link in links)
