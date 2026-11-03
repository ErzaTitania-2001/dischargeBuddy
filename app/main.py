import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Header, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.models import (
    DischargeAnalysisResponse,
    TextAnalyzeRequest,
    RegisterRequest,
    LoginRequest,
    ProfileUpdateRequest,
    ExtractResponse,
    FollowUpTask,
    CheckDuplicateRequest,
    CheckDuplicateResponse,
    DeleteDocumentResponse
)
from app.services.pdf_service import extract_text_from_pdf
from app.services.gemini_service import analyze_discharge_text
from app.services.sample_data import get_sample_discharge_data, SAMPLE_DISCHARGE_TEXT
from app.services.auth_service import user_store, User, DocumentRecord
from app.services.duplicate_detector import check_for_duplicate

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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Dependency to get current user from session token
async def get_current_user(
    authorization: Optional[str] = Header(None),
    x_session_token: Optional[str] = Header(None)
) -> Optional[User]:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ")[1].strip()
    elif x_session_token:
        token = x_session_token.strip()

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
async def register(payload: RegisterRequest):
    """Registers a new user and returns user info + session token."""
    try:
        user, token = user_store.register(
            email=payload.email,
            password=payload.password,
            name=payload.name,
            preferred_language=payload.preferred_language
        )
        return {"user": user, "token": token, "auth_mode": "in-memory-session"}
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

@app.post("/api/auth/login")
async def login(payload: LoginRequest):
    """Authenticates existing user with email and password."""
    try:
        user, token = user_store.login(payload.email, payload.password)
        return {"user": user, "token": token, "auth_mode": "in-memory-session"}
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(ve))

@app.post("/api/auth/demo")
async def demo_login():
    """Instant demo login pre-populated with Sarah Jenkins sample clinical data."""
    user, token = user_store.demo_login()
    return {
        "user": user,
        "token": token,
        "auth_mode": "demo",
        "demo_notice": "Running in Development Demo Mode with synthetic clinical data."
    }

@app.get("/api/auth/me")
async def get_me(user: User = Depends(require_current_user)):
    """Returns profile for currently authenticated user."""
    return {"user": user}

@app.post("/api/auth/logout")
async def logout(
    authorization: Optional[str] = Header(None),
    x_session_token: Optional[str] = Header(None)
):
    """Logs out user and invalidates session token."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ")[1].strip()
    elif x_session_token:
        token = x_session_token.strip()

    if token:
        user_store.logout(token)
    return {"message": "Logged out successfully"}

@app.put("/api/user/profile")
async def update_profile(
    payload: ProfileUpdateRequest,
    user: User = Depends(require_current_user)
):
    """Updates user display name or preferred language."""
    updated = user_store.update_profile(user.id, name=payload.name, preferred_language=payload.preferred_language)
    return {"user": updated}

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
    
    success, rem_docs, rem_tasks = user_store.remove_document(user.id, doc_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove document. Please try again."
        )
    
    return DeleteDocumentResponse(
        success=True,
        message=f"Document '{doc.filename or doc.title}' removed successfully.",
        removed_document_id=doc_id,
        remaining_documents_count=rem_docs,
        remaining_tasks_count=rem_tasks
    )

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

# ========================================================
# UPLOAD, EXTRACTION & REVIEW PIPELINE
# ========================================================

@app.post("/api/documents/extract", response_model=ExtractResponse)
async def extract_document_text(
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    user: Optional[User] = Depends(get_current_user)
):
    """
    Step 1 of Document Workflow:
    Extracts text from PDF or validates pasted text, returning raw text
    for user review and editing BEFORE sending to AI.
    Also checks for duplicate documents for the current user.
    """
    extracted_text = ""
    page_count = 1
    filename = None
    dup_res = None

    if file and file.filename:
        filename = file.filename
        file_bytes = await file.read()
        if len(file_bytes) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")
        
        if filename.lower().endswith(".pdf"):
            try:
                extracted_text, page_count = extract_text_from_pdf(file_bytes)
            except ValueError as ve:
                raise HTTPException(status_code=422, detail=str(ve))
        elif filename.lower().endswith((".txt", ".md")):
            extracted_text = file_bytes.decode("utf-8", errors="replace")
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format '{filename}'. Please upload a PDF or TXT file."
            )

        if user:
            existing_docs = user_store.get_documents(user.id)
            dup_res = check_for_duplicate(filename, existing_docs)
    elif text and text.strip():
        extracted_text = text.strip()
        filename = "pasted_discharge_summary.txt"
    else:
        raise HTTPException(
            status_code=400,
            detail="Please select a PDF file or paste discharge summary text."
        )

    if len(extracted_text.strip()) < 20:
        raise HTTPException(
            status_code=400,
            detail="Extracted text is too short to be a discharge summary. Please check your document."
        )

    return ExtractResponse(
        extracted_text=extracted_text,
        page_count=page_count,
        char_count=len(extracted_text),
        filename=filename,
        is_duplicate=dup_res.is_duplicate if dup_res else False,
        duplicate_type=dup_res.duplicate_type if dup_res else "none",
        duplicate_message=dup_res.message if dup_res else None,
        existing_document_id=dup_res.existing_document_id if dup_res else None,
        existing_filename=dup_res.existing_filename if dup_res else None,
        existing_upload_date=dup_res.existing_upload_date if dup_res else None
    )

@app.post("/api/documents/analyze")
async def analyze_and_save_document(
    text: str = Form(...),
    language: str = Form("en"),
    title: Optional[str] = Form(None),
    filename: Optional[str] = Form(None),
    user: Optional[User] = Depends(get_current_user)
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

    # Analyze via Gemini AI or synthetic demo
    analysis: DischargeAnalysisResponse = analyze_discharge_text(text, language=lang_code)

    # If user is authenticated, persist in their user store
    if user:
        doc_title = title or (
            analysis.patient_info.procedure_or_diagnosis 
            if analysis.patient_info and analysis.patient_info.procedure_or_diagnosis 
            else "Hospital Discharge Summary"
        )
        record = DocumentRecord(
            id=f"doc-{uuid.uuid4().hex[:8]}",
            title=doc_title,
            filename=filename or "discharge_summary.pdf",
            uploaded_at=datetime.now(timezone.utc).strftime("%b %d, %Y • %I:%M %p"),
            raw_text=text,
            status="processed",
            analysis=analysis
        )
        user_store.add_document(user.id, record)

    return analysis

# ========================================================
# GENERAL & BACKWARD COMPATIBLE API
# ========================================================

@app.get("/api/health")
async def health_check():
    """Service health and AI configuration status."""
    has_key = bool(settings.GEMINI_API_KEY.strip())
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "ai_engine": "Gemini API" if has_key else "Synthetic Demo Fallback",
        "gemini_configured": has_key,
        "model": settings.GEMINI_MODEL if has_key else "None (demo mode)"
    }

@app.get("/api/sample")
async def get_sample(lang: str = "en") -> DischargeAnalysisResponse:
    """Returns synthetic hospital discharge analysis in requested language."""
    return get_sample_discharge_data(lang)

@app.get("/api/sample-text")
async def get_sample_text():
    """Returns raw realistic hospital discharge summary text for testing."""
    return {"text": SAMPLE_DISCHARGE_TEXT.strip()}

@app.post("/api/analyze", response_model=DischargeAnalysisResponse)
async def analyze_document_legacy(
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    language: str = Form("en"),
    user: Optional[User] = Depends(get_current_user)
):
    """Direct upload & analyze endpoint for compatibility."""
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

    analysis = analyze_discharge_text(content_to_analyze, language=lang_code)

    if user:
        record = DocumentRecord(
            id=f"doc-{uuid.uuid4().hex[:8]}",
            title=analysis.patient_info.procedure_or_diagnosis or "Discharge Document",
            filename=filename,
            uploaded_at=datetime.now(timezone.utc).strftime("%b %d, %Y • %I:%M %p"),
            raw_text=content_to_analyze,
            status="processed",
            analysis=analysis
        )
        user_store.add_document(user.id, record)

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
