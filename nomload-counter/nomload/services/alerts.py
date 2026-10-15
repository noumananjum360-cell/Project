"""Alerts: on-screen + sound locally, and optional remote delivery.

Remote alerts (email / WhatsApp Cloud API / SMS HTTP gateway) are written to a
persistent queue first and delivered by a background sender whenever the
internet is available, so nothing is lost while the factory is offline.
"""
from __future__ import annotations

import json
import logging
import smtplib
import socket
import ssl
import threading
import time
import urllib.parse
import urllib.request
from email.message import EmailMessage
from pathlib import Path

from nomload.data import crypto
from nomload.data.db import Database

log = logging.getLogger(__name__)

KINDS = {
    "mismatch": ("critical", "Quantity mismatch"),
    "low_confidence": ("warning", "Low-confidence count"),
    "camera_offline": ("critical", "Camera offline"),
    "camera_online": ("info", "Camera back online"),
    "tamper": ("critical", "Camera tampering"),
    "plate_mismatch": ("warning", "Plate does not match gate pass"),
    "session_released": ("info", "Truck released after mismatch"),
    "cleared": ("info", "Truck cleared"),
}


class AlertCenter:
    def __init__(self, db: Database, settings):
        self.db = db
        self.settings = settings
        self.listeners: list = []   # callables(alert_dict)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------- raise
    def raise_alert(self, kind: str, message: str, bay_id: int | None = None, session_id: int | None = None,
                    attachment: str | None = None) -> int:
        sev, title = KINDS.get(kind, ("warning", kind))
        aid = self.db.execute("INSERT INTO alerts(ts, kind, severity, bay_id, session_id, message) VALUES (?,?,?,?,?,?)",
                              (time.time(), kind, sev, bay_id, session_id, message))
        alert = {"id": aid, "kind": kind, "severity": sev, "title": title, "message": message, "bay_id": bay_id,
                 "session_id": session_id, "ts": time.time()}
        for fn in list(self.listeners):
            try:
                fn(alert)
            except Exception:  # pragma: no cover
                log.exception("alert listener failed")
        if kind in (self.settings.get("remote_events") or []):
            self.queue_remote(f"NomLoad: {title}", self._format(alert), attachment)
        return aid

    def _format(self, a: dict) -> str:
        company = self.settings.get("company_name") or ""
        return f"{company}\n{a['title']}\n{a['message']}\n{time.strftime('%d-%b-%Y %H:%M:%S', time.localtime(a['ts']))}"

    def acknowledge(self, alert_id: int, user) -> None:
        self.db.execute("UPDATE alerts SET acknowledged_by=?, acknowledged_at=? WHERE id=?",
                        (user.id or None, time.time(), alert_id))

    def recent(self, limit: int = 100, unacked_only=False):
        sql = "SELECT * FROM alerts" + (" WHERE acknowledged_at IS NULL" if unacked_only else "") + " ORDER BY ts DESC LIMIT ?"
        return self.db.q(sql, (limit,))

    # ------------------------------------------------------------- remote queue
    def queue_remote(self, subject: str, body: str, attachment: str | None = None):
        s = self.settings
        targets = []
        if s.get("email_enabled") and s.get("email_to"):
            targets += [("email", t.strip()) for t in s.get("email_to").split(",") if t.strip()]
        if s.get("whatsapp_enabled") and s.get("whatsapp_to"):
            targets += [("whatsapp", t.strip()) for t in s.get("whatsapp_to").split(",") if t.strip()]
        if s.get("sms_enabled") and s.get("sms_to"):
            targets += [("sms", t.strip()) for t in s.get("sms_to").split(",") if t.strip()]
        for ch, to in targets:
            self.db.execute("INSERT INTO remote_queue(created_at, channel, recipient, subject, body, attachment) "
                            "VALUES (?,?,?,?,?,?)", (time.time(), ch, crypto.encrypt(to), subject, body, attachment))
        if targets:
            self._wake.set()

    def start_sender(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, daemon=True, name="remote-alerts")
            self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    @staticmethod
    def online(host="8.8.8.8", port=53, timeout=2.0) -> bool:
        try:
            socket.create_connection((host, port), timeout=timeout).close()
            return True
        except OSError:
            return False

    def _loop(self):
        while not self._stop.is_set():
            self._wake.wait(60)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                self.flush()
            except Exception:  # pragma: no cover
                log.exception("remote alert flush failed")

    def flush(self, check_online: bool = True) -> int:
        rows = self.db.q("SELECT * FROM remote_queue WHERE status='queued' AND attempts < 20 ORDER BY id LIMIT 50")
        if not rows or (check_online and not self.online()):
            return 0
        sent = 0
        for r in rows:
            to = crypto.decrypt(r["recipient"])
            try:
                {"email": self._send_email, "whatsapp": self._send_whatsapp, "sms": self._send_sms}[r["channel"]](
                    to, r["subject"], r["body"], r["attachment"])
                self.db.execute("UPDATE remote_queue SET status='sent', sent_at=?, attempts=attempts+1 WHERE id=?",
                                (time.time(), r["id"]))
                sent += 1
            except Exception as e:
                st = "failed" if r["attempts"] + 1 >= 20 else "queued"
                self.db.execute("UPDATE remote_queue SET attempts=attempts+1, last_error=?, status=? WHERE id=?",
                                (str(e)[:300], st, r["id"]))
        return sent

    def pending_count(self) -> int:
        return self.db.scalar("SELECT COUNT(*) FROM remote_queue WHERE status='queued'") or 0

    # ------------------------------------------------------------- transports
    def _send_email(self, to, subject, body, attachment):
        s = self.settings
        msg = EmailMessage()
        msg["From"] = s.get("email_from") or s.get("smtp_user")
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        if attachment and Path(attachment).exists() and Path(attachment).stat().st_size < 15 * 1024 * 1024:
            data = Path(attachment).read_bytes()
            sub = "pdf" if attachment.lower().endswith(".pdf") else "octet-stream"
            msg.add_attachment(data, maintype="application", subtype=sub, filename=Path(attachment).name)
        port = int(s.get("smtp_port") or 587)
        if port == 465:
            srv = smtplib.SMTP_SSL(s.get("smtp_host"), port, timeout=20, context=ssl.create_default_context())
        else:
            srv = smtplib.SMTP(s.get("smtp_host"), port, timeout=20)
            if s.get("smtp_tls"):
                srv.starttls(context=ssl.create_default_context())
        try:
            if s.get("smtp_user"):
                srv.login(s.get("smtp_user"), s.get("smtp_password"))
            srv.send_message(msg)
        finally:
            srv.quit()

    def _send_whatsapp(self, to, subject, body, attachment):
        """WhatsApp Business Cloud API (Meta). Requires a permanent token and phone number id."""
        s = self.settings
        url = f"https://graph.facebook.com/v19.0/{s.get('whatsapp_phone_id')}/messages"
        payload = {"messaging_product": "whatsapp", "to": to.replace("+", "").replace("-", ""), "type": "text",
                   "text": {"body": f"*{subject}*\n{body}"}}
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {s.get('whatsapp_token')}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            if r.status >= 300:
                raise RuntimeError(f"WhatsApp API HTTP {r.status}")

    def _send_sms(self, to, subject, body, attachment):
        """Generic HTTP SMS gateway: URL template with {to} and {message} placeholders."""
        tpl = self.settings.get("sms_url_template") or ""
        if "{to}" not in tpl or "{message}" not in tpl:
            raise RuntimeError("SMS URL template must contain {to} and {message}")
        url = tpl.format(to=urllib.parse.quote(to), message=urllib.parse.quote(f"{subject}: {body}"[:300]))
        with urllib.request.urlopen(url, timeout=20) as r:
            if r.status >= 300:
                raise RuntimeError(f"SMS gateway HTTP {r.status}")
