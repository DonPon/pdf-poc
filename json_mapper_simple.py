#!/usr/bin/env python3
import ast, json, os, tkinter as tk
from tkinter import filedialog, messagebox

# --- Parser ---
def get_models_metadata(models_file):
    if not os.path.exists(models_file): return {}
    with open(models_file, 'r') as f: tree = ast.parse(f.read())
    models = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and any(b.id in ('Model', 'ClientRelatedModel') for b in node.bases if isinstance(b, ast.Name)):
            fields = []
            for item in node.body:
                if isinstance(item, ast.Assign) and isinstance(item.value, ast.Call):
                    field_name = item.targets[0].id
                    if not field_name.startswith('_'):
                        verbose = field_name.replace('_', ' ').title()
                        for kw in item.value.keywords:
                            if kw.arg == 'verbose_name' and isinstance(kw.value, ast.Constant):
                                verbose = kw.value.value
                        fields.append({'name': field_name, 'verbose': verbose})
            if fields: models[node.name] = fields
    return models

# --- App ---
class MapperApp:
    def __init__(self, root, models):
        self.root = root
        self.models = models
        self.data = None
        self.mappings = []
        
        root.title("JSON Mapper")
        root.geometry("1000x600")
        
        # Configure Grid Weights for Expansion
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)
        
        # Layout: Grid
        left = tk.Frame(root, bg="#f0f0f0", bd=2, relief=tk.GROOVE)
        left.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        right = tk.Frame(root, bg="#f0f0f0", bd=2, relief=tk.GROOVE)
        right.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        
        # Configure Left Grid
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)
        
        tk.Button(left, text="1. Load JSON", command=self.load).grid(row=0, column=0, sticky="ew")
        self.search = tk.Entry(left)
        self.search.grid(row=1, column=0, sticky="ew")
        self.search.bind('<Return>', self.do_search)
        self.results = tk.Listbox(left)
        self.results.grid(row=2, column=0, sticky="nsew")
        
        # Configure Right Grid
        right.columnconfigure(0, weight=1)
        right.rowconfigure(6, weight=1)
        
        self.path_lbl = tk.Label(right, text="Select path...", bg="#f0f0f0")
        self.path_lbl.grid(row=0, column=0, sticky="ew")
        
        tk.Label(right, text="Models:", bg="#f0f0f0").grid(row=1, column=0, sticky="w")
        self.m_list = tk.Listbox(right, height=5)
        self.m_list.grid(row=2, column=0, sticky="ew")
        self.m_list.bind('<<ListboxSelect>>', self.show_fields)
        
        tk.Label(right, text="Fields:", bg="#f0f0f0").grid(row=3, column=0, sticky="w")
        self.f_list = tk.Listbox(right, height=5)
        self.f_list.grid(row=4, column=0, sticky="ew")
        
        tk.Button(right, text="2. Add Mapping", command=self.add).grid(row=5, column=0, sticky="ew")
        self.map_text = tk.Text(right, height=10)
        self.map_text.grid(row=6, column=0, sticky="nsew")
        tk.Button(right, text="3. Save Mapping", command=self.save).grid(row=7, column=0, sticky="ew")

    def load(self):
        fp = filedialog.askopenfilename()
        if fp:
            self.data = json.load(open(fp))
            self.results.delete(0, tk.END)
            self.m_list.delete(0, tk.END)
            for m in self.models: self.m_list.insert(tk.END, m)

    def do_search(self, e):
        self.results.delete(0, tk.END)
        self.search_recursive(self.data, self.search.get(), "")

    def search_recursive(self, d, val, path):
        if isinstance(d, dict):
            for k, v in d.items():
                p = f"{path}.{k}" if path else k
                if isinstance(v, (dict, list)): self.search_recursive(v, val, p)
                elif val.lower() in str(v).lower(): self.results.insert(tk.END, f"{p} = {v}")
        elif isinstance(d, list):
            for i, v in enumerate(d):
                p = f"{path}[{i}]"
                if isinstance(v, (dict, list)): self.search_recursive(v, val, p)
                elif val.lower() in str(v).lower(): self.results.insert(tk.END, f"{p} = {v}")

    def show_fields(self, e):
        sel = self.m_list.curselection()
        if not sel: return
        m = self.m_list.get(sel[0])
        self.f_list.delete(0, tk.END)
        for f in self.models[m]: self.f_list.insert(tk.END, f['name'])

    def add(self):
        res_sel = self.results.curselection()
        m_sel = self.m_list.curselection()
        f_sel = self.f_list.curselection()
        if not (res_sel and m_sel and f_sel):
            messagebox.showwarning("Incomplete", "Select path, model, and field.")
            return
            
        p = self.results.get(res_sel[0]).split(" = ")[0]
        m = self.m_list.get(m_sel[0])
        f = self.f_list.get(f_sel[0])
        self.mappings.append(f"{p} -> {m}.{f}")
        self.map_text.insert(tk.END, self.mappings[-1] + "\n")

    def save(self):
        with open("mapping.json", "w") as f: json.dump(self.mappings, f)
        messagebox.showinfo("Done", "Saved to mapping.json")

if __name__ == "__main__":
    models = get_models_metadata("models.py")
    root = tk.Tk()
    MapperApp(root, models)
    root.mainloop()
