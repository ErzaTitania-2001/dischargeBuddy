import uuid
from datetime import datetime, timezone

from app.models import DischargeAnalysisResponse, FollowUpTask
from app.services.auth_service import DocumentRecord, UserStore


def test_account_and_original_document_survive_store_restart(tmp_path):
    database = tmp_path / "care.sqlite3"
    uploads = tmp_path / "uploads"
    original = uploads / "account" / "original.txt"
    original.parent.mkdir(parents=True)
    original.write_text("Discharge instructions retained across restart.", encoding="utf-8")

    first = UserStore(database)
    user, token = first.register("restart@example.test", "password123", "Restart Patient")
    doc = DocumentRecord(
        id=f"doc-{uuid.uuid4().hex}", title="Discharge", filename="original.txt",
        uploaded_at=datetime.now(timezone.utc).isoformat(), raw_text="Discharge instructions retained across restart.",
        status="uploaded", extraction_status="completed", mime_type="text/plain",
        storage_path=str(original), content_sha256="unique-restart-document"
    )
    first.add_document(user.id, doc)

    restarted = UserStore(database)
    assert restarted.get_user_by_token(token).id == user.id
    documents = restarted.get_documents(user.id)
    assert len(documents) == 1
    assert documents[0].raw_text == doc.raw_text
    assert documents[0].storage_path == str(original)
    assert original.read_text(encoding="utf-8") == doc.raw_text


def test_documents_are_isolated_by_account(tmp_path):
    store = UserStore(tmp_path / "isolation.sqlite3")
    alice, _ = store.register("alice@example.test", "password123", "Alice")
    bob, _ = store.register("bob@example.test", "password123", "Bob")
    doc = DocumentRecord(id="doc-alice", title="Alice document", uploaded_at="today", content_sha256="alice-hash")
    store.add_document(alice.id, doc)
    assert store.get_documents(bob.id) == []
    assert store.get_document(bob.id, "doc-alice") is None


def test_all_tasks_from_multiple_documents_and_completion_survive_reprocessing(tmp_path):
    database = tmp_path / "care-tasks.sqlite3"
    store = UserStore(database)
    user, _ = store.register("care@example.test", "password123", "Care Patient")
    first_task = FollowUpTask(id="first-task", title="Walk daily", type="recovery_task")
    first = DocumentRecord(id="doc-one", title="First", uploaded_at="today", content_sha256="first",
        analysis=DischargeAnalysisResponse(summary="First summary", follow_up_tasks=[first_task]))
    store.add_document(user.id, first)
    tasks = store.get_tasks(user.id)
    assert len(tasks) == 1
    task_id = tasks[0].id
    assert store.toggle_task(user.id, task_id).completed is True

    reprocessed = store.get_document(user.id, "doc-one")
    reprocessed.analysis.follow_up_tasks[0].id = "different-model-generated-id"
    store.update_document(user.id, reprocessed)
    second = DocumentRecord(id="doc-two", title="Second", uploaded_at="today", content_sha256="second",
        analysis=DischargeAnalysisResponse(summary="Second summary", follow_up_tasks=[
            FollowUpTask(id="second-task", title="Change dressing", type="recovery_task")
        ]))
    store.add_document(user.id, second)

    restarted = UserStore(database)
    saved_tasks = restarted.get_tasks(user.id)
    assert len(saved_tasks) == 2
    assert next(task for task in saved_tasks if task.title == "Walk daily").completed is True
