p = "test_apply2.py"
s = open(p, encoding="utf-8").read()
marker = 'sys.modules["tkinter.messagebox"] = fake_msg'
extra = '''fake_fd = types.ModuleType("tkinter.filedialog")
fake_fd.askopenfilename = lambda *a, **k: ""
fake_fd.asksaveasfilename = lambda *a, **k: ""
fake_tk.filedialog = fake_fd
sys.modules["tkinter.filedialog"] = fake_fd
'''
s = s.replace(marker, extra + marker, 1)
open(p, "w", encoding="utf-8").write(s)
print("patched test")
