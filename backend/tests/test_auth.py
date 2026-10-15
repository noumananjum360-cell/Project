from __future__ import annotations

from app.services.email import OUTBOX
from tests.conftest import PASSWORD, Client, make_client


def test_register_login_me_logout() -> None:
    c = make_client()
    me = c.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"
    assert "password_hash" not in me.json()

    c.post("/api/v1/auth/logout")
    assert c.get("/api/v1/auth/me").status_code == 401

    c2 = make_client(register=False)
    r = c2.post("/api/v1/auth/login", json={"email": "ALICE@example.com", "password": PASSWORD})
    assert r.status_code == 200
    assert "bg_access" in r.cookies or c2.cookies.get("bg_access")
    assert r.json()["tokens"] is None  # web clients never receive tokens in the body


def test_duplicate_registration_rejected(client: Client) -> None:
    r = Client(client.app).post("/api/v1/auth/register", json={"email": "alice@example.com", "password": PASSWORD})
    assert r.status_code == 409


def test_weak_password_rejected() -> None:
    r = Client(make_client(register=False).app).post(
        "/api/v1/auth/register", json={"email": "weak@example.com", "password": "short"}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_invalid_credentials_are_generic(client: Client) -> None:
    c = make_client(register=False)
    wrong_pw = c.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "Wrong123456"})
    no_user = c.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "Wrong123456"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json()["error"]["message"] == no_user.json()["error"]["message"]


def test_protected_route_requires_auth() -> None:
    c = make_client(register=False)
    assert c.get("/api/v1/profile").status_code == 401
    assert c.get("/api/v1/jobs").status_code == 401


def test_csrf_required_for_cookie_auth(client: Client) -> None:
    client.csrf = None
    r = client.put("/api/v1/profile", json={"full_name": "X"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


def test_extension_bearer_flow_and_refresh_rotation(client: Client) -> None:
    ext = make_client(register=False)
    r = ext.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": PASSWORD, "client": "extension"})
    tokens = r.json()["tokens"]
    assert tokens["access_token"] and tokens["refresh_token"]
    ext.cookies.clear()
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert ext.get("/api/v1/auth/me", headers=h).status_code == 200
    # Bearer requests need no CSRF header.
    assert ext.put("/api/v1/profile", json={"full_name": "Ext"}, headers=h).status_code == 200

    r2 = ext.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r2.status_code == 200
    new = r2.json()["tokens"]
    assert new["refresh_token"] != tokens["refresh_token"]
    # Reusing the old token is rejected and revokes the family.
    assert ext.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    assert ext.post("/api/v1/auth/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 401


def test_cookie_refresh(client: Client) -> None:
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 200
    client.csrf = r.json()["csrf_token"]
    assert client.get("/api/v1/auth/me").status_code == 200


def test_password_reset_flow(client: Client) -> None:
    anon = make_client(register=False)
    assert anon.post("/api/v1/auth/forgot-password", json={"email": "alice@example.com"}).status_code == 200
    assert anon.post("/api/v1/auth/forgot-password", json={"email": "ghost@example.com"}).status_code == 200
    resets = [m for m in OUTBOX if "Reset" in m["subject"]]
    assert len(resets) == 1
    token = resets[0]["link"].split("token=")[1]
    new_pw = "NewPassword42x"
    assert anon.post("/api/v1/auth/reset-password", json={"token": token, "new_password": new_pw}).status_code == 200
    # Token is single-use.
    assert anon.post("/api/v1/auth/reset-password", json={"token": token, "new_password": new_pw}).status_code == 401
    assert anon.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": new_pw}).status_code == 200


def test_email_verification(client: Client) -> None:
    link = next(m["link"] for m in OUTBOX if "Verify" in m["subject"])
    token = link.split("token=")[1]
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    assert client.get("/api/v1/auth/me").json()["email_verified_at"] is not None


def test_change_password(client: Client) -> None:
    r = client.post("/api/v1/auth/change-password", json={"current_password": "nope", "new_password": "Another123abc"})
    assert r.status_code == 401
    r = client.post("/api/v1/auth/change-password", json={"current_password": PASSWORD, "new_password": "Another123abc"})
    assert r.status_code == 200


def test_rate_limit_on_login(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "RATE_LIMIT_AUTH_PER_MINUTE", 3)
    c = make_client(register=False)
    codes = [
        c.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "Whatever123"}).status_code for _ in range(5)
    ]
    assert codes[:3] == [401, 401, 401]
    assert codes[3] == 429


def test_account_delete_and_export(client: Client) -> None:
    client.post("/api/v1/portfolio", json={"title": "Thing", "description": "A description that is long enough."})
    exported = client.get("/api/v1/account/export").json()
    assert exported["account"]["email"] == "alice@example.com"
    assert len(exported["portfolio_projects"]) == 1
    assert "password_hash" not in str(exported)
    assert client.request("DELETE", "/api/v1/account", json={"password": "wrong"}).status_code == 401
    assert client.request("DELETE", "/api/v1/account", json={"password": PASSWORD}).status_code == 200
    assert (
        make_client(register=False)
        .post("/api/v1/auth/login", json={"email": "alice@example.com", "password": PASSWORD})
        .status_code
        == 401
    )
