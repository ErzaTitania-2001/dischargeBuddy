from typing import List, Optional
from pydantic import BaseModel, Field

class MedicationInstruction(BaseModel):
    name: str = Field(..., description="Medication brand or generic name (e.g., Cephalexin)")
    dosage: str = Field(..., description="Exact dosage (e.g., 500mg)")
    route: str = Field("Oral", description="Administration route (e.g., Oral Capsule, SubQ Syringe)")
    frequency: str = Field(..., description="Frequency (e.g., Every 6 hours)")
    duration: Optional[str] = Field(None, description="Duration of therapy if specified (e.g., 7 days)")
    purpose: str = Field(..., description="Plain-language purpose (e.g., Antibiotic Course to prevent knee infection)")
    verbatim_order: str = Field(..., description="Exact doctor's order as documented in source")
    patient_explanation: str = Field(..., description="Simple, reassuring patient-friendly instructions")
    tips_or_warnings: Optional[str] = Field(None, description="Important tips, e.g. take with food, avoid alcohol")

class FollowUpTask(BaseModel):
    id: str = Field(..., description="Unique task identifier")
    title: str = Field(..., description="Task title (e.g., Suture Removal & ROM Test)")
    provider: Optional[str] = Field(None, description="Doctor or clinic name (e.g., Dr. Robert Chen)")
    date_time: str = Field(..., description="Explicit date and time stated in source (e.g., Thursday, Oct 31 • 10:30 AM)")
    location: Optional[str] = Field(None, description="Clinic location or pavilion")
    time_of_day: str = Field("Morning", description="Morning, Afternoon, or Evening")
    completed: bool = Field(False, description="Whether marked completed")
    type: str = Field("appointment", description="'appointment' or 'recovery_task'")
    instructions: Optional[str] = Field(None, description="Specific instructions for this task")
    document_id: Optional[str] = Field(None, description="ID of source document that produced this task")

class WarningSign(BaseModel):
    sign: str = Field(..., description="Warning sign explicitly stated in source (e.g., Fever over 101.4°F)")
    severity: str = Field("High Priority", description="'Immediate ER', 'Call 911', 'High Priority', or 'Contact Surgeon'")
    action: str = Field(..., description="Required patient action (e.g., Call triage nurse immediately)")

class PatientMetadata(BaseModel):
    patient_name: str = Field("Not specified in discharge summary", description="Patient name if documented")
    hospital_name: str = Field("Not specified in discharge summary", description="Hospital name")
    record_number: str = Field("Not specified in discharge summary", description="MRN or Document ID")
    attending_physician: str = Field("Not specified in discharge summary", description="Attending physician")
    discharge_date: str = Field("Not specified in discharge summary", description="Date of discharge")
    procedure_or_diagnosis: str = Field("Not specified in discharge summary", description="Procedure or primary diagnosis")

class DischargeAnalysisResponse(BaseModel):
    patient_info: PatientMetadata = Field(default_factory=PatientMetadata)
    summary: str = Field(..., description="Plain-language explanation of what happened and what to do next")
    recovery_milestones: List[str] = Field(default_factory=list, description="Key recovery highlights (e.g., Ice 20 min/2 hrs, Elevate above heart)")
    medication_instructions: List[MedicationInstruction] = Field(default_factory=list)
    follow_up_tasks: List[FollowUpTask] = Field(default_factory=list)
    source_warning_signs: List[WarningSign] = Field(default_factory=list)
    missing_or_ambiguous_information: List[str] = Field(default_factory=list, description="Ambiguities or missing instructions flagged for clinician review")
    language: str = Field("en", description="Language code: en, hi, bn")
    is_synthetic_demo: bool = Field(False, description="True if synthetic fallback was used")

class TextAnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=10, description="Hospital discharge summary text")
    language: str = Field("en", description="Target language: en, hi, bn")

# Auth & User Schemas
class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, description="User full name")
    email: str = Field(..., description="Valid email address")
    password: str = Field(..., min_length=6, description="Password (at least 6 characters)")
    preferred_language: str = Field("en", description="en, hi, or bn")

class LoginRequest(BaseModel):
    email: str = Field(..., description="Registered email address")
    password: str = Field(..., description="User password")

class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    preferred_language: Optional[str] = None

class ExtractResponse(BaseModel):
    extracted_text: str
    page_count: int
    char_count: int
    filename: Optional[str] = None
    is_duplicate: bool = False
    duplicate_type: str = "none"
    duplicate_message: Optional[str] = None
    existing_document_id: Optional[str] = None
    existing_filename: Optional[str] = None
    existing_upload_date: Optional[str] = None

class CheckDuplicateRequest(BaseModel):
    filename: str = Field(..., min_length=1, description="Filename to check for duplicates")

class CheckDuplicateResponse(BaseModel):
    is_duplicate: bool
    duplicate_type: str  # "none", "exact", "potential"
    message: str
    existing_document_id: Optional[str] = None
    existing_filename: Optional[str] = None
    existing_upload_date: Optional[str] = None

class DeleteDocumentResponse(BaseModel):
    success: bool
    message: str
    removed_document_id: str
    remaining_documents_count: int
    remaining_tasks_count: int
