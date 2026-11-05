import logging
import uuid
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Optional, List
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Header, Cookie, Response, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse

from app.config import settings
from app.models import (
    DischargeAnalysisResponse,
    ExtractedFact,
    TextAnalyzeRequest,
    RegisterRequest,
    LoginRequest,
    ProfileUpdateRequest,
    ExtractResponse,
    FollowUpTask,
    CheckDuplicateRequest,
    CheckDuplicateResponse,
    DeleteDocumentResponse,
    PainEntryRequest,
    HandoverEventRequest,
    ReviewConfirmRequest,
    ConsultationNotesRequest,
    MedicalHistoryExportRequest
)
from app.services.pdf_service import extract_text_from_pdf
from app.services.meta_spark_service import analyze_discharge_text
from app.services.clinical_normalizer import normalize_analysis
from app.services.document_storage import save_original, delete_original, read_original, original_exists
from app.services.auth_service import user_store, User, DocumentRecord
from app.services.duplicate_detector import check_for_duplicate
from app.services.reminder_service import (dispatch_due_reminders, send_brevo_email,
    create_verification_token, verify_email_token)
from app.services.medical_history_pdf import build_medical_history_pdf
from email.utils import parseaddr
from html import escape
from io import BytesIO

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="DischargeBuddy AI - Simplifying hospital discharge summaries for patients"
)

# CORS for local development and cloud integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "db_session", token, max_age=settings.SESSION_TTL_DAYS * 86400,
        httponly=True, secure=settings.COOKIE_SECURE, samesite="lax", path="/api"
    )

def attach_source_document(analysis: DischargeAnalysisResponse, doc_id: str) -> None:
    for item in analysis.medication_instructions:
        item.source_document_id = doc_id
    for item in analysis.follow_up_tasks:
        item.document_id = doc_id
    for item in analysis.source_warning_signs:
        item.source_document_id = doc_id
    for item in analysis.investigations:
        item.source_document_id = doc_id
    for group in (analysis.diagnoses, analysis.allergies, analysis.past_history, analysis.user_added_information):
        for item in group:
            item.source_document_id = doc_id

# Dependency to get current user from session token
async def get_current_user(
    authorization: Optional[str] = Header(None),
    x_session_token: Optional[str] = Header(None),
    session_cookie: Optional[str] = Cookie(None, alias="db_session")
) -> Optional[User]:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ")[1].strip()
    elif x_session_token:
        token = x_session_token.strip()
    elif session_cookie:
        token = session_cookie.strip()

    if not token:
        return None
    return user_store.get_user_by_token(token)

async def require_current_user(user: Optional[User] = Depends(get_current_user)) -> User:
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in or use demo mode."
        )
    return user

# ========================================================
# AUTHENTICATION ENDPOINTS
# ========================================================

@app.post("/api/auth/register")
async def register(payload: RegisterRequest, response: Response):
    """Registers a new user and returns user info + session token."""
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", payload.email.strip()):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    try:
        user, token = user_store.register(
            email=payload.email,
            password=payload.password,
            name=payload.name,
            preferred_language=payload.preferred_language
        )
        _set_session_cookie(response, token)
        return {"user": user, "auth_mode": "cookie-session"}
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

@app.post("/api/auth/login")
async def login(payload: LoginRequest, response: Response):
    """Authenticates existing user with email and password."""
    try:
        user, token = user_store.login(payload.email, payload.password)
        _set_session_cookie(response, token)
        return {"user": user, "auth_mode": "cookie-session"}
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(ve))

@app.post("/api/auth/demo")
async def demo_login(response: Response):
    """Open an empty demonstration account without preloaded clinical records."""
    user, token = user_store.demo_login()
    _set_session_cookie(response, token)
    return {
        "user": user,
        "auth_mode": "demo",
        "demo_notice": "Empty demonstration account; no clinical records are preloaded."
    }

@app.get("/api/auth/me")
async def get_me(user: User = Depends(require_current_user)):
    """Returns profile for currently authenticated user."""
    return {"user": user}

@app.post("/api/auth/refresh")
async def refresh_session(
    response: Response,
    authorization: Optional[str] = Header(None),
    x_session_token: Optional[str] = Header(None),
    session_cookie: Optional[str] = Cookie(None, alias="db_session")
):
    """Validates a still-active session after an authenticated request is rejected."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
    elif x_session_token:
        token = x_session_token.strip()
    elif session_cookie:
        token = session_cookie.strip()
    user, refreshed_token = user_store.refresh_session(token)
    if not user or not refreshed_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired. Please sign in again.")
    _set_session_cookie(response, refreshed_token)
    return {"user": user}

@app.post("/api/auth/logout")
async def logout(
    response: Response,
    authorization: Optional[str] = Header(None),
    x_session_token: Optional[str] = Header(None),
    session_cookie: Optional[str] = Cookie(None, alias="db_session")
):
    """Logs out user and invalidates session token."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ")[1].strip()
    elif x_session_token:
        token = x_session_token.strip()
    elif session_cookie:
        token = session_cookie.strip()

    if token:
        user_store.logout(token)
    response.delete_cookie("db_session", path="/api", httponly=True, secure=settings.COOKIE_SECURE, samesite="lax")
    return {"message": "Logged out successfully"}

@app.put("/api/user/profile")
async def update_profile(
    payload: ProfileUpdateRequest,
    user: User = Depends(require_current_user)
):
    """Updates user display name or preferred language."""
    if payload.timezone:
        try:
            ZoneInfo(payload.timezone)
        except ZoneInfoNotFoundError:
            raise HTTPException(status_code=400, detail="Choose a valid IANA timezone.")
    updated = user_store.update_profile(user.id, name=payload.name, preferred_language=payload.preferred_language,
        email_notifications_enabled=payload.email_notifications_enabled, timezone_name=payload.timezone)
    return {"user": updated}

@app.post("/api/auth/email-verification")
async def request_email_verification(user: User = Depends(require_current_user)):
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", user.email or ""):
        raise HTTPException(status_code=400, detail="Add a usable email address before verifying it.")
    if user.email_verified:
        return {"message": "Email address is already verified."}
    token = create_verification_token(user)
    link = f"{settings.APP_BASE_URL}/api/auth/email-verification/confirm?token={quote(token)}"
    try:
        send_brevo_email(user.email, "Verify your DischargeBuddy email address",
            f"<p>Use this link within 24 hours to verify your email address and enable appointment reminders:</p><p><a href=\"{link}\">Verify email address</a></p>",
            f"Use this link within 24 hours to verify your email address and enable appointment reminders:\n{link}")
    except Exception:
        logger.exception("Unable to send email verification message for user %s", user.id)
        raise HTTPException(status_code=503, detail="Verification email could not be sent. Check email settings and try again.")
    return {"message": "Verification email sent. Check your inbox and follow the link within 24 hours."}

@app.get("/api/auth/email-verification/confirm")
async def confirm_email_verification(token: str):
    verified = verify_email_token(token)
    if not verified:
        raise HTTPException(status_code=400, detail="Verification link is invalid, expired, or already used.")
    return RedirectResponse(url=f"{settings.APP_BASE_URL}/?email_verified=1", status_code=303)

# ========================================================
# USER DOCUMENTS & CARE TASKS ENDPOINTS
# ========================================================

@app.get("/api/user/documents")
async def get_user_documents(user: User = Depends(require_current_user)):
    """Returns list of documents belonging strictly to the authenticated user."""
    docs = user_store.get_documents(user.id)
    return {"documents": docs}

@app.delete("/api/user/documents/{doc_id}", response_model=DeleteDocumentResponse)
async def delete_user_document(doc_id: str, user: User = Depends(require_current_user)):
    """
    Removes a discharge document belonging to the authenticated user.
    Cleans up any care tasks exclusively owned by that document.
    Enforces user ownership and authorization.
    """
    doc = user_store.get_document(user.id, doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or does not belong to your account."
        )
    
    success, rem_docs, rem_tasks, storage_path = user_store.remove_document(user.id, doc_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove document. Please try again."
        )
    if storage_path:
        delete_original(storage_path)
    
    return DeleteDocumentResponse(
        success=True,
        message=f"Document '{doc.filename or doc.title}' removed successfully.",
        removed_document_id=doc_id,
        remaining_documents_count=rem_docs,
        remaining_tasks_count=rem_tasks
    )

@app.get("/api/user/documents/{doc_id}/file")
async def download_user_document(doc_id: str, user: User = Depends(require_current_user)):
    document = user_store.get_document(user.id, doc_id)
    if not document or not document.storage_path or not original_exists(document.storage_path):
        raise HTTPException(status_code=404, detail="Original file not found in this account.")
    if document.storage_path.startswith("gs://"):
        from fastapi.responses import Response as RawResponse
        return RawResponse(content=read_original(document.storage_path), media_type=document.mime_type or "application/octet-stream",
                           headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(Path(document.filename or 'discharge-document').name)}"})
    return FileResponse(path=document.storage_path, media_type=document.mime_type or "application/octet-stream",
                        filename=document.filename or "discharge-document")

@app.get("/api/user/summaries")
async def get_user_summaries(user: User = Depends(require_current_user)):
    return {"summaries": [{"document_id": doc.id, "filename": doc.filename, "analysis": doc.analysis}
                           for doc in user_store.get_documents(user.id) if doc.analysis]}

@app.get("/api/user/medicines")
async def get_user_medicines(user: User = Depends(require_current_user)):
    return {"medicines": [{**medicine.model_dump(), "document_id": doc.id, "document_filename": doc.filename}
                           for doc in user_store.get_documents(user.id) if doc.analysis
                           for medicine in doc.analysis.medication_instructions]}

@app.get("/api/user/appointments")
async def get_user_appointments(user: User = Depends(require_current_user)):
    return {"appointments": [task for task in user_store.get_tasks(user.id) if task.type == "appointment"]}

@app.get("/api/user/reminders")
async def get_user_reminders(user: User = Depends(require_current_user)):
    return {"deliveries": user_store.get_reminder_deliveries(user.id)}

@app.get("/api/user/upload-confirmations")
async def get_upload_confirmation_history(user: User = Depends(require_current_user)):
    return {"deliveries": user_store.get_upload_confirmation_deliveries(user.id)}

@app.post("/api/internal/notifications/dispatch")
def dispatch_scheduled_notifications(authorization: Optional[str] = Header(None)):
    """Cloud Scheduler OIDC endpoint; only the configured service account may invoke it."""
    if not settings.SCHEDULER_SERVICE_ACCOUNT_EMAIL:
        raise HTTPException(status_code=503, detail="Scheduler service account is not configured.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Scheduler OIDC token required.")
    try:
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2 import id_token
        claims = id_token.verify_oauth2_token(authorization.split(" ", 1)[1], GoogleRequest(), audience=settings.APP_BASE_URL)
        if claims.get("email") != settings.SCHEDULER_SERVICE_ACCOUNT_EMAIL or not claims.get("email_verified"):
            raise ValueError("Unexpected scheduler identity")
    except Exception as error:
        logger.warning("Rejected notification scheduler invocation: %s", error)
        raise HTTPException(status_code=401, detail="Invalid scheduler identity.")
    if not settings.EMAIL_NOTIFICATIONS_ENABLED:
        return {"status": "disabled", "sent": 0, "failed": 0, "skipped": 0}
    try:
        return dispatch_due_reminders()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))

@app.post("/api/documents/check-duplicate", response_model=CheckDuplicateResponse)
async def check_duplicate_document(
    payload: CheckDuplicateRequest,
    user: User = Depends(require_current_user)
):
    """
    Checks candidate filename against the authenticated user's existing documents.
    Detects exact duplicates and potential duplicates with normalized comparison.
    """
    user_docs = user_store.get_documents(user.id)
    result = check_for_duplicate(payload.filename, user_docs)
    return CheckDuplicateResponse(
        is_duplicate=result.is_duplicate,
        duplicate_type=result.duplicate_type,
        message=result.message,
        existing_document_id=result.existing_document_id,
        existing_filename=result.existing_filename,
        existing_upload_date=result.existing_upload_date
    )

@app.get("/api/user/tasks")
async def get_user_tasks(user: User = Depends(require_current_user)):
    """Returns follow-up care tasks and appointments for the authenticated user."""
    tasks = user_store.get_tasks(user.id)
    return {"tasks": tasks}

@app.post("/api/user/tasks/{task_id}/toggle")
async def toggle_task_status(task_id: str, user: User = Depends(require_current_user)):
    """Toggles completion state of a user's task."""
    updated = user_store.toggle_task(user.id, task_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": updated, "tasks": user_store.get_tasks(user.id)}

@app.get("/api/user/tracker/pain")
async def get_pain_entries(user: User = Depends(require_current_user)):
    return {"entries": user_store.get_pain_entries(user.id)}

@app.post("/api/user/tracker/pain")
async def save_pain_entry(payload: PainEntryRequest, user: User = Depends(require_current_user)):
    entry = user_store.add_pain_entry(user.id, payload.score, payload.note)
    return {"entry": entry, "entries": user_store.get_pain_entries(user.id)}

@app.get("/api/user/handover/history")
async def get_handover_history(user: User = Depends(require_current_user)):
    return {"events": user_store.get_handover_events(user.id)}

@app.post("/api/user/handover/history")
async def save_handover_event(payload: HandoverEventRequest, user: User = Depends(require_current_user)):
    event = user_store.add_handover_event(user.id, payload.model_dump())
    return {"event": event, "events": user_store.get_handover_events(user.id)}


def _medical_history_payload(user: User, consultation_id: str = "upcoming") -> dict:
    documents = user_store.get_documents(user.id)
    completed = [doc for doc in documents if doc.analysis]
    tasks = user_store.get_tasks(user.id)
    notes = user_store.get_consultation_notes(user.id, consultation_id)
    previous_consultation_notes = [event for event in user_store.get_handover_events(user.id) if event.get("kind") == "visit" and event.get("notes")]
    documents_by_id = {doc.id: doc for doc in completed}
    patient_names, clinicians = [], []
    history, medicines, care, investigations, allergies = [], [], [], [], []
    for doc in completed:
        analysis = doc.analysis
        metadata = analysis.patient_info
        if metadata.patient_name and "not specified" not in metadata.patient_name.lower() and metadata.patient_name not in patient_names:
            patient_names.append(metadata.patient_name)
        if metadata.attending_physician and "not specified" not in metadata.attending_physician.lower() and metadata.attending_physician not in clinicians:
            clinicians.append(metadata.attending_physician)
        facts = [fact.value for fact in (analysis.diagnoses or []) + (analysis.past_history or [])]
        details = [analysis.summary]
        if analysis.hospital_course:
            details.append(f"Hospital course: {analysis.hospital_course}")
        if facts:
            details.append("Documented diagnoses / history: " + "; ".join(dict.fromkeys(facts)))
        patient_added = [fact.value for fact in analysis.user_added_information]
        if patient_added:
            details.append("Patient/caregiver-entered during document review (not clinician findings): " + "; ".join(patient_added))
        details.append(f"Hospital: {metadata.hospital_name}; discharge date: {metadata.discharge_date}; attending: {metadata.attending_physician}")
        details.append(f"Admission: {metadata.admission_date}; reason: {metadata.admission_reason}")
        details.append(f"Procedure / diagnosis: {metadata.procedure_or_diagnosis}")
        for instruction in analysis.recovery_milestones:
            details.append(f"Discharge instruction: {instruction}")
        source = f"{doc.filename or doc.title} · {metadata.discharge_date} · Document ID {doc.id}"
        history.append({"date": metadata.discharge_date, "heading": metadata.procedure_or_diagnosis or "Hospital discharge", "details": "\n".join(details), "source": source})
        if analysis.allergies:
            allergies.extend([[fact.value, fact.state, f"{doc.filename or doc.title} · {metadata.discharge_date}" + (f" · {', '.join(fact.source_references)}" if fact.source_references else "")] for fact in analysis.allergies])
        elif analysis.allergy_status == "none_reported":
            allergies.append(["No allergies reported in this document", "Source reports none", f"{doc.filename or doc.title} · {metadata.discharge_date}"])
        else:
            allergies.append(["Not recorded in this document", "Unknown; not evidence of no allergies", f"{doc.filename or doc.title} · {metadata.discharge_date}"])
        for med in analysis.medication_instructions:
            status_text = (med.continuation_status or "").strip()
            low = status_text.lower()
            if any(word in low for word in ("discontinued", "stop", "ceased")):
                verification = "Discontinued per source" + (f" · {med.state}" if med.state != "stated" else "")
            elif any(word in low for word in ("current", "continue", "ongoing", "active")):
                verification = "Current per source" + (f" · {med.state}" if med.state != "stated" else "")
            elif any(word in low for word in ("historical", "previous", "past medicine")):
                verification = "Historical per source; verify whether still active" + (f" · {med.state}" if med.state != "stated" else "")
            else:
                verification = "Historical / continuation unclear; verify" + (f" · {med.state}" if med.state != "stated" else "")
            instructions = "; ".join(part for part in [med.dosage, med.frequency, med.when_to_take,
                med.route, med.duration, f"PRN: {med.frequency or 'frequency not recorded'}" if med.frequency_type == "as_needed" else None,
                f"Maximum: {med.maximum_limit}" if med.maximum_limit else None] if part) or "Instructions not recorded"
            incomplete = [field.replace("_", " ") for field in ("name", "dosage", "route", "frequency", "when_to_take", "duration")
                          if not getattr(med, field) or med.field_states.get(field) != "stated"]
            if med.conflicts or med.state in ("ambiguous", "conflicting") or incomplete:
                verification += " · Verify" + (f"; incomplete: {', '.join(incomplete)}" if incomplete else "")
                verification += (f"; conflict: {'; '.join(med.conflicts)}" if med.conflicts else "")
            medicines.append([med.name or "Not recorded", instructions, verification,
                              f"{doc.filename or doc.title} · {metadata.discharge_date}" + (f" · {', '.join(med.source_references)}" if med.source_references else "")])
        for item in analysis.recovery_milestones:
            care.append(f"{item} (source: {doc.filename or doc.title})")
        for warning in analysis.source_warning_signs:
            care.append(f"Warning sign from source: {warning.sign}" + (f" — Action: {warning.action}" if warning.action else "") + f" (source: {doc.filename or doc.title})")
        for investigation in analysis.investigations:
            investigations.append([investigation.name or "Investigation name not recorded", investigation.date or "Not recorded",
                                   investigation.result or "Result not recorded",
                                   f"{doc.filename or doc.title} · {metadata.discharge_date}" + (f" · {', '.join(investigation.source_references)}" if investigation.source_references else "")])
    # Sort only dates that are explicitly parseable; do not guess ambiguous date formats.
    def chronology_key(value: str):
        for pattern in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
            try:
                return (0, datetime.strptime(value.strip(), pattern).date().isoformat())
            except (ValueError, AttributeError):
                pass
        return (1, str(value or ""))
    history.sort(key=lambda item: chronology_key(item["date"]))
    medicine_groups = {}
    for row in medicines:
        medicine_groups.setdefault(re.sub(r"\s+", " ", row[0].casefold()).strip(), []).append(row)
    for group in medicine_groups.values():
        if len(group) > 1:
            instructions_differ = len({row[1].casefold() for row in group}) > 1
            warning = "Conflicting medication instructions across records; verify" if instructions_differ else "Listed in multiple records; verify whether duplicate or ongoing"
            for row in group:
                row[2] += " · " + warning
    appointments = []
    for task in tasks:
        if task.type != "appointment":
            if not task.completed:
                care.append(f"Outstanding care task: {task.title}")
            continue
        source_doc = documents_by_id.get(task.document_id or "")
        source = f"{source_doc.filename or source_doc.title} · {source_doc.analysis.patient_info.discharge_date}" if source_doc else "Source document unavailable"
        if task.source_references:
            source += " · " + ", ".join(task.source_references)
        appointments.append([task.date_time or "Date not recorded", task.title,
                             " · ".join(value for value in [task.provider, task.location] if value) or "Not recorded",
                             source + (" · Completed" if task.completed else "")])
    appointments.sort(key=lambda row: chronology_key(row[0]))
    sources = [{"filename": doc.filename or doc.title, "title": doc.title, "uploaded_at": doc.uploaded_at, "status": doc.status} for doc in documents]
    return {
        "patient": {"Full name": "; ".join(patient_names) if patient_names else "Not recorded",
                    "Age / date of birth": "; ".join(dict.fromkeys(doc.analysis.patient_info.age_or_date_of_birth for doc in completed if "not specified" not in doc.analysis.patient_info.age_or_date_of_birth.lower())) or "Not recorded",
                    "Sex": "; ".join(dict.fromkeys(doc.analysis.patient_info.sex for doc in completed if "not specified" not in doc.analysis.patient_info.sex.lower())) or "Not recorded",
                    "Contact": "Not recorded", "Patient ID": "; ".join(dict.fromkeys(doc.analysis.patient_info.record_number for doc in completed if "not specified" not in doc.analysis.patient_info.record_number.lower())) or "Not recorded",
                    "Treating doctor / specialists": "; ".join(clinicians) if clinicians else "Not recorded"},
        "history": history, "allergies": allergies, "medications": medicines, "appointments": appointments,
        "care": list(dict.fromkeys(care)), "investigations": investigations, "sources": sources,
        "notes": notes, "previous_consultation_notes": previous_consultation_notes,
    }


def _send_upload_appointment_email(user: User, document: DocumentRecord) -> None:
    """Send a generic, idempotent upload confirmation after extracted data is saved."""
    if (not settings.EMAIL_NOTIFICATIONS_ENABLED or not user.email_notifications_enabled or not user.email_verified
            or not document.analysis):
        return
    recipient = parseaddr(user.email)[1]
    if not recipient or recipient.lower() != user.email.strip().lower() or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", recipient):
        logger.info("Skipping upload appointment email for account %s: invalid email", user.account_id)
        return
    try:
        zone = ZoneInfo(user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = timezone.utc
    today = datetime.now(zone).date()
    future = []
    for task in user_store.get_tasks(user.id):
        if task.document_id != document.id or task.type != "appointment" or task.completed or task.cancelled:
            continue
        date_value = task.date_sort_key
        try:
            appointment_date = datetime.strptime(date_value, "%Y-%m-%d").date() if date_value else None
        except ValueError:
            appointment_date = None
        if appointment_date and appointment_date >= today:
            future.append((appointment_date, task))
    if not future:
        return
    _, appointment = min(future, key=lambda item: (item[0], item[1].appointment_time or ""))
    claim = user_store.claim_upload_confirmation(user.account_id, document.id, appointment.id, recipient)
    if not claim:
        return
    date_text = appointment.date_time or appointment.date_sort_key or "Date not specified"
    time_text = appointment.appointment_time or appointment.time_of_day
    provider_text = appointment.provider or "Not specified"
    clinic_text = appointment.location or "Not specified"
    text_body = ("Hello,\n\nYour discharge document has been successfully uploaded to DischargeBuddy.\n\n"
                 "Your next scheduled follow-up appointment is:\n\n"
                 f"Date: {date_text}\n" + (f"Time: {time_text}\n" if time_text else "") +
                 f"Doctor / Department: {provider_text}\nHospital / Clinic: {clinic_text}\n\n"
                 f"You can access your saved medical records and care plan through {settings.APP_BASE_URL}.\n\n"
                 "Please review your appointment details and contact your healthcare provider if anything needs clarification.\n\nRegards,\nDischargeBuddy")
    html_body = "<p>Hello,</p><p>Your discharge document has been successfully uploaded to DischargeBuddy.</p>" \
        "<p>Your next scheduled follow-up appointment is:</p><ul>" \
        f"<li>Date: {escape(date_text)}</li>" + (f"<li>Time: {escape(time_text)}</li>" if time_text else "") + \
        f"<li>Doctor / Department: {escape(provider_text)}</li><li>Hospital / Clinic: {escape(clinic_text)}</li></ul>" \
        f"<p>You can access your saved medical records and care plan through <a href=\"{escape(settings.APP_BASE_URL, quote=True)}\">DischargeBuddy</a>.</p>" \
        "<p>Please review your appointment details and contact your healthcare provider if anything needs clarification.</p><p>Regards,<br>DischargeBuddy</p>"
    try:
        send_brevo_email(recipient, "Your next follow-up appointment — DischargeBuddy", html_body, text_body,
                         idempotency_key=claim["id"])
        user_store.finish_upload_confirmation(claim["id"], "sent")
    except Exception as error:
        logger.warning("Upload appointment email delivery failed for document %s: %s", document.id, error)
        user_store.finish_upload_confirmation(claim["id"], "failed", str(error)[:500])


@app.get("/api/user/medical-history")
async def get_medical_history(consultation_id: str = "upcoming", user: User = Depends(require_current_user)):
    return {"history": _medical_history_payload(user, consultation_id)}


@app.put("/api/user/consultation-notes")
async def save_consultation_notes(payload: ConsultationNotesRequest, user: User = Depends(require_current_user)):
    consultation_id = payload.consultation_id.strip() or "upcoming"
    notes = payload.model_dump(exclude={"consultation_id"})
    notes["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        saved = user_store.save_consultation_notes(user.id, consultation_id, notes)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
    return {"consultation_id": consultation_id, "notes": saved}


@app.post("/api/user/medical-history/export")
async def export_medical_history(payload: MedicalHistoryExportRequest, user: User = Depends(require_current_user)):
    if not payload.reviewed:
        raise HTTPException(status_code=400, detail="Review and confirm the selected medical information before exporting.")
    allowed = {"patient", "history", "allergies", "medications", "followups", "care", "consultation", "investigations", "sources"}
    sections = list(dict.fromkeys(section for section in payload.sections if section in allowed))
    if not sections:
        raise HTTPException(status_code=400, detail="Select at least one section to include.")
    pdf = build_medical_history_pdf(_medical_history_payload(user, payload.consultation_id), sections)
    export_id = user_store.record_medical_export(user.id, sections, payload.consultation_id, pdf)
    headers = {"Content-Disposition": f'attachment; filename="DischargeBuddy-Medical-History-{export_id[-12:]}.pdf"',
               "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    return StreamingResponse(BytesIO(pdf), media_type="application/pdf", headers=headers)


@app.get("/api/user/medical-history/exports")
async def list_medical_history_exports(user: User = Depends(require_current_user)):
    return {"exports": user_store.get_medical_exports(user.id)}


@app.get("/api/user/medical-history/exports/{export_id}")
async def download_saved_medical_history_export(export_id: str, user: User = Depends(require_current_user)):
    export = user_store.get_medical_export(user.id, export_id)
    if not export:
        raise HTTPException(status_code=404, detail="Medical history export not found in this account.")
    if not export.get("pdf_data"):
        raise HTTPException(status_code=410, detail="The saved PDF is unavailable. Generate a new export from the current records.")
    return StreamingResponse(BytesIO(export["pdf_data"]), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="DischargeBuddy-Medical-History-{export_id[-12:]}.pdf"',
                 "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

# ========================================================
# UPLOAD, EXTRACTION & REVIEW PIPELINE
# ========================================================

@app.post("/api/documents/extract", response_model=ExtractResponse)
async def extract_document_text(
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    user: User = Depends(require_current_user)
):
    """
    Step 1 of Document Workflow:
    Extracts text from PDF or validates pasted text, returning raw text
    for user review and editing BEFORE sending to AI.
    Also checks for duplicate documents for the current user.
    """
    filename = file.filename if file and file.filename else "pasted_discharge_summary.txt"
    if file and file.filename:
        suffix = Path(filename).suffix.lower()
        if suffix not in (".pdf", ".txt", ".md"):
            raise HTTPException(status_code=400, detail="Unsupported format. Upload a PDF or text file.")
        content = await file.read(settings.MAX_UPLOAD_BYTES + 1)
    elif text and text.strip():
        content = text.strip().encode("utf-8")
        filename = "pasted_discharge_summary.txt"
    else:
        raise HTTPException(status_code=400, detail="Please select a PDF or text file, or paste discharge summary text.")
    if len(content) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The file exceeds the configured upload size limit.")
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")

    import hashlib
    content_hash = hashlib.sha256(content).hexdigest()
    duplicate = user_store.find_document_by_hash(user.id, content_hash)
    if duplicate:
        return ExtractResponse(
            extracted_text=duplicate.raw_text, page_count=0, char_count=len(duplicate.raw_text),
            filename=duplicate.filename, is_duplicate=True, duplicate_type="exact",
            duplicate_message="This file is already saved in your account.", existing_document_id=duplicate.id,
            existing_filename=duplicate.filename, document_id=duplicate.id, processing_status=duplicate.status,
            extraction_status=duplicate.extraction_status, error_detail=duplicate.error_detail
        )

    try:
        storage_path, stored_hash, mime_type = save_original(user.account_id, filename, content)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception:
        logger.exception("Could not store original document")
        raise HTTPException(status_code=503, detail="Original document storage is unavailable. Please retry.")
    created_at = datetime.now(timezone.utc)
    record = DocumentRecord(
        id=f"doc-{uuid.uuid4().hex}", title=Path(filename).stem or "Discharge Document",
        filename=filename, uploaded_at=created_at.strftime("%b %d, %Y • %I:%M %p"), raw_text="",
        status="uploaded", extraction_status="pending", ai_status="pending",
        mime_type=mime_type, storage_path=str(storage_path), content_sha256=stored_hash
    )
    try:
        saved, inserted = user_store.add_document(user.id, record)
    except Exception:
        delete_original(str(storage_path))
        logger.exception("Could not create uploaded document record")
        raise HTTPException(status_code=503, detail="The original file could not be registered. Please retry.")
    if not inserted:
        delete_original(str(storage_path))
        return ExtractResponse(
            extracted_text=saved.raw_text, page_count=0, char_count=len(saved.raw_text), filename=saved.filename,
            is_duplicate=True, duplicate_type="exact", duplicate_message="This file is already saved in your account.",
            existing_document_id=saved.id, existing_filename=saved.filename, document_id=saved.id,
            processing_status=saved.status, extraction_status=saved.extraction_status, error_detail=saved.error_detail
        )

    try:
        if Path(filename).suffix.lower() == ".pdf":
            extracted_text, page_count = extract_text_from_pdf(content)
        else:
            extracted_text, page_count = content.decode("utf-8", errors="replace"), 1
        if len(extracted_text.strip()) < 20:
            raise ValueError("Extracted text is too short to be a discharge summary. Please check the original document.")
        saved.raw_text = extracted_text
        saved.extraction_status = "completed"
        saved.status = "uploaded"
        saved.error_detail = None
    except Exception as error:
        logger.info("Text extraction failed for document %s: %s", saved.id, error)
        extracted_text, page_count = "", 0
        saved.status = "failed"
        saved.extraction_status = "failed"
        saved.error_detail = str(error) or "Text extraction failed. Retry from Documents & Intake."
    user_store.update_document(user.id, saved)
    return ExtractResponse(
        extracted_text=extracted_text, page_count=page_count, char_count=len(extracted_text), filename=filename,
        document_id=saved.id, processing_status=saved.status, extraction_status=saved.extraction_status,
        error_detail=saved.error_detail
    )

@app.post("/api/documents/analyze")
async def analyze_and_save_document(
    text: str = Form(...),
    language: str = Form("en"),
    title: Optional[str] = Form(None),
    filename: Optional[str] = Form(None),
    document_id: Optional[str] = Form(None),
    confirm: bool = Form(False),
    user: User = Depends(require_current_user)
):
    """
    Step 2 of Document Workflow:
    Receives reviewed & confirmed text from user, runs AI structured explanation,
    and attaches to user session if authenticated.
    """
    if len(text.strip()) < 20:
        raise HTTPException(status_code=400, detail="Text is too short to analyze.")

    lang_code = language.strip().lower()
    if lang_code not in ["en", "hi", "bn"]:
        lang_code = "en"

    record = user_store.get_document(user.id, document_id) if document_id else None
    if document_id and not record:
        raise HTTPException(status_code=404, detail="Document not found in this account.")
    if not record:
        record = _persist_text_document(user, text, filename or "pasted_discharge_summary.txt")
    record.raw_text = text
    record.status = "processing"
    record.ai_status = "processing"
    record.error_detail = None
    user_store.update_document(user.id, record)
    return await _process_document_record(user, record, lang_code, confirm)


def _persist_text_document(user: User, text: str, filename: str) -> DocumentRecord:
    import hashlib
    content = text.encode("utf-8")
    content_hash = hashlib.sha256(content).hexdigest()
    existing = user_store.find_document_by_hash(user.id, content_hash)
    if existing:
        return existing
    safe_filename = filename if Path(filename).suffix.lower() in (".pdf", ".txt", ".md") else "pasted_discharge_summary.txt"
    storage_path, content_hash, mime_type = save_original(user.account_id, safe_filename, content)
    record = DocumentRecord(
        id=f"doc-{uuid.uuid4().hex}", title=Path(filename).stem or "Discharge Document", filename=filename,
        uploaded_at=datetime.now(timezone.utc).strftime("%b %d, %Y • %I:%M %p"), raw_text=text,
        status="uploaded", extraction_status="completed", ai_status="pending", mime_type=mime_type,
        storage_path=str(storage_path), content_sha256=content_hash
    )
    try:
        saved, inserted = user_store.add_document(user.id, record)
    except Exception:
        delete_original(storage_path)
        raise
    if not inserted:
        delete_original(storage_path)
    return saved


async def _process_document_record(user: User, record: DocumentRecord, language: str, confirm: bool):
    if not settings.MODEL_API_KEY.strip():
        record.status, record.ai_status = "failed", "failed"
        record.error_detail = "Meta Muse Spark is not configured. Add MODEL_API_KEY before analyzing this document."
        user_store.update_document(user.id, record)
        raise HTTPException(status_code=503, detail=record.error_detail)
    try:
        analysis = normalize_analysis(analyze_discharge_text(record.raw_text, language=language))
    except Exception:
        logger.exception("Muse Spark analysis failed for document %s", record.id)
        record.status, record.ai_status = "failed", "failed"
        record.error_detail = "AI extraction failed. The uploaded original is retained; retry processing when service is available."
        user_store.update_document(user.id, record)
        raise HTTPException(status_code=502, detail=record.error_detail)
    attach_source_document(analysis, record.id)
    if confirm:
        record.analysis = analysis
        record.pending_analysis = None
        record.pending_review_id = None
        record.status, record.ai_status = "completed", "completed"
        record.error_detail = None
        saved = user_store.update_document(user.id, record)
        if saved:
            _send_upload_appointment_email(user, saved)
        return {"document_id": record.id, "processing_status": "completed", "analysis": analysis, "document": saved}
    review_id = user_store.add_pending_review(user.id, {
        "analysis": analysis.model_dump(), "raw_text": record.raw_text,
        "filename": record.filename, "title": record.title, "document_id": record.id
    })
    record.pending_analysis = analysis
    record.pending_review_id = review_id
    record.status, record.ai_status = "reviewing", "reviewing"
    user_store.update_document(user.id, record)
    return {"review_id": review_id, "document_id": record.id, "processing_status": "reviewing", "analysis": analysis}


@app.post("/api/user/documents/{doc_id}/retry-analysis")
async def retry_document_analysis(doc_id: str, user: User = Depends(require_current_user)):
    record = user_store.get_document(user.id, doc_id)
    if not record:
        raise HTTPException(status_code=404, detail="Document not found in this account.")
    if record.extraction_status != "completed" or not record.raw_text:
        raise HTTPException(status_code=409, detail="Retry extraction before AI processing.")
    record.status, record.ai_status, record.error_detail = "processing", "processing", None
    user_store.update_document(user.id, record)
    return await _process_document_record(user, record, user.preferred_language, False)

@app.post("/api/user/documents/{doc_id}/retry-extraction")
async def retry_document_extraction(doc_id: str, user: User = Depends(require_current_user)):
    record = user_store.get_document(user.id, doc_id)
    if not record or not record.storage_path or not original_exists(record.storage_path):
        raise HTTPException(status_code=404, detail="Original file not found in this account.")
    try:
        content = read_original(record.storage_path)
        if len(content) > settings.MAX_UPLOAD_BYTES:
            raise ValueError("The stored file exceeds the configured upload size limit.")
        if Path(record.filename or "").suffix.lower() == ".pdf":
            record.raw_text, _ = extract_text_from_pdf(content)
        else:
            record.raw_text = content.decode("utf-8", errors="replace")
        if len(record.raw_text.strip()) < 20:
            raise ValueError("Extracted text is too short. Verify the original document.")
        record.extraction_status = "completed"
        record.status = "uploaded"
        record.ai_status = "pending"
        record.error_detail = None
    except Exception as error:
        record.extraction_status = "failed"
        record.status = "failed"
        record.error_detail = str(error)
    saved = user_store.update_document(user.id, record)
    return {"document": saved}

@app.post("/api/user/documents/confirm-review")
async def confirm_document_review(payload: ReviewConfirmRequest, user: User = Depends(require_current_user)):
    pending = user_store.get_pending_review(user.id, payload.review_id)
    if not pending:
        raise HTTPException(status_code=404, detail="Review session not found or already confirmed.")
    analysis = DischargeAnalysisResponse.model_validate(pending["analysis"])
    for index, addition in enumerate(payload.additions):
        section = (addition.get("section") or "Additional note").strip()[:80]
        value = (addition.get("value") or "").strip()[:1000]
        if value:
            analysis.user_added_information.append(ExtractedFact(
                value=f"{section}: {value} (Added by you, {datetime.now().date().isoformat()})",
                state="stated", source_references=["Added by you"]
            ))
    attach_source_document(analysis, pending["document_id"])
    record = user_store.complete_pending_review(user.id, payload.review_id, analysis)
    if not record:
        raise HTTPException(status_code=404, detail="Document was removed or is no longer available.")
    _send_upload_appointment_email(user, record)
    return {"document": record}

@app.delete("/api/user/documents/review/{review_id}")
async def discard_document_review(review_id: str, user: User = Depends(require_current_user)):
    user_store.discard_pending_review(user.id, review_id)
    return {"success": True}

# ========================================================
# GENERAL & BACKWARD COMPATIBLE API
# ========================================================

@app.get("/api/health")
async def health_check():
    """Service health and AI configuration status."""
    has_key = bool(settings.MODEL_API_KEY.strip())
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "ai_engine": "Meta Muse Spark API" if has_key else "Not configured",
        "model_configured": has_key,
        "meta_spark_configured": has_key,
        "model": settings.MODEL_NAME if has_key else "None"
    }

@app.get("/api/settings/region")
async def get_region_settings():
    """Returns configurable regional emergency contact settings."""
    return {"emergency_number": settings.EMERGENCY_NUMBER.strip() or "911"}

@app.post("/api/analyze", response_model=DischargeAnalysisResponse)
async def analyze_document_legacy(
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    language: str = Form("en"),
    user: Optional[User] = Depends(get_current_user)
):
    """Legacy analyze endpoint; returns extraction without persisting a document."""
    content_to_analyze = ""
    lang_code = language.strip().lower()
    if lang_code not in ["en", "hi", "bn"]:
        lang_code = "en"

    filename = None
    if file and file.filename:
        filename = file.filename
        file_bytes = await file.read()
        if len(file_bytes) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")

        if filename.lower().endswith(".pdf"):
            try:
                extracted, _ = extract_text_from_pdf(file_bytes)
                content_to_analyze = extracted
            except ValueError as ve:
                raise HTTPException(status_code=422, detail=str(ve))
        elif filename.lower().endswith((".txt", ".md")):
            content_to_analyze = file_bytes.decode("utf-8", errors="replace")
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format.")
    elif text and text.strip():
        content_to_analyze = text.strip()
        filename = "pasted_text.txt"
    else:
        raise HTTPException(status_code=400, detail="No document provided.")

    if not settings.MODEL_API_KEY.strip():
        raise HTTPException(status_code=503, detail="Muse Spark is not configured. Please try again later.")
    try:
        analysis = analyze_discharge_text(content_to_analyze, language=lang_code)
    except Exception:
        logger.exception("Muse Spark analysis failed")
        raise HTTPException(status_code=502, detail="Unable to extract — please verify the original document and try again.")

    normalize_analysis(analysis)
    return analysis

# Serve static frontend assets
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def serve_index():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return JSONResponse({"message": "DischargeBuddy API is running."})
