p = "test_apply2.py"
s = open(p, encoding="utf-8").read()
s = s.replace("for key, label, _i, _l in mod.fields.CORE_FIELDS: app.core_vars[key] = FakeVar()",
              "for entry in mod.fields.CORE_FIELDS: app.core_vars[entry[0]] = FakeVar()")
open(p, "w", encoding="utf-8").write(s)
print("patched")
