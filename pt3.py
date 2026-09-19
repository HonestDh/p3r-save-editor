p = "test_apply2.py"
s = open(p, encoding="utf-8").read()
tail = '''
# --- now change values and persist ---
import shutil, os
shutil.copy2("SaveData007.sav", "_apply.sav")
app2 = mod.EditorApp.__new__(mod.EditorApp)
app2.doc = mod.SaveDocument("_apply.sav")
app2.rows = []
app2.core_vars = {}; app2.stat_vars = {}; app2.link_vars = {}
app2.diff_var = FakeVar(); app2.formation_var = FakeVar("1, 2, 5, 4"); app2.status = FakeVar()
for entry in mod.fields.CORE_FIELDS: app2.core_vars[entry[0]] = FakeVar()
for key, label, _i, _l in mod.fields.SOCIAL_STATS:
    app2.stat_vars[key] = FakeVar(); app2.stat_vars[key + "__rank"] = None
for label, arcana, index in mod.fields.SOCIAL_LINKS: app2.link_vars[str(index)] = FakeVar()
for p_ in app2.doc.header_struct.inner: app2.rows.append(mod.PropertyRow(None, p_))
app2.refresh_gameplay()
app2.refresh_party = lambda: None
app2.refresh_personas = lambda: None
app2.core_vars["money"].set("500000")
app2.link_vars["5304"].set("5")          # previously missing Fuuka link
app2.diff_var.set("4")
app2.on_apply()
app2.doc.save_to("_apply.sav")

doc = mod.SaveDocument("_apply.sav")
view = doc.area_view(); base = mod.fields.shift(doc.version)
print("saved money:", view.get(7257 + base))
print("saved Fuuka rank:", view.get(5304 + base))
print("saved difficulty:", view.difficulty(doc.version))
print("size:", os.path.getsize("_apply.sav"))
os.remove("_apply.sav")
'''
open(p, "w", encoding="utf-8").write(s + tail)
print("extended")
