#!/usr/bin/env python3
import sys
import ast
import json
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QSplitter, QListWidget, QLineEdit, 
                             QPushButton, QLabel, QFileDialog, QMessageBox, QTextEdit)
from PyQt5.QtCore import Qt

# --- Parser ---
def get_models_metadata(models_file):
    """
    Parses models.py to extract model class names and their fields.
    """
    if not os.path.exists(models_file): return {}
    
    with open(models_file, 'r') as f: 
        try:
            tree = ast.parse(f.read())
        except SyntaxError:
            return {}
            
    models = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and any(b.id in ('Model', 'ClientRelatedModel') for b in node.bases if isinstance(b, ast.Name)):
            fields = []
            for item in node.body:
                if isinstance(item, ast.Assign) and isinstance(item.value, ast.Call):
                    # We are looking for assignments like: field_name = models.FieldType(...)
                    # item.targets[0] is the field_name
                    if item.targets and isinstance(item.targets[0], ast.Name):
                        field_name = item.targets[0].id
                        if not field_name.startswith('_'):
                            verbose = field_name.replace('_', ' ').title()
                            for kw in item.value.keywords:
                                if kw.arg == 'verbose_name' and isinstance(kw.value, ast.Constant):
                                    verbose = kw.value.value
                            fields.append({'name': field_name, 'verbose': verbose})
            if fields: models[node.name] = fields
    return models

# --- Helper ---
def search_recursive(d, val, path, results):
    if isinstance(d, dict):
        for k, v in d.items():
            p = f"{path}.{k}" if path else k
            if isinstance(v, (dict, list)): search_recursive(v, val, p, results)
            elif val.lower() in str(v).lower(): results.append(f"{p} = {v}")
    elif isinstance(d, list):
        for i, v in enumerate(d):
            p = f"{path}[{i}]"
            if isinstance(v, (dict, list)): search_recursive(v, val, p, results)
            elif val.lower() in str(v).lower(): results.append(f"{p} = {v}")

# --- App ---
class MapperApp(QMainWindow):
    def __init__(self, models):
        super().__init__()
        self.models = models
        self.data = None
        self.mappings = {}
        
        self.setWindowTitle("JSON Mapper (PyQt5)")
        self.resize(1000, 600)
        
        # Central Splitter
        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)
        
        # Left Panel (Search)
        left = QWidget()
        l_layout = QVBoxLayout(left)
        btn_load = QPushButton("1. Load JSON")
        btn_load.clicked.connect(self.load)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search JSON value...")
        self.search.returnPressed.connect(self.do_search)
        self.results = QListWidget()
        l_layout.addWidget(btn_load)
        l_layout.addWidget(self.search)
        l_layout.addWidget(self.results)
        
        # Right Panel (Mapping)
        right = QWidget()
        r_layout = QVBoxLayout(right)
        
        self.m_list = QListWidget()
        self.f_list = QListWidget()
        self.m_list.clicked.connect(self.show_fields)
        
        self.map_text = QTextEdit()
        self.map_text.setReadOnly(True)
        
        btn_add = QPushButton("2. Add Mapping")
        btn_add.clicked.connect(self.add)
        btn_save = QPushButton("3. Save Mapping")
        btn_save.clicked.connect(self.save)
        
        r_layout.addWidget(QLabel("Tables (Models):"))
        r_layout.addWidget(self.m_list)
        r_layout.addWidget(QLabel("Fields: field_name - (GUI name)"))
        r_layout.addWidget(self.f_list)
        r_layout.addWidget(btn_add)
        r_layout.addWidget(QLabel("Current Mappings:"))
        r_layout.addWidget(self.map_text)
        r_layout.addWidget(btn_save)
        
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        
        for m in self.models: self.m_list.addItem(m)

    def load(self):
        fp, _ = QFileDialog.getOpenFileName(self, "Open JSON")
        if fp:
            try:
                self.data = json.load(open(fp))
                self.results.clear()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load JSON: {e}")

    def do_search(self):
        if self.data is None:
            QMessageBox.warning(self, "No Data", "Load a JSON file first.")
            return
        self.results.clear()
        res = []
        search_recursive(self.data, self.search.text(), "", res)
        self.results.addItems(res)

    def show_fields(self):
        if not self.m_list.currentItem(): return
        m = self.m_list.currentItem().text()
        self.f_list.clear()
        for f in self.models[m]: self.f_list.addItem(f"{f['name']} ({f['verbose']})")

    def add(self):
        if not self.results.currentItem() or not self.m_list.currentItem() or not self.f_list.currentItem():
            QMessageBox.warning(self, "Incomplete", "Select path, model, and field.")
            return
        p = self.results.currentItem().text().split(" = ")[0]
        m = self.m_list.currentItem().text()
        f = self.models[m][self.f_list.currentRow()]['name']
        
        if m not in self.mappings:
            self.mappings[m] = {}
        self.mappings[m][f] = p
        self.redraw_mappings()

    def redraw_mappings(self):
        self.map_text.clear()
        for model, fields in self.mappings.items():
            self.map_text.append(f"[{model}]")
            for field, path in fields.items():
                self.map_text.append(f"  {field} -> {path}")
            self.map_text.append("")

    def save(self):
        fp, _ = QFileDialog.getSaveFileName(self, "Save Mapping", "mapping.json", "JSON Files (*.json)")
        if not fp:
            return
        with open(fp, "w") as f:
            json.dump(self.mappings, f, indent=2)
        QMessageBox.information(self, "Done", f"Saved to {fp}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    models_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models.py")
    models = get_models_metadata(models_file)
    window = MapperApp(models)
    window.show()
    sys.exit(app.exec_())
