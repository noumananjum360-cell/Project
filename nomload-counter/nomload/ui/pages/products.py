"""Product profiles: detector class mapping, units per stack, tolerance, sample images."""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QSpinBox, QVBoxLayout, QWidget)

from nomload.config import COUNTABLE_CLASSES, DEFAULT_CLASSES, data_home
from nomload.i18n import _
from nomload.ui.widgets import Card, PageHeader, button, confirm, error, fill_table, info, make_table, selected_data


class ProductsPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.setObjectName("Page")
        self.main = main
        self.app = main.app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        hdr = PageHeader("Products")
        self.del_btn = hdr.add(button("Delete product", icon_name="x"))
        self.del_btn.clicked.connect(self.delete)
        new = hdr.add(button("New product", "Primary", "plus"))
        new.clicked.connect(self.new)
        lay.addWidget(hdr)
        body = QHBoxLayout()
        body.setSpacing(14)
        lc = Card("Product profiles")
        self.table = make_table(["Product", "SKU", "Detector class", "Units / detection", "Tolerance", "Active"], 0)
        self.table.itemSelectionChanged.connect(self.load_form)
        lc.lay.addWidget(self.table)
        body.addWidget(lc, 3)
        fc = Card("Profile")
        f = QFormLayout()
        self.name = QLineEdit()
        self.sku = QLineEdit()
        self.cls = QComboBox()
        self.cls.setEditable(True)
        self.units = QSpinBox()
        self.units.setRange(1, 1000)
        self.units.setToolTip(_("Units counted for each detected item"))
        self.tol_u = QSpinBox()
        self.tol_u.setRange(-1, 10000)
        self.tol_u.setSpecialValueText(_("use global"))
        self.tol_p = QDoubleSpinBox()
        self.tol_p.setRange(-0.1, 50)
        self.tol_p.setDecimals(1)
        self.tol_p.setSingleStep(0.5)
        self.tol_p.setSpecialValueText(_("use global"))
        self.tol_p.setSuffix(" %")
        self.notes = QLineEdit()
        self.active = QCheckBox(_("Active"))
        f.addRow(_("Name"), self.name)
        f.addRow(_("SKU / code"), self.sku)
        f.addRow(_("Detector class"), self.cls)
        f.addRow(_("Units per detection (stack rule)"), self.units)
        f.addRow(_("Tolerance (units)"), self.tol_u)
        f.addRow(_("Tolerance (%)"), self.tol_p)
        f.addRow(_("Notes"), self.notes)
        f.addRow("", self.active)
        fc.lay.addLayout(f)
        sv = button("Save profile", "Primary", "check")
        sv.clicked.connect(self.save)
        fc.lay.addWidget(sv)
        st = QLabel(_("Sample images"))
        st.setObjectName("CardTitle")
        fc.lay.addWidget(st)
        self.samples = QListWidget()
        self.samples.setViewMode(QListWidget.ViewMode.IconMode)
        self.samples.setIconSize(QSize(110, 80))
        self.samples.setFixedHeight(130)
        fc.lay.addWidget(self.samples)
        ab = button("Add sample images", icon_name="upload")
        ab.clicked.connect(self.add_samples)
        fc.lay.addWidget(ab)
        body.addWidget(fc, 2)
        lay.addLayout(body, 1)
        self.pid = None

    def showEvent(self, e):
        super().showEvent(e)
        self.del_btn.setVisible(bool(self.app.user and self.app.user.can("manage_products")))
        self.cls.clear()
        classes = list(COUNTABLE_CLASSES)
        det = self.app.registry.detector
        if det:
            classes = [c for c in det.classes if c not in ("person", "truck", "plate")] or classes
        self.cls.addItems(sorted(set(classes)))
        self.reload()

    def reload(self):
        ps = self.app.products.list()
        self._ps = ps
        fill_table(self.table, [[p.name, p.sku, p.detector_class, p.units_per_detection,
                                 (f"{p.tolerance_units} u" if p.tolerance_units is not None else "") +
                                 (f" {p.tolerance_pct}%" if p.tolerance_pct is not None else "") or _("global"),
                                 "✔" if p.active else ""] for p in ps], [p.id for p in ps])

    def load_form(self):
        pid = selected_data(self.table)
        p = next((x for x in self._ps if x.id == pid), None)
        if not p:
            return
        self.pid = p.id
        self.name.setText(p.name)
        self.sku.setText(p.sku)
        self.cls.setCurrentText(p.detector_class)
        self.units.setValue(p.units_per_detection)
        self.tol_u.setValue(p.tolerance_units if p.tolerance_units is not None else -1)
        self.tol_p.setValue(p.tolerance_pct if p.tolerance_pct is not None else -0.1)
        self.notes.setText(p.notes)
        self.active.setChecked(p.active)
        self.samples.clear()
        for s in self.app.products.samples(p.id):
            if Path(s).exists():
                self.samples.addItem(QListWidgetItem(QIcon(s), ""))

    def new(self):
        self.pid = None
        self.table.clearSelection()
        for w in (self.name, self.sku, self.notes):
            w.clear()
        self.units.setValue(1)
        self.tol_u.setValue(-1)
        self.tol_p.setValue(-0.1)
        self.active.setChecked(True)
        self.samples.clear()
        self.name.setFocus()

    def save(self):
        if not self.app.user.can("manage_products"):
            error(self, _("Only a supervisor or admin can change products."))
            return
        if not self.name.text().strip():
            error(self, _("Enter a product name."))
            return
        try:
            self.pid = self.app.products.save(
                self.app.user, self.name.text().strip(), self.cls.currentText().strip() or "bag", self.units.value(),
                self.sku.text().strip(), None if self.tol_u.value() < 0 else self.tol_u.value(),
                None if self.tol_p.value() < 0 else self.tol_p.value(), self.notes.text().strip(), self.pid,
                self.active.isChecked())
        except Exception as e:
            error(self, str(e))
            return
        self.reload()
        info(self, _("Product saved."))

    def delete(self):
        pid = selected_data(self.table)
        p = next((x for x in self._ps if x.id == pid), None)
        if not p:
            error(self, _("Select a product first."))
            return
        if not confirm(self, f"{_('Delete product')} {p.name}?"):
            return
        try:
            self.app.products.delete(self.app.user, p.id)
        except ValueError as e:
            error(self, str(e))
            return
        self.reload()
        self.new()

    def add_samples(self):
        if not self.pid:
            error(self, _("Save the product first."))
            return
        files, _f = QFileDialog.getOpenFileNames(self, _("Sample images"), "", "Images (*.jpg *.jpeg *.png *.bmp)")
        d = data_home() / "product_samples" / str(self.pid)
        d.mkdir(parents=True, exist_ok=True)
        for f in files:
            dst = d / f"{int(time.time() * 1000)}_{Path(f).name}"
            shutil.copy2(f, dst)
            self.app.products.add_sample(self.pid, str(dst))
        self.load_form()
