"""Role-based access control. Every service call that changes or reveals data checks a permission here."""
from __future__ import annotations

ROLES = ("Admin", "Manager", "Cashier")

PERMISSIONS: dict[str, set[str]] = {
    "Cashier": {
        "dashboard.view", "customers.view", "customers.create", "sales.create", "sales.view_own",
        "alerts.view", "products.view", "pos.use",
    },
    "Manager": {
        "dashboard.view", "customers.view", "customers.view_sensitive", "customers.create", "customers.edit",
        "customers.archive", "customers.export", "sales.create", "sales.view_own", "sales.view_all", "sales.refund",
        "sales.void", "products.view", "products.manage", "vip.view", "vip.override", "alerts.view", "alerts.handle",
        "reports.view", "reports.export", "pos.use", "import.run", "privacy.requests", "camera.view",
    },
}
PERMISSIONS["Admin"] = PERMISSIONS["Manager"] | {
    "customers.delete", "vip.rules", "staff.manage", "settings.manage", "privacy.manage", "integrations.manage",
    "camera.manage", "backup.manage", "audit.view", "demo.manage", "export.unrestricted",
}

# optional, set by the Admin in Settings: managers may edit VIP rules
OPTIONAL = {"vip.rules": "manager_can_edit_vip_rules"}


class PermissionDenied(Exception):
    pass


def role_can(role: str, perm: str, settings: dict | None = None) -> bool:
    if perm in PERMISSIONS.get(role, set()):
        return True
    key = OPTIONAL.get(perm)
    return bool(role == "Manager" and key and settings and settings.get(key))
