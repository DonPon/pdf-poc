#!/usr/bin/env python3
import sys
import ast
import json
import os
import random
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QSplitter, QListWidget, QLineEdit, 
                             QPushButton, QLabel, QFileDialog, QMessageBox, QTextEdit)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QColor, QBrush

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

# --- Confetti Overlay ---
class ConfettiOverlay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setGeometry(parent.rect())
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.particles = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.hide()

    def burst(self):
        self.setGeometry(self.parent().rect())
        self.particles = []
        for _ in range(40):
            x = random.randint(0, self.width())
            y = random.randint(0, self.height() // 2)
            color = QColor(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            dx = random.uniform(-3, 3)
            dy = random.uniform(-5, -1)
            life = random.randint(30, 60)
            self.particles.append([x, y, dx, dy, life, color])
        self.show()
        self.raise_()
        self.timer.start(30)

    def animate(self):
        alive = []
        for p in self.particles:
            p[0] += p[2]
            p[1] += p[3]
            p[3] += 0.15  # gravity
            p[4] -= 1
            if p[4] > 0:
                alive.append(p)
        self.particles = alive
        if not self.particles:
            self.timer.stop()
            self.hide()
            return
        self.update()

    def stop(self):
        self.particles = []
        self.timer.stop()
        self.hide()

    def paintEvent(self, event):
        if not self.particles:
            return
        painter = QPainter(self)
        for p in self.particles:
            alpha = min(255, int(p[4] * 8))
            color = QColor(p[5])
            color.setAlpha(alpha)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(int(p[0]), int(p[1]), 8, 8)
        painter.end()


# --- App ---
class MapperApp(QMainWindow):
    def __init__(self, models):
        super().__init__()
        self.models = models
        self.data = None
        self.mappings = {}
        self.score = 0
        
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
        
        self.score_label = QLabel("Score: 0")
        self.score_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #2e7d32;")
        r_layout.insertWidget(0, self.score_label)
        
        self.anim_label = QLabel("")
        self.anim_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #ff6f00;")
        self.anim_label.setAlignment(Qt.AlignCenter)
        self.anim_label.hide()
        r_layout.insertWidget(1, self.anim_label)
        
        self.confetti = ConfettiOverlay(self)

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
        for f in self.models[m]: self.f_list.addItem(f"{f['name']} - ({f['verbose']})")

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
        points_added = random.randint(1, 15)
        self.score += points_added
        self.score_label.setText(f"Score: {self.score}")
        self.show_animation(points_added)

    def show_animation(self, points):
        self.anim_label.setText(f"+{points}")
        self.anim_label.show()
        self.anim_label.setStyleSheet("font-size: 48px; font-weight: bold; color: #ff6f00;")
        self.confetti.burst()
        QTimer.singleShot(800, self.hide_animation)

    def hide_animation(self):
        self.anim_label.hide()
        self.confetti.stop()

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
        #QMessageBox.information(self, "Done", f"Saved to {fp}\n\nTotal Points Earned: {self.score}")
        QMessageBox.information(self, "Done", f"🎉 Saved successfully! 🎉\n📁 {fp}\n\n🏆 Total Points Earned: {self.score}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    models_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models.py")
    models = get_models_metadata(models_file)
    window = MapperApp(models)
    window.show()
    sys.exit(app.exec_())
