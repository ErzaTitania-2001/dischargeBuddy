from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field

class MedicationInstruction(BaseModel):
    name: Optional[str] = None
    ingredient: Optional[str] = None
    dosage: Optional[str] = None
    route: Optional[str] = None
    frequency: Optional[str] = None
    frequency_type: Literal["scheduled", "as_needed", "event_based", "unspecified"] = "unspecified"
    when_to_take: Optional[str] = None
    duration: Optional[str] = None
    maximum_limit: Optional[str] = None
    continuation_status: Optional[str] = None
    purpose: Optional[str] = None
    verbatim_order: Optional[str] = None
    patient_explanation: Optional[str] = None
    tips_or_warnings: Optional[str] = None
    source_references: List[str] = Field(default_factory=list)
    source_document_id: Optional[str] = None
    state: Literal["stated", "missing", "ambiguous", "conflicting"] = "stated"
    field_states: Dict[str, Literal["stated", "missing", "ambiguous", "conflicting"]] = Field(default_factory=dict)
    conflicts: List[str] = Field(default_factory=list)
    duplicate_count: int = 1

class FollowUpTask(BaseModel):
    id: str = Field(..., description="Unique task identifier")
    title: str = Field(..., description="Task title as stated in the source")
    provider: Optional[str] = Field(None, description="Provider or clinic as stated in the source")
    date_time: Optional[str] = None
    location: Optional[str] = Field(None, description="Location as stated in the source")
    time_of_day: Optional[str] = None
    completed: bool = Field(False, description="Whether marked completed")
    completed_at: Optional[str] = None
    cancelled: bool = False
    type: str = Field("appointment", description="'appointment' or 'recovery_task'")
    instructions: Optional[str] = Field(None, description="Specific instructions for this task")
    document_id: Optional[str] = Field(None, description="ID of source document that produced this task")
    preparation_text: Optional[str] = None
    appointment_time: Optional[str] = None
    date_sort_key: Optional[str] = None
    source_references: List[str] = Field(default_factory=list)
    state: Literal["stated", "missing", "ambiguous", "conflicting"] = "stated"
    field_states: Dict[str, Literal["stated", "missing", "ambiguous", "conflicting"]] = Field(default_factory=dict)

class ExtractedFact(BaseModel):
    value: str
    state: Literal["stated", "missing", "ambiguous", "conflicting"] = "stated"
    source_references: List[str] = Field(default_factory=list)
    source_document_id: Optional[str] = None

class WarningSign(BaseModel):
    sign: str
    severity: Optional[str] = None
    action: Optional[str] = None
    source_references: List[str] = Field(default_factory=list)
    source_document_id: Optional[str] = None
    state: Literal["stated", "missing", "ambiguous", "conflicting"] = "stated"

class InvestigationResult(BaseModel):
    name: Optional[str] = None
    date: Optional[str] = None
    result: Optional[str] = None
    source_references: List[str] = Field(default_factory=list)
    source_document_id: Optional[str] = None
    state: Literal["stated", "missing", "ambiguous", "conflicting"] = "stated"

class PatientMetadata(BaseModel):
    patient_name: str = Field("Not specified in discharge summary", description="Patient name if documented")
    age_or_date_of_birth: str = Field("Not specified in discharge summary", description="Only explicitly documented age or date of birth")
    sex: str = Field("Not specified in discharge summary", description="Sex only if explicitly documented")
    contact_information: str = Field("Not specified in discharge summary", description="Contact information only if included in source")
    hospital_name: str = Field("Not specified in discharge summary", description="Hospital name")
    record_number: str = Field("Not specified in discharge summary", description="MRN or Document ID")
    attending_physician: str = Field("Not specified in discharge summary", description="Attending physician")
    admission_date: str = Field("Not specified in discharge summary", description="Admission date, if documented")
    admission_reason: str = Field("Not specified in discharge summary", description="Reason for admission, if documented")
    discharge_date: str = Field("Not specified in discharge summary", description="Date of discharge")
    procedure_or_diagnosis: str = Field("Not specified in discharge summary", description="Procedure or primary diagnosis")

class DischargeAnalysisResponse(BaseModel):
    patient_info: PatientMetadata = Field(default_factory=PatientMetadata)
    summary: str = Field(..., description="Plain-language explanation of what happened and what to do next")
    recovery_milestones: List[str] = Field(default_factory=list, description="Recovery instructions stated in the source")
    medication_instructions: List[MedicationInstruction] = Field(default_factory=list)
    follow_up_tasks: List[FollowUpTask] = Field(default_factory=list)
    source_warning_signs: List[WarningSign] = Field(default_factory=list)
    investigations: List[InvestigationResult] = Field(default_factory=list)
    diagnoses: List[ExtractedFact] = Field(default_factory=list)
    hospital_course: Optional[str] = None
    allergies: List[ExtractedFact] = Field(default_factory=list)
    allergy_status: Literal["listed", "none_reported", "not_in_document", "ambiguous", "conflicting"] = "not_in_document"
    past_history: List[ExtractedFact] = Field(default_factory=list)
    preparation_instructions: List[str] = Field(default_factory=list)
    user_added_information: List[ExtractedFact] = Field(default_factory=list)
    conflicting_information: List[str] = Field(default_factory=list)
    missing_or_ambiguous_information: List[str] = Field(default_factory=list, description="Ambiguities or missing instructions flagged for clinician review")
    language: str = Field("en", description="Language code: en, hi, bn")

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
    email_notifications_enabled: Optional[bool] = None
    timezone: Optional[str] = None

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
    document_id: Optional[str] = None
    processing_status: Optional[str] = None
    extraction_status: Optional[str] = None
    error_detail: Optional[str] = None

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

class PainEntryRequest(BaseModel):
    score: int = Field(..., ge=1, le=10)
    note: Optional[str] = None

class HandoverEventRequest(BaseModel):
    kind: Literal["visit", "caregiver"]
    outgoing_name: str = Field(..., min_length=1, max_length=120)
    incoming_name: str = Field(..., min_length=1, max_length=120)
    sections_read: List[str] = Field(default_factory=list)
    teach_back_passed: bool = False
    notes: Optional[str] = None

class ConsultationNotesRequest(BaseModel):
    consultation_id: str = Field("upcoming", max_length=200)
    reason: str = Field("", max_length=3000)
    concerns: str = Field("", max_length=6000)
    observations: str = Field("", max_length=6000)
    questions: str = Field("", max_length=6000)
    pending_investigations: str = Field("", max_length=3000)
    medication_questions: str = Field("", max_length=3000)
    additional_notes: str = Field("", max_length=6000)

class MedicalHistoryExportRequest(BaseModel):
    sections: List[str] = Field(default_factory=lambda: ["patient", "history", "allergies", "medications", "followups", "care", "consultation", "investigations", "sources"])
    reviewed: bool = False
    consultation_id: str = Field("upcoming", max_length=200)

class ReviewConfirmRequest(BaseModel):
    review_id: str = Field(..., min_length=1)
    additions: List[Dict[str, str]] = Field(default_factory=list)
