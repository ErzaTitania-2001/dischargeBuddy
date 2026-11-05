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
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

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
    ReviewConfirmRequest
)
from app.services.pdf_service import extract_text_from_pdf
from app.services.meta_spark_service import analyze_discharge_text
from app.services.clinical_normalizer import normalize_analysis
from app.services.document_storage import save_original, delete_original, read_original, original_exists
from app.services.auth_service import user_store, User, DocumentRecord
from app.services.duplicate_detector import check_for_duplicate
from app.services.reminder_service import (dispatch_due_reminders, send_brevo_email,
    create_verification_token, verify_email_token)

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
