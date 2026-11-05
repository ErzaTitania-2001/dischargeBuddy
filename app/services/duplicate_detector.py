import re
import os
from typing import Optional, List, Tuple
from pydantic import BaseModel
from app.models import DischargeAnalysisResponse

class DuplicateCheckResult(BaseModel):
    is_duplicate: bool
    duplicate_type: str  # "none", "exact", "potential"
    message: str
    existing_document_id: Optional[str] = None
    existing_filename: Optional[str] = None
    existing_upload_date: Optional[str] = None

def normalize_filename(filename: str) -> str:
    """
    Normalizes a filename for duplicate comparison:
    1. Removes file extension (e.g. .pdf, .txt, .docx).
    2. Lowercases string.
    3. Replaces underscores, dashes, and dots with spaces.
    4. Trims leading/trailing whitespace.
    5. Normalizes consecutive whitespace into a single space.
    """
    if not filename:
        return ""
    
    # Strip extension
    base, _ = os.path.splitext(filename.strip())
    if not base:
        base = filename.strip()
    
    # Lowercase
    clean = base.lower()
    
    # Replace separators with spaces
    clean = re.sub(r'[_\-\.]+', ' ', clean)
    
    # Normalize spaces
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

def extract_stem_without_copy_markers(normalized: str) -> str:
    """
    Removes common copy/duplicate markers from the end of a normalized filename.
    Examples:
    - 'discharge document (1)' -> 'discharge document'
    - 'discharge document 1' -> 'discharge document'
    - 'discharge document copy' -> 'discharge document'
    - 'discharge document (copy)' -> 'discharge document'
    - 'discharge document copy 1' -> 'discharge document'
    """
    if not normalized:
        return ""
    
    stem = normalized
    # Regex to strip trailing copy suffixes like (1), (2), copy, copy 1, - 1, etc.
    patterns = [
        r'\s*\(\s*\d+\s*\)$',          # (1), (2), etc.
        r'\s*\(\s*copy(\s*\d+)?\s*\)$',# (copy), (copy 1), etc.
        r'\s+copy(\s+\d+)?$',          # copy, copy 1, etc.
        r'\s+\d+$',                    # trailing space followed by single/double digit
    ]
    
    changed = True
    while changed:
        changed = False
        for p in patterns:
            new_stem = re.sub(p, '', stem, flags=re.IGNORECASE).strip()
            if new_stem != stem and len(new_stem) > 0:
                stem = new_stem
                changed = True
                
    return stem

def check_for_duplicate(new_filename: str, existing_docs: List[any]) -> DuplicateCheckResult:
    """
    Compares a candidate filename against existing documents for the user.
    Returns DuplicateCheckResult with exact or potential duplicate status.
    """
    if not new_filename or not existing_docs:
        return DuplicateCheckResult(
            is_duplicate=False,
            duplicate_type="none",
            message="No duplicates found."
        )

    target_norm = normalize_filename(new_filename)
    target_stem = extract_stem_without_copy_markers(target_norm)

    # First pass: Check for EXACT duplicate
    for doc in existing_docs:
        doc_filename = getattr(doc, 'filename', '') or getattr(doc, 'title', '')
        if not doc_filename:
            continue
        
        doc_norm = normalize_filename(doc_filename)
        if target_norm == doc_norm:
            uploaded_at = getattr(doc, 'uploaded_at', 'Previously uploaded')
            return DuplicateCheckResult(
                is_duplicate=True,
                duplicate_type="exact",
                message="This discharge summary may already exist.",
                existing_document_id=getattr(doc, 'id', None),
                existing_filename=doc_filename,
                existing_upload_date=uploaded_at
            )

    # Second pass: Check for POTENTIAL duplicate (copy markers, e.g. " (1)", " copy")
    for doc in existing_docs:
        doc_filename = getattr(doc, 'filename', '') or getattr(doc, 'title', '')
        if not doc_filename:
            continue

        doc_norm = normalize_filename(doc_filename)
        doc_stem = extract_stem_without_copy_markers(doc_norm)

        # If stems match and at least one has a copy marker, or stems match identically
        if target_stem == doc_stem and len(target_stem) >= 4:
            # Verify they are not completely different (e.g. October vs November)
            uploaded_at = getattr(doc, 'uploaded_at', 'Previously uploaded')
            return DuplicateCheckResult(
                is_duplicate=True,
                duplicate_type="potential",
                message=f"This file appears similar to '{doc_filename}'.",
                existing_document_id=getattr(doc, 'id', None),
                existing_filename=doc_filename,
                existing_upload_date=uploaded_at
            )

    return DuplicateCheckResult(
        is_duplicate=False,
        duplicate_type="none",
        message="No duplicates found."
    )
