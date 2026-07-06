#!/usr/bin/env python3
import ast
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, Dict, List


def parse_models(filepath: str) -> Dict[str, Dict]:
    with open(filepath, 'r') as f:
        content = f.read()
    tree = ast.parse(content)
    models = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        is_model = False
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id in ('Model', 'ClientRelatedModel'):
                is_model = True
                break
            if isinstance(base, ast.Attribute) and base.attr == 'Model':
                is_model = True
                break
        if not is_model:
            continue
        class_name = node.name
        fields = []
        for item in node.body:
            if not isinstance(item, ast.Assign):
                continue
            for target in item.targets:
                if not isinstance(target, ast.Name):
                    continue
                field_name = target.id
                if field_name.startswith('_'):
                    continue
                if isinstance(item.value, (ast.List, ast.Tuple)):
                    continue
                if not isinstance(item.value, ast.Call):
                    continue
                verbose_name = field_name.replace('_', ' ').title()
                for kw in item.value.keywords:
                    if kw.arg == 'verbose_name' and isinstance(kw.value, ast.Constant):
                        verbose_name = kw.value.value
                fields.append({'name': field_name, 'verbose_name': verbose_name})
        if fields:
            models[class_name] = {'verbose_name': class_name, 'fields': fields}
    return models


def find_json_paths(data: Any, search_value: str, current_path: str = "") -> List[str]:
    results = []
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{current_path}.{key}" if current_path else key
            if isinstance(value, (dict, list)):
                results.extend(find_json_paths(value, search_value, path))
            else:
                str_value = str(value) if value is not None else ""
                if search_value.lower() in str_value.lower():
                    results.append(f"{path} = {value}")
    elif isinstance(data, list):
        for index, item in enumerate(data):
            path = f"{current_path}[{index}]"
            if isinstance(item, (dict, list)):
                results.extend(find_json_paths(item, search_value, path))
            else:
                str_value = str(item) if item is not None else ""
                if search_value.lower() in str_value.lower():
                    results.append(f"{path} = {item}")
    return results


class JsonMapperApp:
    def __init__(self, root: tk.Tk, models: Dict):
        self.root = root
        self.models = models
        self.json_data = None
        self.json_filepath = None
        self.mappings: List[Dict] = []

        root.title("JSON to Model Mapper")
        root.geometry("1200x700")
        root.minsize(800, 400)

        menubar = tk.Menu(root)
        root.config(menu=menubar)
        fm = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=fm)
        fm.add_command(label="Open JSON...", command=self.load_json)
        fm.add_separator()
        fm.add_command(label="Export Mapping...", command=self.export_mapping)
        fm.add_separator()
        fm.add_command(label="Exit", command=root.quit)

        # === TOP toolbar ===
        top = tk.Frame(root, bg="#e0e0e0", bd=1, relief=tk.RAISED)
        top.pack(fill=tk.X)
        tk.Button(top, text="Open JSON File", command=self.load_json).pack(side=tk.LEFT, padx=4, pady=3)
        self.file_label = tk.Label(top, text="No file loaded", bg="#e0e0e0")
        self.file_label.pack(side=tk.LEFT, padx=8)

        # === MAIN ===
        main = tk.PanedWindow(root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=6)
        main.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # ---- LEFT panel ----
        left = tk.Frame(main, bg="white", bd=1, relief=tk.SUNKEN)
        main.add(left, width=650)

        tk.Label(left, text="Search JSON value:", bg="white", font=("", 10, "bold")).pack(anchor=tk.W, padx=4, pady=(4, 0))
        search_row = tk.Frame(left, bg="white")
        search_row.pack(fill=tk.X, padx=4, pady=2)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.on_search)
        tk.Entry(search_row, textvariable=self.search_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.count_label = tk.Label(search_row, text="", bg="white")
        self.count_label.pack(side=tk.RIGHT, padx=4)

        list_row = tk.Frame(left, bg="white")
        list_row.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.results_box = tk.Listbox(list_row, font=("Courier", 9), exportselection=False)
        self.results_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.results_box.bind('<<ListboxSelect>>', self.on_select)
        sb = tk.Scrollbar(list_row, orient=tk.VERTICAL, command=self.results_box.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.results_box.config(yscrollcommand=sb.set)

        # ---- RIGHT panel ----
        right = tk.Frame(main, bg="#f5f5f5", bd=1, relief=tk.SUNKEN)
        main.add(right, width=400)

        row = 0

        tk.Label(right, text="Selected JSON Path:", bg="#f5f5f5", font=("", 10, "bold")).grid(row=row, column=0, sticky=tk.W, padx=4, pady=(4, 0))
        row += 1
        self.path_var = tk.StringVar()
        tk.Entry(right, textvariable=self.path_var, state='readonly', bg="white").grid(row=row, column=0, sticky=tk.EW, padx=4, pady=2)
        row += 1

        tk.Label(right, text="Model (Table):", bg="#f5f5f5", font=("", 10, "bold")).grid(row=row, column=0, sticky=tk.W, padx=4, pady=(8, 0))
        row += 1
        self.model_var = tk.StringVar()
        self.model_dd = tk.Listbox(right, height=8, exportselection=False)
        self.model_dd.grid(row=row, column=0, sticky=tk.EW, padx=4, pady=2)
        for m in models.keys():
            self.model_dd.insert(tk.END, m)
        self.model_dd.bind('<<ListboxSelect>>', self.on_model_select)
        model_sb = tk.Scrollbar(right, orient=tk.VERTICAL, command=self.model_dd.yview)
        model_sb.grid(row=row, column=1, sticky=tk.NS)
        self.model_dd.config(yscrollcommand=model_sb.set)
        row += 1

        tk.Label(right, text="Field:", bg="#f5f5f5", font=("", 10, "bold")).grid(row=row, column=0, sticky=tk.W, padx=4, pady=(8, 0))
        row += 1
        self.field_var = tk.StringVar()
        self.field_dd = tk.Listbox(right, height=8, exportselection=False)
        self.field_dd.grid(row=row, column=0, sticky=tk.EW, padx=4, pady=2)
        field_sb = tk.Scrollbar(right, orient=tk.VERTICAL, command=self.field_dd.yview)
        field_sb.grid(row=row, column=1, sticky=tk.NS)
        self.field_dd.config(yscrollcommand=field_sb.set)
        row += 1

        btn_row = tk.Frame(right, bg="#f5f5f5")
        btn_row.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=6)
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)
        tk.Button(btn_row, text="Add Mapping", command=self.add_mapping).grid(row=0, column=0, padx=2)
        tk.Button(btn_row, text="Remove", command=self.remove_mapping).grid(row=0, column=1, padx=2)
        row += 1

        tk.Label(right, text="Current Mappings:", bg="#f5f5f5", font=("", 10, "bold")).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=4, pady=(4, 0))
        row += 1

        map_row = tk.Frame(right, bg="#f5f5f5")
        map_row.grid(row=row, column=0, columnspan=2, sticky=tk.NSEW, padx=4, pady=2)
        right.grid_rowconfigure(row, weight=1)
        right.grid_columnconfigure(0, weight=1)
        self.mappings_text = tk.Text(map_row, font=("Courier", 9), width=40, bg="white")
        self.mappings_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        map_sb = tk.Scrollbar(map_row, orient=tk.VERTICAL, command=self.mappings_text.yview)
        map_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.mappings_text.config(yscrollcommand=map_sb.set)

        # === BOTTOM toolbar ===
        bottom = tk.Frame(root, bg="#e0e0e0", bd=1, relief=tk.RAISED)
        bottom.pack(fill=tk.X)
        tk.Button(bottom, text="Export Mapping", command=self.export_mapping).pack(side=tk.RIGHT, padx=4, pady=3)
        tk.Button(bottom, text="Clear All", command=self.clear_mappings).pack(side=tk.RIGHT, padx=4, pady=3)

    def load_json(self):
        fp = filedialog.askopenfilename(title="Select JSON File", filetypes=[("JSON files", "*.json")])
        if not fp:
            return
        try:
            with open(fp, 'r') as f:
                self.json_data = json.load(f)
            self.json_filepath = fp
            self.file_label.config(text=os.path.basename(fp))
            self.results_box.delete(0, tk.END)
            self.count_label.config(text="")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load JSON:\n{e}")

    def on_search(self, *args):
        val = self.search_var.get()
        self.results_box.delete(0, tk.END)
        self.count_label.config(text="")
        if not val.strip() or self.json_data is None:
            return
        paths = find_json_paths(self.json_data, val.strip())
        n = len(paths)
        self.count_label.config(text=f"{n} match{'es' if n != 1 else ''}")
        for p in paths[:200]:
            self.results_box.insert(tk.END, p)
        if n > 200:
            self.results_box.insert(tk.END, f"... and {n - 200} more")

    def on_select(self, event):
        sel = self.results_box.curselection()
        if not sel:
            return
        t = self.results_box.get(sel[0])
        if " = " in t:
            t = t.split(" = ")[0]
        self.path_var.set(t)

    def on_model_select(self, event):
        sel = self.model_dd.curselection()
        if not sel:
            return
        model_name = self.model_dd.get(sel[0])
        self.field_dd.delete(0, tk.END)
        for f in self.models[model_name]['fields']:
            self.field_dd.insert(tk.END, f"{f['name']}  ({f['verbose_name']})")

    def add_mapping(self):
        path = self.path_var.get()
        ms = self.model_dd.curselection()
        fs = self.field_dd.curselection()
        if not path:
            messagebox.showwarning("No Path", "Select a JSON path from search results first.")
            return
        if not ms:
            messagebox.showwarning("No Model", "Select a model.")
            return
        if not fs:
            messagebox.showwarning("No Field", "Select a field.")
            return
        model_name = self.model_dd.get(ms[0])
        field_text = self.field_dd.get(fs[0])
        field_name = field_text.split("  (")[0]
        self.mappings.append({'json_path': path, 'model': model_name, 'field': field_name})
        self.redraw_mappings()

    def remove_mapping(self):
        if not self.mappings:
            return
        try:
            pos = self.mappings_text.index(tk.INSERT)
            ln = int(pos.split('.')[0])
            idx = (ln - 1) // 3
            if 0 <= idx < len(self.mappings):
                self.mappings.pop(idx)
                self.redraw_mappings()
        except Exception:
            pass

    def redraw_mappings(self):
        self.mappings_text.delete(1.0, tk.END)
        for m in self.mappings:
            self.mappings_text.insert(tk.END, f"  {m['json_path']}\n")
            self.mappings_text.insert(tk.END, f"    -> {m['model']}.{m['field']}\n")
            self.mappings_text.insert(tk.END, "\n")

    def clear_mappings(self):
        if self.mappings and messagebox.askyesno("Clear All", "Remove all mappings?"):
            self.mappings.clear()
            self.mappings_text.delete(1.0, tk.END)

    def export_mapping(self):
        if not self.mappings:
            messagebox.showwarning("No Mappings", "No mappings to export.")
            return
        fp = filedialog.asksaveasfilename(title="Save Mapping", defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if not fp:
            return
        with open(fp, 'w') as f:
            json.dump({'json_file': self.json_filepath or "", 'mappings': self.mappings}, f, indent=2)
        messagebox.showinfo("Exported", f"Mapping saved to:\n{fp}")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    models_path = os.path.join(script_dir, 'models.py')
    models = parse_models(models_path)
    root = tk.Tk()
    JsonMapperApp(root, models)
    root.mainloop()


if __name__ == "__main__":
    main()
