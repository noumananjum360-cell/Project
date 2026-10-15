"""Users and roles."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from nomload import theme
from nomload.i18n import _
from nomload.services.context import ROLE_LABELS
from nomload.services.reports import fmt_ts
from nomload.ui.dialogs import UserDialog
from nomload.ui.widgets import Card, PageHeader, button, confirm, error, fill_table, make_table, selected_data


class UsersPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.setObjectName("Page")
        self.main = main
        self.app = main.app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        hdr = PageHeader("Users")
        n = hdr.add(button("New user", "Primary", "plus"))
        n.clicked.connect(self.new)
        lay.addWidget(hdr)
        c = Card()
        self.table = make_table(["Username", "Full name", "Role", "Status", "Last login", "Created"], 1)
        self.table.doubleClicked.connect(self.edit)
        c.lay.addWidget(self.table)
        bb = QHBoxLayout()
        e = button("Edit / reset password", icon_name="edit")
        e.clicked.connect(self.edit)
        t = button("Enable / disable", icon_name="lock")
        t.clicked.connect(self.toggle)
        bb.addWidget(e)
        bb.addWidget(t)
        bb.addStretch(1)
        c.lay.addLayout(bb)
        lay.addWidget(c, 1)
        r = Card("Roles")
        lbl = QLabel(_("<b>Admin</b>: setup, cameras, models, users, settings, delete records.<br>"
                       "<b>Supervisor</b>: approve mismatches with PIN, review low-confidence counts, adjust counts, products.<br>"
                       "<b>Clerk</b>: run loading sessions, enter gate passes, view history and reports. "
                       "Clerks cannot delete or change counted records."))
        lbl.setWordWrap(True)
        r.lay.addWidget(lbl)
        lay.addWidget(r)

    def showEvent(self, e):
        super().showEvent(e)
        self.reload()

    def reload(self):
        rows = self.app.auth.users()
        self._rows = rows
        colors = {(i, 3): theme.c("success") if r["active"] else theme.c("muted") for i, r in enumerate(rows)}
        fill_table(self.table, [[r["username"], r["full_name"], ROLE_LABELS[r["role"]],
                                 _("Active") if r["active"] else _("Disabled"), fmt_ts(r["last_login"]),
                                 fmt_ts(r["created_at"])[:11]] for r in rows], [r["id"] for r in rows], colors)

    def _row(self):
        uid = selected_data(self.table)
        return next((r for r in self._rows if r["id"] == uid), None)

    def new(self):
        if UserDialog(self, self.app).exec():
            self.reload()

    def edit(self):
        r = self._row()
        if r and UserDialog(self, self.app, r).exec():
            self.reload()

    def toggle(self):
        r = self._row()
        if not r:
            return
        if r["id"] == self.app.user.id:
            error(self, _("You cannot disable your own account."))
            return
        if confirm(self, f"{_('Disable') if r['active'] else _('Enable')} {r['username']}?"):
            try:
                self.app.auth.update_user(r["id"], self.app.user, active=0 if r["active"] else 1)
            except Exception as e:
                error(self, str(e))
            self.reload()
