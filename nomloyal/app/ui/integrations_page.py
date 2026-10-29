"""CSV import (preview -> commit), export & templates, POS connectors, import history."""
from __future__ import annotations

import json

from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QTabWidget, QVBoxLayout, QWidget)

from app.config import exports_dir
from app.services.import_service import TEMPLATES, write_template
from app.ui.reusable_widgets import (EmptyState, PageHeader, button, card, confirm, fill_table, guarded, info, make_table,
                                     muted, subtitle, ts)
from app.ui.theme import CRIT, OK, WARN

KINDS = [("customers", "Customers"), ("products", "Products"), ("sales", "Sales (from another POS)")]


class IntegrationsPage(QWidget):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        self.preview = None
        self.connector = None
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        lay.addWidget(PageHeader("Import & POS", "CSV import/export and POS connectors"))
        self.tabs = QTabWidget(); lay.addWidget(self.tabs, 1)
        self.tabs.addTab(self._import_tab(), "CSV import")
        self.tabs.addTab(self._export_tab(), "Export & templates")
        self.tabs.addTab(self._pos_tab(), "POS connectors")
        self.tabs.addTab(self._history_tab(), "Import history")

    # ------------------------------------------------------------------ import
    def _import_tab(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 8, 0, 0)
        row = QHBoxLayout()
        self.kind = QComboBox()
        for k, t in KINDS:
            self.kind.addItem(t, k)
        pick = button("Choose CSV file…", "primary", "upload"); pick.clicked.connect(self._choose)
        row.addWidget(QLabel("Import")); row.addWidget(self.kind); row.addWidget(pick); row.addStretch(1)
        v.addLayout(row)
        v.addWidget(muted("Nothing is saved until you press Import. Rows with errors and duplicates are skipped. "
                          "Sales are linked to a customer only when the file has a matching loyalty ID or phone."))
        self.summary = QLabel(); v.addWidget(self.summary)
        self.ptable = make_table(["Line", "Result", "Details"], 2)
        self.pempty = EmptyState("Choose a file to see the preview.")
        v.addWidget(self.ptable, 1); v.addWidget(self.pempty)
        self.commit_btn = button("Import the valid rows", "primary", "check"); self.commit_btn.clicked.connect(self._commit)
        self.commit_btn.setEnabled(False)
        v.addWidget(self.commit_btn)
        return w

    def _choose(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choose CSV", "", "CSV (*.csv)")
        if p:
            self.connector = None
            ok, pv = guarded(self, "Import", self.ctx.imports.preview, self.kind.currentData(), p)
            if ok:
                self._show_preview(pv)

    def _show_preview(self, pv):
        self.preview = pv
        colors = {"ok": OK, "warning": WARN, "error": CRIT, "duplicate": WARN}
        fill_table(self.ptable, [[r.line, r.status, r.message] for r in pv.rows],
                   colors={(i, 1): colors[r.status] for i, r in enumerate(pv.rows)})
        self.ptable.setVisible(bool(pv.rows)); self.pempty.setVisible(not pv.rows)
        n_ok = pv.count("ok") + pv.count("warning")
        self.summary.setText(f"<b>{pv.filename}</b>: {n_ok} ready to import · {pv.count('error')} with errors · "
                             f"{pv.count('duplicate')} duplicates")
        self.commit_btn.setEnabled(n_ok > 0)

    def _commit(self):
        if not self.preview or not confirm(self, "Import", "Import the valid rows now?"):
            return
        ok, n = guarded(self, "Import", self.ctx.imports.commit, self.preview)
        if ok:
            msg = f"{n} record(s) imported."
            if self.connector:                     # folder connector: never import the same files twice
                self.connector.mark_imported()
                msg += " The files were moved to the 'imported' sub-folder."
                self.connector = None
            info(self, "Import", msg)
            self.preview = None; self.commit_btn.setEnabled(False)
            self.load_history()

    # ------------------------------------------------------------------ export
    def _export_tab(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 8, 0, 0)
        for k, t in KINDS:
            row = QHBoxLayout()
            tb = button(f"Template: {t.split(' (')[0]}", icon_name="download")
            tb.clicked.connect(lambda _c=False, kk=k: self._template(kk))
            eb = button(f"Export {t.split(' (')[0].lower()}", icon_name="download")
            eb.clicked.connect(lambda _c=False, kk=k: self._export(kk))
            row.addWidget(tb); row.addWidget(eb); row.addWidget(muted(", ".join(TEMPLATES[k])), 1)
            v.addWidget(card(subtitle(t), _wrap(row)))
        v.addWidget(muted("Customer exports contain personal data and need the Admin role. Store them securely."))
        v.addStretch(1)
        return w

    def _template(self, kind):
        p, _ = QFileDialog.getSaveFileName(self, "Save template", str(exports_dir() / f"{kind}_template.csv"), "CSV (*.csv)")
        if p:
            write_template(kind, p)
            info(self, "Template", "Template saved. Fill it in Excel and save as CSV UTF-8.")

    def _export(self, kind):
        p, _ = QFileDialog.getSaveFileName(self, "Export", str(exports_dir() / f"{kind}.csv"), "CSV (*.csv)")
        if p:
            ok, n = guarded(self, "Export", self.ctx.imports.export, kind, p)
            if ok:
                info(self, "Export", f"{n} row(s) exported.")

    # ------------------------------------------------------------------ connectors
    def _pos_tab(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 8, 0, 0)
        v.addWidget(muted("NomLoyal does not claim a direct integration with any specific POS brand. These connectors work "
                          "with exported files; a vendor API connector can be added (see docs/POS_CONNECTOR_GUIDE.md)."))
        row = QHBoxLayout()
        self.folder = QLineEdit(self.ctx.settings.get("pos_import_folder") or "")
        self.folder.setPlaceholderText("Folder where your POS saves sales CSV exports")
        br = button("Browse…"); br.clicked.connect(self._browse)
        t = button("Test", icon_name="check"); t.clicked.connect(self._test_folder)
        go = button("Preview import", "primary", "upload"); go.clicked.connect(self._import_folder)
        for x in (self.folder, br, t, go):
            row.addWidget(x)
        row.setStretch(0, 1)
        v.addWidget(card(subtitle("CSV folder connector"), _wrap(row)))
        row2 = QHBoxLayout()
        self.json_path = QLineEdit(); self.json_path.setPlaceholderText("Example JSON receipt export (see guide)")
        br2 = button("Browse…"); br2.clicked.connect(self._browse_json)
        go2 = button("Preview import", icon_name="upload"); go2.clicked.connect(self._import_json)
        for x in (self.json_path, br2, go2):
            row2.addWidget(x)
        row2.setStretch(0, 1)
        v.addWidget(card(subtitle("Example JSON POS adapter (template for vendor connectors)"), _wrap(row2)))
        self.conn_msg = muted(); v.addWidget(self.conn_msg)
        v.addStretch(1)
        return w

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "POS export folder", self.folder.text())
        if d:
            self.folder.setText(d)
            if self.ctx.can("integrations.manage"):
                self.ctx.settings.set("pos_import_folder", d)

    def _test_folder(self):
        from app.integrations.pos_csv import CsvFolderConnector
        ok, msg = CsvFolderConnector(self.folder.text()).test_connection()
        self.conn_msg.setText(("✔ " if ok else "✖ ") + msg)

    def _import_folder(self):
        from app.integrations.pos_csv import CsvFolderConnector
        con = CsvFolderConnector(self.folder.text())
        ok, msg = con.test_connection()
        if not ok:
            self.conn_msg.setText("✖ " + msg); return
        ok, pv = guarded(self, "Import", self.ctx.imports.preview, "sales", self.folder.text(), con.fetch_sales_rows())
        if ok:
            self.connector = con
            self.tabs.setCurrentIndex(0); self.kind.setCurrentIndex(2)
            self._show_preview(pv)

    def _browse_json(self):
        p, _ = QFileDialog.getOpenFileName(self, "JSON export", "", "JSON (*.json)")
        if p:
            self.json_path.setText(p)

    def _import_json(self):
        from app.integrations.pos_csv import ExampleJsonPOSAdapter
        self.connector = None
        a = ExampleJsonPOSAdapter(self.json_path.text())
        ok, msg = a.test_connection()
        if not ok:
            self.conn_msg.setText("✖ " + msg); return
        ok, pv = guarded(self, "Import", self.ctx.imports.preview, "sales", self.json_path.text(), a.fetch_sales_rows())
        if ok:
            self.tabs.setCurrentIndex(0); self.kind.setCurrentIndex(2)
            self._show_preview(pv)

    # ------------------------------------------------------------------ history
    def _history_tab(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 8, 0, 0)
        self.hist = make_table(["When", "Type", "File", "Status", "Imported", "Errors", "Duplicates", "By"], 2)
        self.hist.doubleClicked.connect(self._job_errors)
        v.addWidget(self.hist, 1)
        v.addWidget(muted("Double-click a job to see its row errors."))
        return w

    def load_history(self):
        jobs = self.ctx.imports.jobs()
        self._jobs = {j["id"]: j for j in jobs}
        fill_table(self.hist, [[ts(j["created_at"]), j["kind"], j["filename"], j["status"], j["rows_ok"], j["rows_error"],
                                j["rows_duplicate"], j["username"] or "-"] for j in jobs], [j["id"] for j in jobs])

    def _job_errors(self):
        from app.ui.reusable_widgets import selected_key
        j = self._jobs.get(selected_key(self.hist))
        if j:
            errs = json.loads(j["errors_json"] or "[]")
            info(self, "Import errors", "\n".join(errs[:40]) or "No errors.")

    def refresh(self):
        self.load_history()


def _wrap(layout) -> QWidget:
    w = QWidget(); w.setLayout(layout); return w
