from __future__ import annotations

from tests.conftest import PASSWORD, SAMPLE_JOB, SAMPLE_PROFILE, SAMPLE_PROJECT, Client, make_admin, make_client


def _job(client: Client) -> str:
    client.put("/api/v1/profile", json=SAMPLE_PROFILE)
    client.post("/api/v1/portfolio", json=SAMPLE_PROJECT)
    return client.post("/api/v1/jobs", json=SAMPLE_JOB).json()["id"]


def test_generate_edit_version_regenerate(client: Client) -> None:
    jid = _job(client)
    r = client.post("/api/v1/proposals/generate", json={"job_id": jid, "tone": "friendly", "length": "short"})
    assert r.status_code == 201, r.text
    p = r.json()
    assert set(p["sections"]) == {"hook", "solution", "proof", "call_to_action"}
    assert p["content"].startswith(p["sections"]["hook"])
    assert SAMPLE_PROJECT["title"] in p["sections"]["proof"]  # proof cites the user's real project
    assert p["tone"] == "friendly" and p["is_simulated"] is True
    pid = p["id"]

    # Edit + persist (survives "refresh" = new GET).
    edited = p["content"] + "\n\nP.S. Available to start Monday."
    assert client.put(f"/api/v1/proposals/{pid}", json={"content": edited}).status_code == 200
    assert client.get(f"/api/v1/proposals/{pid}").json()["content"] == edited

    v = client.post(f"/api/v1/proposals/{pid}/versions").json()
    assert v["version_number"] == 2 and v["source"] == "manual"

    regen = client.post(f"/api/v1/proposals/{pid}/regenerate", json={"section": "call_to_action"})
    assert regen.status_code == 200, regen.text
    versions = client.get(f"/api/v1/proposals/{pid}/versions").json()
    assert [x["version_number"] for x in versions] == [3, 2, 1]
    assert versions[0]["source"] == "section_regenerated"
    assert versions[-1]["source"] == "generated" and versions[-1]["model"]
    assert versions[-1]["input_tokens"] is not None

    full = client.post(f"/api/v1/proposals/{pid}/regenerate", json={"tone": "technical"}).json()
    assert full["tone"] == "technical" and full["current_version_number"] == 4

    restored = client.post(f"/api/v1/proposals/{pid}/versions/2/restore").json()
    assert restored["content"] == edited

    txt = client.get(f"/api/v1/proposals/{pid}/export", params={"format": "md"})
    assert txt.status_code == 200 and txt.text.startswith("# ")
    assert "attachment" in txt.headers["content-disposition"]

    lst = client.get("/api/v1/proposals").json()
    assert lst["total"] == 1 and lst["items"][0]["job_title"] == SAMPLE_JOB["title"]
    assert client.delete(f"/api/v1/proposals/{pid}").status_code == 200


def test_proposal_without_portfolio_is_honest(client: Client) -> None:
    client.put("/api/v1/profile", json=SAMPLE_PROFILE)
    jid = client.post("/api/v1/jobs", json=SAMPLE_JOB).json()["id"]
    p = client.post("/api/v1/proposals/generate", json={"job_id": jid}).json()
    assert "don't have a closely matching portfolio project" in p["sections"]["proof"]


def test_custom_opening_and_selected_projects(client: Client) -> None:
    jid = _job(client)
    proj = client.get("/api/v1/portfolio").json()["items"][0]["id"]
    p = client.post(
        "/api/v1/proposals/generate",
        json={
            "job_id": jid,
            "custom_opening": "Hi there — I can start this week.",
            "project_ids": [proj],
        },
    ).json()
    assert p["sections"]["hook"].startswith("Hi there — I can start this week.")
    bad = client.post("/api/v1/proposals/generate", json={"job_id": jid, "project_ids": ["00000000-0000-0000-0000-000000000001"]})
    assert bad.status_code == 404


def test_unverified_figures_are_flagged() -> None:
    from app.services.proposal_service import find_unverified_figures

    flagged = find_unverified_figures("I increased revenue by 300% for 12 clients.", '{"years_experience": 12}')
    assert "300%" in flagged and "12" not in flagged


def test_application_tracking(client: Client) -> None:
    jid = _job(client)
    pid = client.post("/api/v1/proposals/generate", json={"job_id": jid}).json()["id"]
    r = client.post("/api/v1/applications", json={"job_id": jid, "proposal_id": pid})
    assert r.status_code == 201, r.text
    app_id = r.json()["id"]
    assert r.json()["proposal_version_number"] == 1
    assert client.post("/api/v1/applications", json={"job_id": jid}).status_code == 409

    for status in ("ready", "sent", "interview"):
        u = client.put(f"/api/v1/applications/{app_id}", json={"status": status})
        assert u.status_code == 200
    a = u.json()
    assert a["status"] == "interview" and a["submitted_at"] is not None
    assert [h["to_status"] for h in a["history"]] == ["interview", "sent", "ready", "draft"]
    assert client.get(f"/api/v1/jobs/{jid}").json()["status"] == "applied"

    u = client.put(f"/api/v1/applications/{app_id}", json={"contract_value": "1500.50", "notes": "Call on Friday"}).json()
    assert u["contract_value"] == "1500.50"
    assert client.get("/api/v1/applications", params={"status": "interview"}).json()["total"] == 1
    assert client.get("/api/v1/applications", params={"q": "friday"}).json()["total"] == 1
    assert client.put(f"/api/v1/applications/{app_id}", json={"status": "won"}).status_code == 422


def test_follow_up_reminder(client: Client) -> None:
    jid = _job(client)
    app_id = client.post("/api/v1/applications", json={"job_id": jid}).json()["id"]
    client.put(f"/api/v1/applications/{app_id}", json={"follow_up_at": "2020-01-01T09:00:00Z"})
    n = client.get("/api/v1/notifications").json()
    assert any(i["type"] == "follow_up" for i in n["items"])
    # Not duplicated on the next poll.
    assert sum(i["type"] == "follow_up" for i in client.get("/api/v1/notifications").json()["items"]) == 1
    assert client.post("/api/v1/notifications/read-all").status_code == 200
    assert client.get("/api/v1/notifications").json()["unread"] == 0


def test_dashboard_reflects_persisted_data(client: Client) -> None:
    empty = client.get("/api/v1/dashboard/summary").json()
    assert empty["total_jobs"] == 0 and empty["average_fit_score"] is None
    jid = _job(client)
    score = client.post(f"/api/v1/jobs/{jid}/analyze").json()["fit_score"]
    pid = client.post("/api/v1/proposals/generate", json={"job_id": jid}).json()["id"]
    aid = client.post("/api/v1/applications", json={"job_id": jid, "proposal_id": pid}).json()["id"]
    client.put(f"/api/v1/applications/{aid}", json={"status": "sent"})
    s = client.get("/api/v1/dashboard/summary").json()
    assert s["total_jobs"] == 1 and s["jobs_analyzed"] == 1 and s["proposals_generated"] == 1
    assert s["proposals_sent"] == 1 and s["interviews"] == 0 and s["hires"] == 0
    assert s["average_fit_score"] == score
    assert s["ai_requests"] > 0
    a = client.get("/api/v1/dashboard/analytics").json()
    assert sum(t["jobs_analyzed"] for t in a["timeline"]) == 1
    assert sum(d["count"] for d in a["fit_score_distribution"]) == 1
    assert {"skill": "react", "count": 1} in a["top_matched_skills"]
    assert next(x for x in a["status_breakdown"] if x["status"] == "sent")["count"] == 1
    act = client.get("/api/v1/dashboard/activity").json()
    assert {e["type"] for e in act} >= {"job_imported", "job_analyzed", "proposal_generated", "status_changed"}


def test_user_data_isolation(client: Client, other_client: Client) -> None:
    jid = _job(client)
    pid = client.post("/api/v1/proposals/generate", json={"job_id": jid}).json()["id"]
    proj = client.get("/api/v1/portfolio").json()["items"][0]["id"]
    aid = client.post("/api/v1/applications", json={"job_id": jid}).json()["id"]

    o = other_client
    for url in (
        f"/api/v1/jobs/{jid}",
        f"/api/v1/proposals/{pid}",
        f"/api/v1/portfolio/{proj}",
        f"/api/v1/applications/{aid}",
        f"/api/v1/proposals/{pid}/versions",
        f"/api/v1/jobs/{jid}/analysis",
    ):
        assert o.get(url).status_code == 404, url
    assert o.put(f"/api/v1/proposals/{pid}", json={"content": "hijack"}).status_code == 404
    assert o.delete(f"/api/v1/jobs/{jid}").status_code == 404
    assert o.post(f"/api/v1/jobs/{jid}/analyze").status_code == 404
    assert o.post("/api/v1/proposals/generate", json={"job_id": jid}).status_code == 404
    assert o.post("/api/v1/applications", json={"job_id": jid}).status_code == 404
    assert o.get("/api/v1/jobs").json()["total"] == 0
    assert o.get("/api/v1/proposals").json()["total"] == 0
    assert o.get("/api/v1/dashboard/summary").json()["total_jobs"] == 0
    # Other user's semantic search never returns Alice's projects.
    o.put("/api/v1/profile", json=SAMPLE_PROFILE)
    ojid = o.post("/api/v1/jobs", json=SAMPLE_JOB).json()["id"]
    assert o.post(f"/api/v1/jobs/{ojid}/match-portfolio").json() == []
    # Other user cannot attach Alice's proposal to their own application.
    r = o.post("/api/v1/applications", json={"job_id": ojid, "proposal_id": pid})
    assert r.status_code == 404
    assert client.get(f"/api/v1/proposals/{pid}").json()["content"] != "hijack"


def test_admin_authorization(client: Client) -> None:
    for url in ("/api/v1/admin/users", "/api/v1/admin/usage", "/api/v1/admin/health", "/api/v1/admin/audit-logs"):
        assert client.get(url).status_code == 403
    assert client.put("/api/v1/admin/scoring-config", json={}).status_code in (403, 422)

    make_client("root@example.com")
    make_admin("root@example.com")
    admin = make_client(register=False)
    r = admin.post("/api/v1/auth/login", json={"email": "root@example.com", "password": PASSWORD})
    admin.csrf = r.json()["csrf_token"]

    users = admin.get("/api/v1/admin/users", params={"q": "alice@"}).json()
    assert users["total"] == 1
    assert "password_hash" not in str(users)
    alice_id = users["items"][0]["id"]

    bad = admin.put(
        "/api/v1/admin/scoring-config",
        json={"skills": 50, "portfolio": 20, "experience": 15, "budget": 15, "scope": 10, "risk": 10},
    )
    assert bad.status_code == 422
    ok = admin.put(
        "/api/v1/admin/scoring-config",
        json={"skills": 40, "portfolio": 20, "experience": 10, "budget": 10, "scope": 10, "risk": 10},
    )
    assert ok.status_code == 200 and ok.json()["weights"]["skills"] == 40

    ai = admin.get("/api/v1/admin/ai-config").json()
    assert "OPENAI_API_KEY" not in str(ai) and "sk-" not in str(ai)
    assert admin.put("/api/v1/admin/usage-limits", json={"daily_ai_requests_per_user": 1}).status_code == 200
    assert admin.get("/api/v1/admin/health").json()["database"]["healthy"] is True
    usage = admin.get("/api/v1/admin/usage").json()
    assert usage["totals"]["users"] == 2

    # Usage limit enforced for Alice (limit 1/day).
    jid = _job(client)
    client.post(f"/api/v1/jobs/{jid}/analyze")
    r = client.post("/api/v1/proposals/generate", json={"job_id": jid})
    assert r.status_code == 429 and r.json()["error"]["code"] == "usage_limit_reached"

    # Deactivate Alice -> her session no longer works; action is audited.
    assert admin.patch(f"/api/v1/admin/users/{alice_id}", json={"is_active": False}).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    logs = admin.get("/api/v1/admin/audit-logs", params={"action": "admin."}).json()
    assert {i["action"] for i in logs["items"]} >= {"admin.user_updated", "admin.scoring_config_updated"}
    # Admin cannot demote themself.
    me = admin.get("/api/v1/auth/me").json()["id"]
    assert admin.patch(f"/api/v1/admin/users/{me}", json={"role": "USER"}).status_code == 400
