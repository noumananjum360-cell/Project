from __future__ import annotations

import io

from tests.conftest import SAMPLE_PROFILE, SAMPLE_PROJECT, Client


def _docx_bytes(text: str) -> bytes:
    import docx

    d = docx.Document()
    for line in text.splitlines():
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _pdf_bytes(text: str) -> bytes:
    """Build a minimal valid single-page PDF containing ``text``."""
    lines = text.splitlines()
    ops = "BT /F1 11 Tf 50 750 Td 14 TL " + " ".join(f"({ln}) Tj T*" for ln in lines) + " ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(ops)} >>\nstream\n{ops}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{off:010d} 00000 n \n" for off in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


RESUME = "Jane Doe\nSenior Python Developer\nI have 7 years of experience building APIs with FastAPI and Django.\nSkills: Python, FastAPI, PostgreSQL, Docker, React\nLanguages: English, Spanish"


def test_profile_crud(client: Client) -> None:
    p = client.get("/api/v1/profile").json()
    assert p["primary_skills"] == [] and p["profile_version"] == 1
    r = client.put("/api/v1/profile", json=SAMPLE_PROFILE)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["hourly_rate"] == "60.00"
    assert body["primary_skills"] == SAMPLE_PROFILE["primary_skills"]
    assert body["profile_version"] == 2
    assert client.get("/api/v1/profile").json()["headline"] == SAMPLE_PROFILE["headline"]
    assert client.delete("/api/v1/profile").status_code == 200
    assert client.get("/api/v1/profile").json()["primary_skills"] == []


def test_profile_validation(client: Client) -> None:
    r = client.put("/api/v1/profile", json={**SAMPLE_PROFILE, "hourly_rate": "-5", "currency": "dollars"})
    assert r.status_code == 422


def test_preferences(client: Client) -> None:
    assert client.get("/api/v1/profile/preferences").json()["fit_score_threshold"] == 70
    r = client.put(
        "/api/v1/profile/preferences",
        json={
            "fit_score_threshold": 80,
            "auto_analyze_on_import": True,
            "notify_high_fit_jobs": True,
            "notify_follow_ups": False,
        },
    )
    assert r.json()["fit_score_threshold"] == 80


def test_resume_docx_upload_review_apply(client: Client) -> None:
    files = {"file": ("cv.docx", _docx_bytes(RESUME), "application/octet-stream")}
    r = client.post("/api/v1/profile/resume", files=files)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["status"] == "parsed"
    assert data["is_simulated"] is True
    assert data["file_retained"] is False
    extracted = data["extracted_data"]
    assert "fastapi" in extracted["skills"]
    assert extracted["years_experience"] == 7
    assert "unverified" in extracted["verification_note"]
    # Nothing applied yet.
    assert client.get("/api/v1/profile").json()["primary_skills"] == []
    r = client.post("/api/v1/profile/resume/apply", json={"add_primary_skills": ["Python", "FastAPI"], "years_experience": 7})
    assert r.status_code == 200
    assert r.json()["primary_skills"] == ["Python", "FastAPI"]
    assert client.get("/api/v1/profile/resume").json()["status"] == "applied"
    assert client.delete("/api/v1/profile/resume").status_code == 200
    assert client.get("/api/v1/profile/resume").status_code == 404


def test_resume_pdf_upload(client: Client) -> None:
    r = client.post("/api/v1/profile/resume", files={"file": ("cv.pdf", _pdf_bytes(RESUME), "application/pdf")})
    assert r.status_code == 201, r.text
    assert "python" in r.json()["extracted_data"]["skills"]


def test_resume_rejects_invalid_files(client: Client) -> None:
    r = client.post("/api/v1/profile/resume", files={"file": ("cv.pdf", b"not a pdf at all", "application/pdf")})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_file_type"
    r = client.post("/api/v1/profile/resume", files={"file": ("cv.exe", b"MZ....", "application/pdf")})
    assert r.status_code == 400
    broken = b"%PDF-1.4\n garbage without structure"
    r = client.post("/api/v1/profile/resume", files={"file": ("cv.pdf", broken, "application/pdf")})
    assert r.status_code == 400 and r.json()["error"]["code"] == "unreadable_file"


def test_resume_size_limit(client: Client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "MAX_UPLOAD_SIZE_MB", 1)
    big = b"%PDF-1.4\n" + b"0" * (1024 * 1024 + 10)
    r = client.post("/api/v1/profile/resume", files={"file": ("cv.pdf", big, "application/pdf")})
    assert r.status_code == 413


def test_portfolio_crud_and_embeddings(client: Client) -> None:
    r = client.post("/api/v1/portfolio", json=SAMPLE_PROJECT)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["embedding_status"] == "ready"
    pid = p["id"]
    assert client.get(f"/api/v1/portfolio/{pid}").json()["title"] == SAMPLE_PROJECT["title"]

    lst = client.get("/api/v1/portfolio", params={"q": "inventory"}).json()
    assert lst["total"] == 1
    assert client.get("/api/v1/portfolio", params={"skill": "fastapi"}).json()["total"] == 1
    assert client.get("/api/v1/portfolio", params={"q": "nothing-matches"}).json()["total"] == 0

    upd = client.put(f"/api/v1/portfolio/{pid}", json={**SAMPLE_PROJECT, "title": "Updated title"}).json()
    assert upd["title"] == "Updated title"
    assert upd["embedding_status"] == "ready"
    reindex = client.post("/api/v1/portfolio/reindex").json()
    assert reindex == {"indexed": 0, "skipped": 1, "failed": 0}  # unchanged => no duplicate embedding

    assert client.delete(f"/api/v1/portfolio/{pid}").status_code == 200
    assert client.get(f"/api/v1/portfolio/{pid}").status_code == 404


def test_portfolio_validation(client: Client) -> None:
    r = client.post("/api/v1/portfolio", json={**SAMPLE_PROJECT, "url": "javascript:alert(1)"})
    assert r.status_code == 422
