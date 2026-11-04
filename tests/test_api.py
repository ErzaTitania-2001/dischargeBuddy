import io
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.sample_data import SAMPLE_DISCHARGE_TEXT

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "DischargeBuddy"
    assert "meta_spark_configured" in data

def test_auth_registration_and_isolation():
    reg_res = client.post("/api/auth/register", json={
        "name": "David Miller",
        "email": "david.miller@example.com",
        "password": "securepassword123",
        "preferred_language": "en"
    })
    assert reg_res.status_code == 200
    reg_data = reg_res.json()
    assert "token" in reg_data
    token = reg_data["token"]
    assert reg_data["user"]["name"] == "David Miller"

    docs_res = client.get("/api/user/documents", headers={"Authorization": f"Bearer {token}"})
    assert docs_res.status_code == 200
    assert len(docs_res.json()["documents"]) == 0

    tasks_res = client.get("/api/user/tasks", headers={"Authorization": f"Bearer {token}"})
    assert tasks_res.status_code == 200
    assert len(tasks_res.json()["tasks"]) == 0

def test_auth_duplicate_email_rejected():
    res = client.post("/api/auth/register", json={
        "name": "David Duplicate",
        "email": "david.miller@example.com",
        "password": "password123",
        "preferred_language": "en"
    })
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"]

def test_auth_login_success_and_failure():
    login_res = client.post("/api/auth/login", json={
        "email": "david.miller@example.com",
        "password": "securepassword123"
    })
    assert login_res.status_code == 200
    assert "token" in login_res.json()

    fail_res = client.post("/api/auth/login", json={
        "email": "david.miller@example.com",
        "password": "wrongpassword"
    })
    assert fail_res.status_code == 401

def test_demo_auth():
    demo_res = client.post("/api/auth/demo")
    assert demo_res.status_code == 200
    demo_data = demo_res.json()
    assert demo_data["auth_mode"] == "demo"
    assert demo_data["user"]["is_demo"] is True
    token = demo_data["token"]

    docs_res = client.get("/api/user/documents", headers={"Authorization": f"Bearer {token}"})
    assert docs_res.status_code == 200
    assert len(docs_res.json()["documents"]) >= 1

    tasks_res = client.get("/api/user/tasks", headers={"Authorization": f"Bearer {token}"})
    assert tasks_res.status_code == 200
    assert len(tasks_res.json()["tasks"]) >= 1

def test_document_extract_and_review_flow():
    extract_res = client.post(
        "/api/documents/extract",
        data={"text": SAMPLE_DISCHARGE_TEXT}
    )
    assert extract_res.status_code == 200
    ext_data = extract_res.json()
    assert ext_data["char_count"] > 100
    assert "ST. JUDE" in ext_data["extracted_text"]

    demo_res = client.post("/api/auth/demo")
    token = demo_res.json()["token"]

    analyze_res = client.post(
        "/api/documents/analyze",
        data={
            "text": ext_data["extracted_text"],
            "language": "en",
            "title": "Reviewed Post-Op Knee Summary"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert analyze_res.status_code == 200
    ana_data = analyze_res.json()
    assert "summary" in ana_data
    assert len(ana_data["medication_instructions"]) > 0

def test_task_toggle():
    demo_res = client.post("/api/auth/demo")
    token = demo_res.json()["token"]

    tasks_res = client.get("/api/user/tasks", headers={"Authorization": f"Bearer {token}"})
    tasks = tasks_res.json()["tasks"]
    assert len(tasks) > 0
    first_task = tasks[0]
    initial_completed = first_task["completed"]

    toggle_res = client.post(
        f"/api/user/tasks/{first_task['id']}/toggle",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert toggle_res.status_code == 200
    assert toggle_res.json()["task"]["completed"] != initial_completed

def test_sample_endpoints_multilingual():
    for lang in ["en", "hi", "bn"]:
        res = client.get(f"/api/sample?lang={lang}")
        assert res.status_code == 200
        assert res.json()["language"] == lang

def test_sample_pdf_extract():
    with open("app/static/sample_discharge_summary.pdf", "rb") as f:
        pdf_bytes = f.read()

    res = client.post(
        "/api/documents/extract",
        files={"file": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    )
    assert res.status_code == 200
    assert res.json()["page_count"] >= 1
    assert "ST. JUDE" in res.json()["extracted_text"]

# ========================================================
# TESTS FOR DUPLICATE DETECTION & DOCUMENT REMOVAL
# ========================================================

def test_duplicate_detection_exact_case_and_spacing():
    # Demo user already has 'knee_arthroscopy_discharge.pdf'
    demo_res = client.post("/api/auth/demo")
    token = demo_res.json()["token"]

    # 1. Exact duplicate with different capitalization
    res1 = client.post(
        "/api/documents/check-duplicate",
        json={"filename": "KNEE_ARTHROSCOPY_DISCHARGE.PDF"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["is_duplicate"] is True
    assert d1["duplicate_type"] == "exact"
    assert "already exist" in d1["message"]
    assert d1["existing_filename"] == "knee_arthroscopy_discharge.pdf"

    # 2. Exact duplicate with extra whitespace and hyphens
    res2 = client.post(
        "/api/documents/check-duplicate",
        json={"filename": "  knee - arthroscopy - discharge.pdf  "},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["is_duplicate"] is True
    assert d2["duplicate_type"] == "exact"

def test_duplicate_detection_potential_copy_markers():
    demo_res = client.post("/api/auth/demo")
    token = demo_res.json()["token"]

    # Potential duplicate with (1) suffix
    res = client.post(
        "/api/documents/check-duplicate",
        json={"filename": "knee_arthroscopy_discharge (1).pdf"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    d = res.json()
    assert d["is_duplicate"] is True
    assert d["duplicate_type"] == "potential"
    assert d["existing_filename"] == "knee_arthroscopy_discharge.pdf"

def test_duplicate_detection_different_document():
    demo_res = client.post("/api/auth/demo")
    token = demo_res.json()["token"]

    # Completely different document (e.g. October vs November)
    res = client.post(
        "/api/documents/check-duplicate",
        json={"filename": "Cardiology_Discharge_November.pdf"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    d = res.json()
    assert d["is_duplicate"] is False
    assert d["duplicate_type"] == "none"

def test_document_removal_and_task_cleanup():
    # 1. Register a dedicated test user
    reg = client.post("/api/auth/register", json={
        "name": "Rachel Green",
        "email": "rachel.removal.test@example.com",
        "password": "password123",
        "preferred_language": "en"
    })
    token = reg.json()["token"]

    # 2. Upload and analyze a document
    ana_res = client.post(
        "/api/documents/analyze",
        data={
            "text": SAMPLE_DISCHARGE_TEXT,
            "filename": "Rachel_Knee_Surgery.pdf",
            "title": "Rachel Post-Op Knee"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert ana_res.status_code == 200

    # 3. Check documents & tasks are populated
    docs_before = client.get("/api/user/documents", headers={"Authorization": f"Bearer {token}"}).json()["documents"]
    tasks_before = client.get("/api/user/tasks", headers={"Authorization": f"Bearer {token}"}).json()["tasks"]
    assert len(docs_before) == 1
    assert len(tasks_before) > 0
    doc_id = docs_before[0]["id"]

    # 4. Remove document
    del_res = client.delete(f"/api/user/documents/{doc_id}", headers={"Authorization": f"Bearer {token}"})
    assert del_res.status_code == 200
    del_data = del_res.json()
    assert del_data["success"] is True
    assert del_data["removed_document_id"] == doc_id
    assert del_data["remaining_documents_count"] == 0
    assert del_data["remaining_tasks_count"] == 0

    # 5. Verify documents and tasks lists are now empty
    docs_after = client.get("/api/user/documents", headers={"Authorization": f"Bearer {token}"}).json()["documents"]
    tasks_after = client.get("/api/user/tasks", headers={"Authorization": f"Bearer {token}"}).json()["tasks"]
    assert len(docs_after) == 0
    assert len(tasks_after) == 0

def test_document_removal_user_isolation_and_security():
    # User Bob registers
    reg_bob = client.post("/api/auth/register", json={
        "name": "Bob Patient",
        "email": "bob.patient@example.com",
        "password": "password123",
        "preferred_language": "en"
    })
    token_bob = reg_bob.json()["token"]

    # Bob uploads a document
    ana = client.post(
        "/api/documents/analyze",
        data={"text": SAMPLE_DISCHARGE_TEXT, "filename": "Bob_Surgery.pdf"},
        headers={"Authorization": f"Bearer {token_bob}"}
    )
    bob_docs = client.get("/api/user/documents", headers={"Authorization": f"Bearer {token_bob}"}).json()["documents"]
    bob_doc_id = bob_docs[0]["id"]

    # User Charlie registers
    reg_charlie = client.post("/api/auth/register", json={
        "name": "Charlie Attacker",
        "email": "charlie.attacker@example.com",
        "password": "password123",
        "preferred_language": "en"
    })
    token_charlie = reg_charlie.json()["token"]

    # Charlie attempts to delete Bob's document
    del_unauth = client.delete(
        f"/api/user/documents/{bob_doc_id}",
        headers={"Authorization": f"Bearer {token_charlie}"}
    )
    assert del_unauth.status_code == 404
    assert "does not belong to your account" in del_unauth.json()["detail"]

    # Verify Bob's document is still intact
    bob_docs_still = client.get("/api/user/documents", headers={"Authorization": f"Bearer {token_bob}"}).json()["documents"]
    assert len(bob_docs_still) == 1
    assert bob_docs_still[0]["id"] == bob_doc_id
