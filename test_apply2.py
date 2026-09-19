import sys, types
sys.path.insert(0,'.')

class FakeVar:
    def __init__(self, value="", master=None, **kw): self._v = value
    def get(self): return self._v
    def set(self, v): self._v = v

class FakeWidget:
    def __init__(self, *a, **k): pass
    def __getattr__(self, n): return lambda *a, **k: None

fake_tk = types.ModuleType("tkinter")
for name in ("StringVar","BooleanVar","IntVar","DoubleVar"):
    setattr(fake_tk, name, FakeVar)
for name in ("Tk","Toplevel","Frame","Label","Entry","Button","Canvas","Menu","Text","Listbox","Checkbutton","Spinbox"):
    setattr(fake_tk, name, FakeWidget)
fake_ttk = types.ModuleType("tkinter.ttk")
for name in ("Frame","Label","Entry","Button","Notebook","Treeview","Combobox","Scrollbar","LabelFrame","PanedWindow","Checkbutton","Style"):
    setattr(fake_ttk, name, FakeWidget)
class FakeLabel(FakeWidget):
    def config(self, **k): pass
fake_ttk.Label = FakeLabel
fake_tk.ttk = fake_ttk
fake_msg = types.ModuleType("tkinter.messagebox")
fake_msg.showerror = lambda *a, **k: print("ERROR DIALOG:", a)
fake_tk.messagebox = fake_msg
sys.modules["tkinter"] = fake_tk
sys.modules["tkinter.ttk"] = fake_ttk
fake_fd = types.ModuleType("tkinter.filedialog")
fake_fd.askopenfilename = lambda *a, **k: ""
fake_fd.asksaveasfilename = lambda *a, **k: ""
fake_tk.filedialog = fake_fd
sys.modules["tkinter.filedialog"] = fake_fd
sys.modules["tkinter.messagebox"] = fake_msg

mod = types.ModuleType('p3r_editor'); mod.__file__='p3r_editor.pyw'
exec(compile(open('p3r_editor.pyw',encoding='utf-8').read(),'p3r_editor.pyw','exec'), mod.__dict__)

app = mod.EditorApp.__new__(mod.EditorApp)
app.doc = mod.SaveDocument('SaveData007.sav')
app.rows = []
app.core_vars = {}; app.stat_vars = {}; app.link_vars = {}
app.diff_var = FakeVar(); app.formation_var = FakeVar("1, 2, 5, 4"); app.status = FakeVar()
# create the var slots exactly like _build_gameplay_tab does
for entry in mod.fields.CORE_FIELDS: app.core_vars[entry[0]] = FakeVar()
for key, label, _i, _l in mod.fields.SOCIAL_STATS:
    app.stat_vars[key] = FakeVar()
    app.stat_vars[key + "__rank"] = None
for label, arcana, index in mod.fields.SOCIAL_LINKS: app.link_vars[str(index)] = FakeVar()
for p in app.doc.header_struct.inner: app.rows.append(mod.PropertyRow(None, p))
# REAL refresh path
app.refresh_gameplay()
app.refresh_party = lambda: None
app.refresh_personas = lambda: None
print("Fuuka var value:", repr(app.link_vars["5304"].get()))
print("SEES var value:", repr(app.link_vars["5300"].get()))
print("Aigis var value:", repr(app.link_vars["5342"].get()))
app.on_apply()
print("on_apply finished cleanly")

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
