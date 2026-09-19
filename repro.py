import importlib.util, sys, traceback
sys.path.insert(0,'.')

class FakeVar:
    def __init__(self, value="", **kw): self._v = value
    def get(self): return self._v
    def set(self, v): self._v = v

spec=importlib.util.spec_from_file_location('p3r_editor','p3r_editor.pyw')
ed=importlib.util.module_from_spec(spec)
# patch tkinter StringVar before exec
class FakeTk:
    StringVar = FakeVar
    def __getattr__(self, name): raise AttributeError(name)
ed_src = open('p3r_editor.pyw',encoding='utf-8').read()
import types
fake_module = types.ModuleType('tkinter')
for n in ['StringVar','Toplevel','Canvas','Menu','Entry','Label','Frame','Button','Checkbutton','Text','Listbox','BooleanVar','IntVar']:
    setattr(fake_module, n, FakeVar)
    setattr(fake_module,'ttk',None)
spec.loader.exec_module(ed)

doc=ed.SaveDocument('SaveData007.sav')
app=ed.EditorApp.__new__(ed.EditorApp)
app.doc=doc; app.rows=[]; app.core_vars={}; app.stat_vars={}; app.link_vars={}
app.diff_var=FakeVar('3'); app.formation_var=FakeVar('1, 2, 5, 4')
view=doc.area_view(); ver=doc.version
for p in doc.header_struct.inner:
    app.rows.append(ed.PropertyRow(app, p))
for f in view.core(ver): app.core_vars[f['key']]=FakeVar(str(f['value']))
stats,links=view.social(ver)
for s in stats: app.stat_vars[s['key']]=FakeVar(str(s['value']))
for l in links: app.link_vars[str(l['index']-ed.fields.shift(ver))]=FakeVar(str(l['rank']))
app.refresh_gameplay=lambda: None; app.refresh_party=lambda: None; app.refresh_personas=lambda: None
app.status=FakeVar()
class MB:
    def showerror(self,*a,**k): print('showerror:', a)
    def showinfo(self,*a,**k): print('showinfo:', a)
ed.messagebox=MB()
app.on_apply()
print('on_apply completed without error')
