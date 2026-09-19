import sys, types, os, shutil
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
fake_msg.showinfo = lambda *a, **k: print("INFO DIALOG:", a)
fake_msg.askyesno = lambda *a, **k: True
fake_fd = types.ModuleType("tkinter.filedialog")
fake_tk.messagebox = fake_msg
fake_tk.filedialog = fake_fd
sys.modules["tkinter"] = fake_tk
sys.modules["tkinter.ttk"] = fake_ttk
sys.modules["tkinter.messagebox"] = fake_msg
sys.modules["tkinter.filedialog"] = fake_fd

import importlib.util
src = open('p3r_editor.pyw', encoding='utf-8').read()
code = compile(src, 'p3r_editor.pyw', 'exec')
mod = types.ModuleType('p3r_editor')
mod.__file__ = 'p3r_editor.pyw'
exec(code, mod.__dict__)

# build an app instance without running __init__
app = mod.EditorApp.__new__(mod.EditorApp)
app.doc = mod.SaveDocument('SaveData007.sav')
app.rows = []
app.core_vars = {}; app.stat_vars = {}; app.link_vars = {}
app.diff_var = FakeVar("3")
app.formation_var = FakeVar("1, 2, 5, 4")
app.status = FakeVar()

view = app.doc.area_view(); ver = app.doc.version
base = mod.fields.shift(ver)
for p in app.doc.header_struct.inner:
    app.rows.append(mod.PropertyRow(None, p))
for f in view.core(ver): app.core_vars[f["key"]] = FakeVar(str(f["value"]))
stats, links = view.social(ver)
for s in stats: app.stat_vars[s["key"]] = FakeVar(str(s["value"]))
for l in links:
    app.link_vars[str(l["index"] - base)] = FakeVar(str(l["rank"]))

app.refresh_gameplay = lambda: None
app.refresh_party = lambda: None
app.refresh_personas = lambda: None
app.refresh_items = lambda: None
app.refresh_compendium = lambda: None

app.on_apply()
print("on_apply finished")

# verify a change actually lands
app.core_vars["money"].set("123456")
app.on_apply()
print("money now:", app.doc.area_view().get(7257 + base))

# out-of-range should show a clear error, not crash
app.stat_vars["charm"].set("999")
app.on_apply()
print("done")
