import io
import uuid
import os
import tempfile
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
from fastapi.testclient import TestClient

TEST_DATA_DIR = Path(tempfile.gettempdir()) / f"dischargebuddy-tests-{uuid.uuid4().hex}"
os.environ["DATABASE_PATH"] = str(TEST_DATA_DIR / "test.sqlite3")
os.environ["UPLOAD_DIR"] = str(TEST_DATA_DIR / "uploads")
os.environ.pop("DATABASE_URL", None)
from app.main import app
from tests.fixture_data import SAMPLE_DISCHARGE_TEXT, get_sample_discharge_data

client = TestClient(app)

@contextmanager
def mock_muse_spark():
    with patch("app.main.settings.MODEL_API_KEY", "test-key"), patch(
        "app.main.analyze_discharge_text",
        side_effect=lambda text, language="en": get_sample_discharge_data(language)
    ):
        yield

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
    assert "token" not in reg_data
    token = reg_res.cookies.get("db_session")
    assert token
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
    assert "token" not in login_res.json()
    assert login_res.cookies.get("db_session")

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
    token = demo_res.cookies.get("db_session")

    docs_res = client.get("/api/user/documents", headers={"Authorization": f"Bearer {token}"})
    assert docs_res.status_code == 200
    assert len(docs_res.json()["documents"]) == 0

    tasks_res = client.get("/api/user/tasks", headers={"Authorization": f"Bearer {token}"})
    assert tasks_res.status_code == 200
    assert len(tasks_res.json()["tasks"]) == 0

def test_auth_refresh_keeps_a_live_session_and_rejects_revoked_tokens():
    demo_res = client.post("/api/auth/demo")
    token = demo_res.cookies.get("db_session")
    refreshed = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert refreshed.status_code == 200
    assert refreshed.cookies.get("db_session")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    rejected = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert rejected.status_code == 401

def test_auth_refresh_rejects_unknown_token():
    rejected = client.post("/api/auth/refresh", headers={"Authorization": "Bearer sess-expired"})
    assert rejected.status_code == 401

def test_analysis_waits_for_explicit_review_confirmation():
    suffix = uuid.uuid4().hex
    auth = client.post("/api/auth/register", json={
        "name": "Review Patient", "email": f"review-{suffix}@example.test", "password": "password123"
    }).json()
    headers = {"Authorization": f"Bearer {client.cookies.get('db_session')}"}
    with mock_muse_spark():
        pending = client.post("/api/documents/analyze", data={
            "text": SAMPLE_DISCHARGE_TEXT, "confirm": "false"
        }, headers=headers)
    assert pending.status_code == 200
    pending_data = pending.json()
    assert pending_data["review_id"]
    assert len(client.get("/api/user/documents", headers=headers).json()["documents"]) == 1

    confirmed = client.post("/api/user/documents/confirm-review", json={
        "review_id": pending_data["review_id"],
        "additions": [{"section": "Patient note", "value": "Patient-entered note"}]
    }, headers=headers)
    assert confirmed.status_code == 200
    saved = client.get("/api/user/documents", headers=headers).json()["documents"]
    assert len(saved) == 1
    assert "Added by you" in saved[0]["analysis"]["user_added_information"][0]["value"]

def test_document_extract_and_review_flow():
    demo_res = client.post("/api/auth/demo")
    token = demo_res.cookies.get("db_session")
    extract_res = client.post(
        "/api/documents/extract",
        data={"text": SAMPLE_DISCHARGE_TEXT}, headers={"Authorization": f"Bearer {token}"}
    )
    assert extract_res.status_code == 200
    ext_data = extract_res.json()
    assert ext_data["char_count"] > 100
    assert "ST. JUDE" in ext_data["extracted_text"]

    with mock_muse_spark():
        analyze_res = client.post(
            "/api/documents/analyze",
            data={"text": ext_data["extracted_text"], "language": "en", "title": "Reviewed Summary", "document_id": ext_data["document_id"], "confirm": "true"},
            headers={"Authorization": f"Bearer {token}"}
        )
    assert analyze_res.status_code == 200
    ana_data = analyze_res.json()
    assert "summary" in ana_data["analysis"]
    assert len(ana_data["analysis"]["medication_instructions"]) > 0

def test_failed_extraction_keeps_original_and_retryable_record():
    registered = client.post("/api/auth/register", json={
        "name": "Extraction Retry", "email": f"extract-{uuid.uuid4().hex}@example.test", "password": "password123"
    })
    token = registered.cookies.get("db_session")
    headers = {"Authorization": f"Bearer {token}"}
    original_text = "too short"
    failed = client.post("/api/documents/extract", data={"text": original_text}, headers=headers)
    assert failed.status_code == 200
    body = failed.json()
    assert body["extraction_status"] == "failed"
    assert body["document_id"]
    docs = client.get("/api/user/documents", headers=headers).json()["documents"]
    assert len(docs) == 1 and docs[0]["status"] == "failed"
    original = client.get(f"/api/user/documents/{body['document_id']}/file", headers=headers)
    assert original.status_code == 200 and original.content == original_text.encode()
    retried = client.post(f"/api/user/documents/{body['document_id']}/retry-extraction", headers=headers)
    assert retried.status_code == 200
    assert retried.json()["document"]["extraction_status"] == "failed"

def test_task_toggle():
    demo_res = client.post("/api/auth/demo")
    token = demo_res.cookies.get("db_session")

    with mock_muse_spark():
        client.post("/api/documents/analyze", data={"text": SAMPLE_DISCHARGE_TEXT, "confirm": "true"}, headers={"Authorization": f"Bearer {token}"})

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

def test_test_fixture_multilingual_data():
    for lang in ["en", "hi", "bn"]:
        assert get_sample_discharge_data(lang).language == lang

def test_sample_pdf_extract():
    with open("tests/fixtures/sample_discharge_summary.pdf", "rb") as f:
        pdf_bytes = f.read()

    res = client.post(
        "/api/documents/extract",
        files={"file": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        headers={"Authorization": f"Bearer {client.cookies.get('db_session')}"}
    )
    assert res.status_code == 200
    assert res.json()["page_count"] >= 1
    assert "ST. JUDE" in res.json()["extracted_text"]

# ========================================================
# TESTS FOR DUPLICATE DETECTION & DOCUMENT REMOVAL
# ========================================================

def _user_with_document(filename):
    suffix = uuid.uuid4().hex
    response = client.post("/api/auth/register", json={
        "name": "Duplicate Test", "email": f"duplicate-{suffix}@example.test", "password": "password123"
    })
    token = response.cookies.get("db_session")
    with mock_muse_spark():
        saved = client.post("/api/documents/analyze", data={
            "text": SAMPLE_DISCHARGE_TEXT, "filename": filename, "confirm": "true"
        }, headers={"Authorization": f"Bearer {token}"})
    assert saved.status_code == 200
    return token

def test_duplicate_detection_exact_case_and_spacing():
    token = _user_with_document("knee_arthroscopy_discharge.pdf")

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
    token = _user_with_document("knee_arthroscopy_discharge.pdf")

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
    token = _user_with_document("knee_arthroscopy_discharge.pdf")

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
    token = reg.cookies.get("db_session")

    # 2. Upload and analyze a document
    with mock_muse_spark():
        ana_res = client.post(
            "/api/documents/analyze",
            data={"text": SAMPLE_DISCHARGE_TEXT, "filename": "patient-summary.pdf", "confirm": "true"},
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
    token_bob = reg_bob.cookies.get("db_session")

    # Bob uploads a document
    with mock_muse_spark():
        ana = client.post(
            "/api/documents/analyze",
            data={"text": SAMPLE_DISCHARGE_TEXT, "filename": "patient-summary.pdf", "confirm": "true"},
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
    token_charlie = reg_charlie.cookies.get("db_session")

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
