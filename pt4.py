src = open("tests/test_codec.py", encoding="utf-8").read()

extra = '''

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
'''

src = src.rstrip("\n") + "\n" + extra
open("tests/test_codec.py", "w", encoding="utf-8").write(src)
print("tests extended")
