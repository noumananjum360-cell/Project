"""Training wizard: collect frames -> annotate (with auto-label) -> train -> evaluate & activate."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import cv2
from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog,
                               QLabel, QListWidget, QListWidgetItem, QPlainTextEdit, QProgressBar, QProgressDialog,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from nomload.i18n import _
from nomload.training.dataset import Dataset, add_synthetic, extract_frames
from nomload.training.trainer import TrainJob, list_models, ultralytics_available
from nomload.ui.widgets import (BarChart, Card, PageHeader, bgr_to_qimage, button, confirm, error, fill_table, info,
                                make_table, selected_data)

PALETTE = ["#E8A33D", "#3E8EDE", "#D64545", "#1F9D55", "#9B59B6", "#16A085", "#F39C12", "#7F8C8D", "#C0392B", "#2C3E50"]


# ======================================================================= annotation canvas
class AnnotCanvas(QWidget):
    changed = Signal()
    class_picked = Signal(int)

    def __init__(self):
        super().__init__()
        self.img: QImage | None = None
        self.w = self.h = 1
        self.boxes: list[list] = []  # [cls, x0, y0, x1, y1] in image px
        self.sel = -1
        self.cls = 0
        self.classes: list[str] = []
        self.drag = None
        self.mouse = None
        self.setMinimumSize(640, 360)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_image(self, bgr, boxes):
        if bgr is None:
            self.img, self.boxes, self.sel = None, [], -1
            self.update()
            return
        self.img = bgr_to_qimage(bgr)
        self.h, self.w = bgr.shape[:2]
        self.boxes = [list(b) for b in boxes]
        self.sel = -1
        self.update()

    def _rect(self):
        s = min(self.width() / self.w, self.height() / self.h)
        return QRectF((self.width() - self.w * s) / 2, (self.height() - self.h * s) / 2, self.w * s, self.h * s), s

    def _to_img(self, p):
        r, s = self._rect()
        return ((p.x() - r.x()) / s, (p.y() - r.y()) / s)

    def _to_w(self, x, y):
        r, s = self._rect()
        return QPointF(r.x() + x * s, r.y() + y * s)

    def mousePressEvent(self, e):
        x, y = self._to_img(e.position())
        hit = [i for i, b in enumerate(self.boxes) if b[1] <= x <= b[3] and b[2] <= y <= b[4]]
        if e.button() == Qt.MouseButton.RightButton:
            if hit:
                self.boxes.pop(hit[-1])
                self.sel = -1
                self.changed.emit()
            self.update()
            return
        if hit and not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.sel = hit[-1]
            self.update()
            return
        self.drag = (x, y)

    def mouseMoveEvent(self, e):
        self.mouse = self._to_img(e.position())
        if self.drag:
            self.update()

    def mouseReleaseEvent(self, e):
        if not self.drag:
            return
        x0, y0 = self.drag
        x1, y1 = self._to_img(e.position())
        self.drag = None
        if abs(x1 - x0) > 4 and abs(y1 - y0) > 4:
            self.boxes.append([self.cls, min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)])
            self.sel = len(self.boxes) - 1
            self.changed.emit()
        self.update()

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and 0 <= self.sel < len(self.boxes):
            self.boxes.pop(self.sel)
            self.sel = -1
            self.changed.emit()
            self.update()
        elif Qt.Key.Key_1 <= k <= Qt.Key.Key_9:
            c = k - Qt.Key.Key_1
            if c < len(self.classes):
                self.cls = c
                if 0 <= self.sel < len(self.boxes):
                    self.boxes[self.sel][0] = c
                    self.changed.emit()
                self.update()
                self.class_picked.emit(c)
        else:
            super().keyPressEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#0F1626"))
        if self.img is None:
            p.setPen(QColor("#9AA5BC"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, _("Select an image on the left"))
            return
        r, s = self._rect()
        p.drawImage(r, self.img)
        f = QFont()
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        for i, (c, x0, y0, x1, y1) in enumerate(self.boxes):
            col = QColor(PALETTE[int(c) % len(PALETTE)])
            p.setPen(QPen(col, 3 if i == self.sel else 2))
            p.setBrush(QColor(col.red(), col.green(), col.blue(), 50 if i == self.sel else 0))
            a, b = self._to_w(x0, y0), self._to_w(x1, y1)
            p.drawRect(QRectF(a, b))
            name = self.classes[int(c)] if int(c) < len(self.classes) else str(c)
            p.fillRect(QRectF(a.x(), a.y() - 16, 8 + 7 * len(name), 16), col)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(QPointF(a.x() + 4, a.y() - 4), name)
        if self.drag and self.mouse:
            p.setPen(QPen(QColor(PALETTE[self.cls % len(PALETTE)]), 2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(self._to_w(*self.drag), self._to_w(*self.mouse)))


# ======================================================================= worker
class Worker(QObject):
    log = Signal(str)
    progress = Signal(int, int, float)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self.done.emit(self.fn(self))
        except Exception as e:  # report to UI
            self.failed.emit(str(e))


# ======================================================================= page
class TrainingPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.setObjectName("Page")
        self.main = main
        self.app = main.app
        self.ds: Dataset | None = None
        self.files: list[Path] = []
        self.idx = -1
        self.job: TrainJob | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        hdr = PageHeader("Training")
        self.ds_combo = QComboBox()
        self.ds_combo.setMinimumWidth(240)
        self.ds_combo.currentIndexChanged.connect(self._ds_changed)
        hdr.add(QLabel(_("Dataset")))
        hdr.add(self.ds_combo)
        dd = hdr.add(button("Delete dataset", icon_name="x"))
        dd.clicked.connect(self.delete_dataset)
        nd = hdr.add(button("New dataset", icon_name="plus"))
        nd.clicked.connect(self.new_dataset)
        lay.addWidget(hdr)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self.tabs.addTab(self._tab_collect(), "1  " + _("Collect frames"))
        self.tabs.addTab(self._tab_annotate(), "2  " + _("Annotate"))
        self.tabs.addTab(self._tab_train(), "3  " + _("Train"))
        self.tabs.addTab(self._tab_models(), "4  " + _("Evaluate && activate"))
        self.tabs.currentChanged.connect(self._tab_changed)

    # ------------------------------------------------------------- tabs
    def _tab_collect(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 12, 0, 0)
        c = Card("Extract frames from video")
        f = QFormLayout()
        self.every = QSpinBox()
        self.every.setRange(1, 300)
        self.every.setValue(15)
        self.maxf = QSpinBox()
        self.maxf.setRange(10, 5000)
        self.maxf.setValue(300)
        f.addRow(_("Take every Nth frame"), self.every)
        f.addRow(_("Maximum frames"), self.maxf)
        c.lay.addLayout(f)
        b = button("Choose video and extract", "Primary", "film")
        b.clicked.connect(self.extract)
        c.lay.addWidget(b, alignment=Qt.AlignmentFlag.AlignLeft)
        l.addWidget(c)
        c2 = Card("Synthetic data")
        h = QHBoxLayout()
        self.n_syn = QSpinBox()
        self.n_syn.setRange(10, 5000)
        self.n_syn.setValue(200)
        sb = button("Generate synthetic frames", icon_name="wand")
        sb.clicked.connect(self.synthetic)
        h.addWidget(self.n_syn)
        h.addWidget(sb)
        h.addStretch(1)
        c2.lay.addLayout(h)
        l.addWidget(c2)
        self.stats_card = Card("Dataset")
        self.stats_lbl = QLabel()
        self.stats_card.lay.addWidget(self.stats_lbl)
        l.addWidget(self.stats_card)
        vc = Card("Videos in this dataset")
        self.src_list = QListWidget()
        self.src_list.setMinimumHeight(140)
        vc.lay.addWidget(self.src_list)
        ds_btn = button("Delete frames from this video", icon_name="x")
        ds_btn.clicked.connect(self.delete_source)
        vc.lay.addWidget(ds_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        l.addWidget(vc, 1)
        return w

    def _tab_annotate(self):
        w = QWidget()
        l = QHBoxLayout(w)
        l.setContentsMargins(0, 12, 0, 0)
        left = QVBoxLayout()
        self.img_list = QListWidget()
        self.img_list.setMaximumWidth(260)
        self.img_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.img_list.currentRowChanged.connect(self.load_image)
        left.addWidget(self.img_list, 1)
        QShortcut(QKeySequence("Delete"), self.img_list, activated=self.delete_images,
                  context=Qt.ShortcutContext.WidgetShortcut)
        del_img = button("Delete image", icon_name="x")
        del_img.setToolTip(_("Delete the selected images from the dataset (Ctrl/Shift-click to select several)"))
        del_img.clicked.connect(self.delete_images)
        left.addWidget(del_img)
        self.only_unl = QCheckBox(_("Show only unlabelled"))
        self.only_unl.toggled.connect(self.reload_images)
        left.addWidget(self.only_unl)
        l.addLayout(left)
        mid = QVBoxLayout()
        bar = QHBoxLayout()
        self.cls_combo = QComboBox()
        self.cls_combo.currentIndexChanged.connect(self._cls_changed)
        addc = button("Add class", icon_name="plus")
        addc.clicked.connect(self.add_class)
        auto = button("Auto-label", "Accent", "wand")
        auto.clicked.connect(self.auto_label)
        auto_all = button("Auto-label all unlabelled", icon_name="wand")
        auto_all.clicked.connect(self.auto_label_all)
        prev = button("◀ Prev")
        prev.clicked.connect(lambda: self.step(-1))
        nxt = button("Save & next ▶", "Primary")
        nxt.clicked.connect(lambda: self.step(1))
        bar.addWidget(QLabel(_("Class")))
        bar.addWidget(self.cls_combo)
        bar.addWidget(addc)
        bar.addWidget(auto)
        bar.addWidget(auto_all)
        clr = button("Clear boxes", icon_name="x")
        clr.clicked.connect(self.clear_boxes)
        bar.addWidget(clr)
        bar.addStretch(1)
        mid.addLayout(bar)
        self.canvas = AnnotCanvas()
        self.canvas.changed.connect(self.save_labels)
        self.canvas.class_picked.connect(self.sync_class)
        mid.addWidget(self.canvas, 1)
        hint = QLabel(_("Drag: new box · 1-9: class · Del: remove · PgDn: next"))
        hint.setObjectName("Muted")
        foot = QHBoxLayout()
        foot.addWidget(hint, 1)
        foot.addWidget(prev)
        foot.addWidget(nxt)
        mid.addLayout(foot)
        l.addLayout(mid, 1)
        QShortcut(QKeySequence("PgDown"), w, activated=lambda: self.step(1))
        QShortcut(QKeySequence("PgUp"), w, activated=lambda: self.step(-1))
        return w

    def _tab_train(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 12, 0, 0)
        c = Card("Train model")
        f = QFormLayout()
        self.backend = QComboBox()
        self.backend.addItem(_("Built-in trainer (CPU)"), "builtin")
        if ultralytics_available():
            self.backend.addItem(_("Ultralytics YOLO (installed)"), "ultralytics")
        self.iters = QSpinBox()
        self.iters.setRange(100, 50000)
        self.iters.setSingleStep(100)
        self.iters.setValue(1500)
        self.finetune = QCheckBox(_("Start from current model"))
        self.finetune.setChecked(True)
        f.addRow(_("Trainer"), self.backend)
        f.addRow(_("Iterations"), self.iters)
        f.addRow("", self.finetune)
        c.lay.addLayout(f)
        h = QHBoxLayout()
        self.train_btn = button("Start training", "Primary", "play")
        self.train_btn.clicked.connect(self.start_training)
        self.stop_btn = button("Stop", icon_name="stop")
        self.stop_btn.clicked.connect(self.stop_training)
        self.stop_btn.setEnabled(False)
        h.addWidget(self.train_btn)
        h.addWidget(self.stop_btn)
        h.addStretch(1)
        c.lay.addLayout(h)
        self.train_prog = QProgressBar()
        self.train_prog.setRange(0, 1000)
        c.lay.addWidget(self.train_prog)
        l.addWidget(c)
        lc = Card("Training loss")
        self.loss_chart = BarChart(value_fmt="{:.2f}")
        self.loss_chart.setMinimumHeight(160)
        lc.lay.addWidget(self.loss_chart)
        l.addWidget(lc)
        self.train_log = QPlainTextEdit()
        self.train_log.setReadOnly(True)
        self.train_log.setMaximumBlockCount(2000)
        l.addWidget(self.train_log, 1)
        self.losses: list[float] = []
        return w

    def _tab_models(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 12, 0, 0)
        c = Card("Detector models")
        self.models = make_table(["Model", "Created", "Images", "Precision", "Recall", "Active"], 0)
        c.lay.addWidget(self.models)
        h = QHBoxLayout()
        act = button("Activate", "Primary", "check")
        act.clicked.connect(self.activate)
        ev = button("Test on sample videos", icon_name="film")
        ev.clicked.connect(self.eval_samples)
        imp = button("Import ONNX model...", icon_name="upload")
        imp.clicked.connect(self.import_model)
        dm = button("Delete model", icon_name="x")
        dm.clicked.connect(self.delete_model)
        h.addWidget(act)
        h.addWidget(ev)
        h.addWidget(imp)
        h.addWidget(dm)
        h.addStretch(1)
        c.lay.addLayout(h)
        l.addWidget(c, 1)
        self.eval_out = QPlainTextEdit()
        self.eval_out.setReadOnly(True)
        self.eval_out.setMaximumHeight(220)
        l.addWidget(self.eval_out)
        return w

    # ------------------------------------------------------------- dataset
    def showEvent(self, e):
        super().showEvent(e)
        self.reload_datasets()

    def reload_datasets(self, select: str | None = None):
        cur = select or self.ds_combo.currentText()
        self.ds_combo.blockSignals(True)
        self.ds_combo.clear()
        for d in Dataset.list_all():
            self.ds_combo.addItem(d.name)
        self.ds_combo.blockSignals(False)
        if self.ds_combo.count() == 0:
            Dataset.create("my_site")
            self.ds_combo.addItem("my_site")
        i = self.ds_combo.findText(cur)
        self.ds_combo.setCurrentIndex(max(0, i))
        self._ds_changed()

    def new_dataset(self):
        name, ok = QInputDialog.getText(self, _("New dataset"), _("Name (e.g. cement_bay1):"))
        if ok and name.strip():
            Dataset.create(name.strip())
            self.reload_datasets(name.strip())

    def _ds_changed(self, *_a):
        name = self.ds_combo.currentText()
        if not name:
            return
        from nomload.config import datasets_dir
        self.ds = Dataset(datasets_dir() / name)
        self.cls_combo.blockSignals(True)
        self.cls_combo.clear()
        for i, c in enumerate(self.ds.classes):
            self.cls_combo.addItem(f"{i + 1}. {c}")
        self.cls_combo.blockSignals(False)
        self.canvas.classes = self.ds.classes
        self.update_stats()
        self.reload_images()

    def delete_dataset(self):
        if not self.ds:
            return
        n = len(self.ds.image_files())
        if not confirm(self, f"{_('Delete dataset')} {self.ds.name} {_('and its')} {n} {_('image(s)')}?\n\n"
                             f"{_('Trained models are kept.')}"):
            return
        self.ds.delete()
        self.ds = None
        self.idx = -1
        self.reload_datasets()

    def delete_source(self):
        it = self.src_list.currentItem()
        if not it or not self.ds:
            error(self, _("Select a video first."))
            return
        src, n = it.data(Qt.ItemDataRole.UserRole)
        if not confirm(self, f"{_('Delete all')} {n} {_('frame(s) taken from')} '{src}'?\n\n"
                             f"{_('They will not be used for training.')}"):
            return
        self.ds.delete_source(src)
        self.idx = -1
        self.update_stats()
        self.reload_images()

    def delete_images(self):
        rows = sorted({self.img_list.row(i) for i in self.img_list.selectedItems()})
        if not rows and 0 <= self.idx < len(self.files):
            rows = [self.idx]
        if not rows or not self.ds:
            return
        files = [self.files[r] for r in rows if r < len(self.files)]
        msg = f"{_('Delete')} {files[0].name}?" if len(files) == 1 else f"{_('Delete')} {len(files)} {_('images')}?"
        if not confirm(self, msg):
            return
        self.ds.delete_images(files)
        self.idx = min(rows)
        self.update_stats()
        self.reload_images()

    def clear_boxes(self):
        if 0 <= self.idx < len(self.files):
            self.canvas.boxes = []
            self.ds.clear_labels(self.files[self.idx])
            self.canvas.update()
            it = self.img_list.item(self.idx)
            if it:
                it.setText("○ " + self.files[self.idx].name)

    def update_stats(self):
        if not self.ds:
            return
        self.src_list.clear()
        for src, n in self.ds.sources().items():
            it = QListWidgetItem(f"{src}   ({n} {_('frames')})")
            it.setData(Qt.ItemDataRole.UserRole, (src, n))
            self.src_list.addItem(it)
        st = self.ds.stats()
        per = ", ".join(f"{k}: {v}" for k, v in st["per_class"].items() if v)
        self.stats_lbl.setText(f"<b>{st['images']}</b> {_('images')}, <b>{st['labeled']}</b> {_('labelled')}<br>{per}")

    def _tab_changed(self, i):
        if i == 1:
            self.reload_images()
        elif i == 3:
            self.reload_models()

    def extract(self):
        p, _f = QFileDialog.getOpenFileName(self, _("Choose loading video"), "", "Video (*.mp4 *.avi *.mkv *.mov)")
        if not p:
            return
        # read the video in a background thread; the dialog is updated by a timer
        dlg = QProgressDialog(_("Extracting frames..."), _("Stop"), 0, 100, self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        st = {"stop": False, "i": 0, "total": 1, "saved": 0, "done": False, "n": 0, "err": ""}
        dlg.canceled.connect(lambda: st.update(stop=True))
        ds, every, maxf = self.ds, self.every.value(), self.maxf.value()

        def work():
            try:
                st["n"] = extract_frames(p, ds, every, maxf, True,
                                         lambda i, total, saved: st.update(i=i, total=max(1, total), saved=saved),
                                         lambda: st["stop"])
            except Exception as e:  # shown below
                st["err"] = str(e)
            st["done"] = True

        threading.Thread(target=work, daemon=True, name="extract").start()
        from PySide6.QtCore import QTimer
        timer = QTimer(self)

        def tick():
            if not st["done"]:
                dlg.setValue(min(99, int(100 * st["i"] / st["total"])))
                dlg.setLabelText(f"{_('Extracting frames...')} {st['saved']}")
                return
            timer.stop()
            dlg.close()
            self.update_stats()
            if st["err"]:
                error(self, st["err"])
            else:
                info(self, f"{st['n']} {_('frames added. Next: Annotate.')}")

        timer.timeout.connect(tick)
        timer.start(200)

    def synthetic(self):
        from nomload.ui.widgets import run_async
        ds, n = self.ds, self.n_syn.value()

        def done(k):
            self.update_stats()
            info(self, f"{k} {_('synthetic frames added with labels.')}")

        run_async(self, lambda: add_synthetic(ds, n), done, busy=_("Rendering synthetic loading scenes..."))

    # ------------------------------------------------------------- annotate
    def reload_images(self):
        if not self.ds:
            return
        files = self.ds.image_files()
        if self.only_unl.isChecked():
            files = [f for f in files if not self.ds.is_labeled(f)]
        self.files = files
        self.img_list.blockSignals(True)
        self.img_list.clear()
        for f in files:
            it = QListWidgetItem(("✔ " if self.ds.is_labeled(f) else "○ ") + f.name)
            self.img_list.addItem(it)
        self.img_list.blockSignals(False)
        if files:
            self.img_list.setCurrentRow(max(0, min(self.idx, len(files) - 1)))
        else:
            self.idx = -1
            self.canvas.set_image(None, [])

    def load_image(self, row):
        if row < 0 or row >= len(self.files):
            return
        self.idx = row
        p = self.files[row]
        img = cv2.imread(str(p))
        if img is None:
            return
        self._img = img
        h, w = img.shape[:2]
        self.canvas.set_image(img, self.ds.read_labels(p, w, h))
        self.canvas.setFocus()

    def save_labels(self):
        if self.idx < 0 or self.idx >= len(self.files):
            return
        p = self.files[self.idx]
        self.ds.write_labels(p, self.canvas.boxes, self.canvas.w, self.canvas.h)
        it = self.img_list.item(self.idx)
        if it:
            it.setText("✔ " + p.name)

    def step(self, d):
        if self.files:
            self.save_labels()
            self.img_list.setCurrentRow(max(0, min(len(self.files) - 1, self.idx + d)))

    def _cls_changed(self, i):
        self.canvas.cls = max(0, i)
        if 0 <= self.canvas.sel < len(self.canvas.boxes):
            self.canvas.boxes[self.canvas.sel][0] = max(0, i)
            self.save_labels()
            self.canvas.update()

    def sync_class(self, c):
        self.cls_combo.setCurrentIndex(c)

    def add_class(self):
        name, ok = QInputDialog.getText(self, _("Add class"), _("Class name (e.g. cement_bag, carton_1L):"))
        if ok and name.strip():
            self.ds.add_class(name.strip().replace(" ", "_"))
            self._ds_changed()

    def _auto_boxes(self, img):
        det = self.app.registry.detector
        if det is None:
            return []
        classes = self.ds.classes
        out = []
        for d in det.detect(img):
            if d.cls in classes and d.score >= 0.4:
                out.append([classes.index(d.cls), d.x0, d.y0, d.x1, d.y1])
        return out

    def auto_label(self):
        if self.idx < 0:
            return
        boxes = self._auto_boxes(self._img)
        self.canvas.boxes += boxes
        self.canvas.update()
        self.save_labels()

    def auto_label_all(self):
        todo = [f for f in self.ds.image_files() if not self.ds.is_labeled(f)]
        if not todo:
            info(self, _("All images are already labelled."))
            return
        if not confirm(self, f"{_('Auto-label')} {len(todo)} {_('images with the current model? Review them afterwards.')}"):
            return
        dlg = QProgressDialog(_("Auto-labelling..."), _("Stop"), 0, len(todo), self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        for i, p in enumerate(todo):
            if dlg.wasCanceled():
                break
            img = cv2.imread(str(p))
            if img is not None:
                self.ds.write_labels(p, self._auto_boxes(img), img.shape[1], img.shape[0])
            dlg.setValue(i + 1)
            QApplication.processEvents()
        self.reload_images()
        self.update_stats()

    # ------------------------------------------------------------- train
    def start_training(self):
        if not self.ds:
            return
        st = self.ds.stats()
        if st["labeled"] < 5:
            error(self, _("Annotate at least 5 images (50+ recommended) before training."))
            return
        base = str(self.app.model_path()) if self.finetune.isChecked() else None
        self.job = TrainJob(self.ds, self.backend.currentData(), self.iters.value(), base)
        self.losses = []
        self.train_log.clear()
        w = Worker(lambda wk: self.job.run())
        self.job.log = w.log.emit
        self.job.progress = w.progress.emit
        w.log.connect(self.train_log.appendPlainText)
        w.progress.connect(self._train_progress)
        w.done.connect(self._train_done)
        w.failed.connect(self._train_failed)
        self._worker = w
        self.train_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        from nomload.services.context import audit
        audit(self.app.db, self.app.user, "training_started", "dataset", self.ds.name,
              {"backend": self.backend.currentData(), "iterations": self.iters.value(), "images": st["labeled"]})
        w.start()

    def stop_training(self):
        if self.job:
            self.job.stop()

    def _train_progress(self, i, n, loss):
        self.train_prog.setValue(int(1000 * i / max(1, n)))
        self.losses.append(loss)
        pts = self.losses[-40:]
        self.loss_chart.set_data([str(len(self.losses) - len(pts) + k + 1) for k in range(len(pts))], pts)

    def _train_done(self, res):
        self.train_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.train_prog.setValue(1000)
        m = res.get("metrics", {})
        txt = "\n".join(f"  {c}: precision {v['precision']:.0%}, recall {v['recall']:.0%}" for c, v in m.items())
        if confirm(self, f"{_('Training finished.')}\n{txt}\n\n{_('Activate the new model now?')}"):
            self._activate(res["path"])
        self.tabs.setCurrentIndex(3)

    def _train_failed(self, msg):
        self.train_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        error(self, msg)

    # ------------------------------------------------------------- models
    def reload_models(self):
        ms = list_models()
        active = str(self.app.model_path())
        rows = []
        for m in ms:
            met = m.get("metrics") or {}
            goods = [v for k, v in met.items() if k not in ("person", "truck", "plate")] or list(met.values())
            pr = sum(v["precision"] for v in goods) / len(goods) if goods else None
            rc = sum(v["recall"] for v in goods) / len(goods) if goods else None
            rows.append([m["name"], m.get("created", ""), m.get("images") or "", f"{pr:.0%}" if pr is not None else "-",
                         f"{rc:.0%}" if rc is not None else "-", "● " + _("active") if m["path"] == active else ""])
        fill_table(self.models, rows, [m["path"] for m in ms])

    def _activate(self, path):
        from nomload.ui.widgets import run_async
        run_async(self, lambda: self.app.activate_model(path, self.app.user), self._activated,
                  lambda m: error(self, f"{_('Model could not be loaded')}: {m}"), busy=_("Loading model..."))

    def _activated(self, det):
        info(self, f"{_('Active model')}: {det.name}\n{_('Classes')}: {', '.join(det.classes)}\n"
                   f"{_('All bays now use this model (no restart needed).')}")
        self.reload_models()

    def activate(self):
        p = selected_data(self.models)
        if p:
            self._activate(p)

    def delete_model(self):
        p = selected_data(self.models)
        if not p:
            error(self, _("Select a model first."))
            return
        if not confirm(self, f"{_('Delete model')} {Path(p).stem}?"):
            return
        from nomload.training.trainer import delete_model
        try:
            delete_model(p, self.app.model_path())
        except ValueError as e:
            error(self, str(e))
            return
        self.reload_models()

    def import_model(self):
        p, _f = QFileDialog.getOpenFileName(self, _("Import ONNX detector"), "", "ONNX (*.onnx)")
        if not p:
            return
        import shutil
        import time
        from nomload.config import user_models_dir
        dst = user_models_dir() / f"detector_imported_{time.strftime('%Y%m%d_%H%M%S')}.onnx"
        shutil.copy2(p, dst)
        dst.with_suffix(".json").write_text(json.dumps({"created": time.strftime("%Y%m%d_%H%M%S"), "backend": "import"}))
        self.reload_models()

    def eval_samples(self):
        from nomload.config import samples_dir
        folder = samples_dir()
        if not (folder / "answer_key.csv").exists():
            error(self, _("No sample videos with answer key found."))
            return
        self.eval_out.setPlainText(_("Running the full counting pipeline on the sample videos..."))

        def run(wk):
            from nomload.core.detector import ModelRegistry
            from nomload.services.evaluation import evaluate_folder
            reg = ModelRegistry()
            p = selected_data(self.models) or str(self.app.model_path())
            reg.load(p, conf_threshold=float(self.app.settings.get("detector_conf") or 0.35))
            return evaluate_folder(reg, folder, int(self.app.settings.get("frame_skip") or 0), log=wk.log.emit)

        w = Worker(run)
        w.log.connect(self.eval_out.appendPlainText)
        w.done.connect(lambda rows: self.eval_out.appendPlainText(_("Done.")))
        w.failed.connect(lambda m: self.eval_out.appendPlainText("Error: " + m))
        self._eval_worker = w
        w.start()
