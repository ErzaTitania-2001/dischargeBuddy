import hashlib
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.models import DischargeAnalysisResponse, FollowUpTask
from app.services.auth_service import DocumentRecord, UserStore
from app.services import reminder_service


def _ready_account(store, email="reminder@example.test", enabled=True, verified=True):
    user, _ = store.register(email, "password123", "Reminder Patient")
    token_hash = hashlib.sha256((user.id + "-verify").encode()).hexdigest()
    store.create_email_verification(user.id, token_hash, "2099-01-01T00:00:00+00:00")
    if verified:
        store.verify_email_token(token_hash)
    store.update_profile(user.id, email_notifications_enabled=enabled, timezone_name="Asia/Kolkata")
    return user


def _add_appointment(store, user, doc_id, appointment_id, appointment_date, *, completed=False, cancelled=False, time=None):
    task = FollowUpTask(
        id=appointment_id, title="Follow-up visit", type="appointment", date_time=appointment_date.isoformat(),
        date_sort_key=appointment_date.isoformat(), appointment_time=time, completed=completed, cancelled=cancelled,
        provider="Orthopedics", location="City Clinic"
    )
    analysis = DischargeAnalysisResponse(summary="Follow-up information", follow_up_tasks=[task])
    store.add_document(user.id, DocumentRecord(
        id=doc_id, title=doc_id, filename=f"{doc_id}.txt", uploaded_at="today", raw_text="Saved discharge record",
        status="completed", extraction_status="completed", ai_status="completed", analysis=analysis
    ))


def _enable_email(monkeypatch):
    monkeypatch.setattr(reminder_service.settings, "EMAIL_NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(reminder_service.settings, "BREVO_API_KEY", "test-key")
    monkeypatch.setattr(reminder_service.settings, "BREVO_SENDER_EMAIL", "care@example.test")


def test_three_day_date_only_reminder_is_idempotent_and_contains_no_time(tmp_path, monkeypatch):
    store = UserStore(tmp_path / "reminders.sqlite3")
    user = _ready_account(store)
    _add_appointment(store, user, "doc-date-only", "apt-date-only", date(2026, 11, 8))
    monkeypatch.setattr(reminder_service, "user_store", store)
    _enable_email(monkeypatch)
    sent = []

    def sender(recipient, subject, body_html, body_text):
        sent.append((recipient, subject, body_html, body_text))
        return "provider-id-1"

    now = datetime(2026, 11, 5, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert reminder_service.dispatch_due_reminders(now, sender) == {"status": "completed", "sent": 1, "failed": 0, "skipped": 0}
    assert reminder_service.dispatch_due_reminders(now, sender)["sent"] == 0
    assert len(sent) == 1
    assert sent[0][1] == "Reminder: Your follow-up appointment is in 3 days"
    assert "Time:" not in sent[0][2] and "Time:" not in sent[0][3]
    assert "diagnosis" not in sent[0][2].lower()
    history = store.get_reminder_deliveries(user.id)
    assert len(history) == 1 and history[0]["delivery_status"] == "sent"
    assert history[0]["provider_message_id"] == "provider-id-1"


def test_two_and_four_day_appointments_do_not_send_early(tmp_path, monkeypatch):
    store = UserStore(tmp_path / "range.sqlite3")
    user = _ready_account(store)
    _add_appointment(store, user, "doc-2", "apt-2", date(2026, 11, 7))
    _add_appointment(store, user, "doc-4", "apt-4", date(2026, 11, 9))
    monkeypatch.setattr(reminder_service, "user_store", store)
    _enable_email(monkeypatch)
    calls = []
    result = reminder_service.dispatch_due_reminders(
        datetime(2026, 11, 5, 9, tzinfo=ZoneInfo("Asia/Kolkata")),
        lambda *args: calls.append(args) or "message-id"
    )
    assert result["sent"] == 0 and calls == []


def test_completed_cancelled_disabled_and_unverified_appointments_are_skipped(tmp_path, monkeypatch):
    store = UserStore(tmp_path / "eligibility.sqlite3")
    user = _ready_account(store)
    _add_appointment(store, user, "doc-complete", "apt-complete", date(2026, 11, 8), completed=True)
    _add_appointment(store, user, "doc-cancel", "apt-cancel", date(2026, 11, 8), cancelled=True)
    disabled = _ready_account(store, "disabled@example.test", enabled=False)
    _add_appointment(store, disabled, "doc-disabled", "apt-disabled", date(2026, 11, 8))
    unverified = _ready_account(store, "unverified@example.test", verified=False)
    _add_appointment(store, unverified, "doc-unverified", "apt-unverified", date(2026, 11, 8))
    monkeypatch.setattr(reminder_service, "user_store", store)
    _enable_email(monkeypatch)
    calls = []
    result = reminder_service.dispatch_due_reminders(
        datetime(2026, 11, 5, 9, tzinfo=ZoneInfo("Asia/Kolkata")),
        lambda *args: calls.append(args) or "message-id"
    )
    assert result["sent"] == 0 and calls == []


def test_transient_provider_failure_retries_once_and_persists_attempts(tmp_path, monkeypatch):
    store = UserStore(tmp_path / "retry.sqlite3")
    user = _ready_account(store)
    _add_appointment(store, user, "doc-retry", "apt-retry", date(2026, 11, 8))
    monkeypatch.setattr(reminder_service, "user_store", store)
    _enable_email(monkeypatch)
    attempts = []

    def sender(*args):
        attempts.append(args)
        if len(attempts) == 1:
            raise reminder_service.BrevoDeliveryError("rate limited", retryable=True)
        return "accepted-after-retry"

    result = reminder_service.dispatch_due_reminders(
        datetime(2026, 11, 5, 9, tzinfo=ZoneInfo("Asia/Kolkata")), sender
    )
    assert result["sent"] == 1 and len(attempts) == 2
    delivery = store.get_reminder_deliveries(user.id)[0]
    assert delivery["attempt_count"] == 2 and delivery["delivery_status"] == "sent"


def test_no_send_outside_local_nine_am_and_bad_address_is_recorded(tmp_path, monkeypatch):
    store = UserStore(tmp_path / "safe.sqlite3")
    user = _ready_account(store, email="invalid-address")
    _add_appointment(store, user, "doc-invalid-email", "apt-invalid-email", date(2026, 11, 8))
    monkeypatch.setattr(reminder_service, "user_store", store)
    _enable_email(monkeypatch)
    calls = []
    assert reminder_service.dispatch_due_reminders(
        datetime(2026, 11, 5, 8, 30, tzinfo=ZoneInfo("Asia/Kolkata")), lambda *args: calls.append(args)
    )["skipped"] == 0
    assert reminder_service.dispatch_due_reminders(
        datetime(2026, 11, 5, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata")), lambda *args: calls.append(args)
    )["skipped"] == 1
    assert calls == []
    assert store.get_reminder_deliveries(user.id)[0]["delivery_status"] == "skipped"


def test_global_email_switch_disables_dispatch(tmp_path, monkeypatch):
    store = UserStore(tmp_path / "global-off.sqlite3")
    user = _ready_account(store)
    _add_appointment(store, user, "doc-global-off", "apt-global-off", date(2026, 11, 8))
    monkeypatch.setattr(reminder_service, "user_store", store)
    monkeypatch.setattr(reminder_service.settings, "EMAIL_NOTIFICATIONS_ENABLED", False)
    calls = []
    result = reminder_service.dispatch_due_reminders(
        datetime(2026, 11, 5, 9, tzinfo=ZoneInfo("Asia/Kolkata")), lambda *args: calls.append(args)
    )
    assert result["status"] == "disabled" and calls == []


def test_ambiguous_timeout_is_not_resent_on_scheduler_retry(tmp_path, monkeypatch):
    store = UserStore(tmp_path / "uncertain.sqlite3")
    user = _ready_account(store)
    _add_appointment(store, user, "doc-uncertain", "apt-uncertain", date(2026, 11, 8))
    monkeypatch.setattr(reminder_service, "user_store", store)
    _enable_email(monkeypatch)
    calls = []

    def sender(*args):
        calls.append(args)
        raise TimeoutError("provider response lost")

    now = datetime(2026, 11, 5, 9, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert reminder_service.dispatch_due_reminders(now, sender)["failed"] == 1
    assert reminder_service.dispatch_due_reminders(now, sender)["failed"] == 0
    assert len(calls) == 1
    assert store.get_reminder_deliveries(user.id)[0]["delivery_status"] == "uncertain"
