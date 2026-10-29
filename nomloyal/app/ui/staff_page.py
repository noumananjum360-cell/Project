"""Staff accounts and roles."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLineEdit,
                               QVBoxLayout, QWidget)

from app.security.permissions import PERMISSIONS, ROLES
from app.ui.reusable_widgets import (PageHeader, button, card, fill_table, guarded, info, make_table, muted, selected_key,
                                     subtitle)

ROLE_TEXT = {"Admin": "Full configuration, staff, privacy, integrations, backups and exports.",
             "Manager": "Customers, sales and analytics, VIP overrides, refunds, alerts, imports.",
             "Cashier": "Sales and customer lookup / registration; sees only what is needed for service."}


class StaffDialog(QDialog):
    def __init__(self, ctx, parent=None, staff=None):
        super().__init__(parent)
        self.ctx, self.staff = ctx, staff
        self.setWindowTitle("Edit staff" if staff else "New staff account"); self.setMinimumWidth(440)
        v = QVBoxLayout(self); f = QFormLayout()
        self.username = QLineEdit(staff.username if staff else ""); self.username.setEnabled(staff is None)
        self.name = QLineEdit(staff.full_name if staff else "")
        self.role = QComboBox(); self.role.addItems(ROLES)
        if staff:
            self.role.setCurrentText(staff.role)
        else:
            self.role.setCurrentText("Cashier")
        self.active = QCheckBox("Active"); self.active.setChecked(staff.active if staff else True)
        self.pw = QLineEdit(); self.pw.setEchoMode(QLineEdit.Password)
        self.pw.setPlaceholderText("leave empty to keep" if staff else "at least 8 characters, letters and numbers")
        f.addRow("Username", self.username); f.addRow("Full name", self.name); f.addRow("Role", self.role)
        f.addRow("", self.active); f.addRow("Password" if not staff else "New password", self.pw)
        v.addLayout(f)
        self.role_info = muted(); v.addWidget(self.role_info)
        self.role.currentTextChanged.connect(lambda r: self.role_info.setText(ROLE_TEXT[r]))
        self.role_info.setText(ROLE_TEXT[self.role.currentText()])
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save); bb.rejected.connect(self.reject); v.addWidget(bb)

    def _save(self):
        a = self.ctx.auth
        if self.staff is None:
            ok, _ = guarded(self, "Staff", a.create, self.username.text(), self.pw.text(), self.role.currentText(),
                            self.name.text())
        else:
            ok, _ = guarded(self, "Staff", a.update, self.staff.id, None, full_name=self.name.text().strip(),
                            role=self.role.currentText(), active=self.active.isChecked())
            if ok and self.pw.text():
                ok, _ = guarded(self, "Staff", a.reset_password, self.staff.id, self.pw.text())
                if ok:
                    info(self, "Staff", "Password set. The user must change it at the next sign-in.")
        if ok:
            self.accept()


class ChangePasswordDialog(QDialog):
    def __init__(self, ctx, parent=None, forced: bool = False):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Change password"); self.setMinimumWidth(400)
        v = QVBoxLayout(self)
        if forced:
            v.addWidget(muted("Your password was set by an administrator. Choose your own password to continue."))
        f = QFormLayout()
        self.old, self.new, self.rep = QLineEdit(), QLineEdit(), QLineEdit()
        for e in (self.old, self.new, self.rep):
            e.setEchoMode(QLineEdit.Password)
        f.addRow("Current password", self.old); f.addRow("New password", self.new); f.addRow("Repeat", self.rep)
        v.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject); v.addWidget(bb)

    def _ok(self):
        if self.new.text() != self.rep.text():
            info(self, "Change password", "The new passwords do not match."); return
        if guarded(self, "Change password", self.ctx.auth.change_own_password, self.old.text(), self.new.text())[0]:
            info(self, "Change password", "Password changed.")
            self.accept()


class StaffPage(QWidget):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        h = PageHeader("Staff", "Accounts and permissions")
        b = h.add(button("New account", "primary", "plus")); b.clicked.connect(self.new)
        lay.addWidget(h)
        self.table = make_table(["Username", "Name", "Role", "Status"], 1)
        self.table.doubleClicked.connect(self.edit)
        self.table.setMinimumHeight(240)
        lay.addWidget(self.table)
        e = button("Edit / reset password", icon_name="edit"); e.clicked.connect(self.edit)
        lay.addWidget(e)
        perms = sorted(set().union(*PERMISSIONS.values()))
        matrix = make_table(["Permission"] + list(ROLES), 0, sortable=False)
        fill_table(matrix, [[p] + ["✔" if p in PERMISSIONS[r] else "" for r in ROLES] for p in perms])
        matrix.setMinimumHeight(360)
        lay.addWidget(card(subtitle("What each role can do"), matrix,
                           muted("Optional: Store settings can allow Managers to edit VIP rules.")))

    def refresh(self):
        st = self.ctx.auth.list()
        fill_table(self.table, [[s.username, s.full_name, s.role, "active" if s.active else "disabled"] for s in st],
                   [s.id for s in st])

    def new(self):
        if StaffDialog(self.ctx, self).exec():
            self.refresh()

    def edit(self):
        uid = selected_key(self.table)
        if uid and StaffDialog(self.ctx, self, self.ctx.auth.get(uid)).exec():
            self.refresh()
