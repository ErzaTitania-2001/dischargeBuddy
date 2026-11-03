import io
import logging
from typing import Tuple
from pypdf import PdfReader

logger = logging.getLogger(__name__)

def extract_text_from_pdf(file_bytes: bytes) -> Tuple[str, int]:
    """
    Extracts text from PDF bytes.
    Returns (extracted_text, page_count).
    Raises ValueError on empty or corrupted files.
    """
    if not file_bytes or len(file_bytes) == 0:
        raise ValueError("Uploaded file is empty (0 bytes). Please upload a valid discharge document.")

    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        num_pages = len(reader.pages)
        if num_pages == 0:
            raise ValueError("PDF document contains no pages.")

        extracted_parts = []
        for idx, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            if page_text.strip():
                extracted_parts.append(f"--- [Page {idx + 1}] ---\n" + page_text.strip())

        full_text = "\n\n".join(extracted_parts).strip()
        if not full_text:
            raise ValueError(
                "Document appears to be a scanned image or empty without selectable text. "
                "Please upload a text-readable PDF or copy and paste the document text."
            )

        # Truncate safety ceiling to prevent massive prompt abuse (e.g. 50,000 characters)
        if len(full_text) > 40000:
            full_text = full_text[:40000] + "\n\n[Warning: Document truncated to first 40,000 characters]"

        return full_text, num_pages

    except Exception as e:
        if isinstance(e, ValueError):
            raise
        logger.error(f"Error parsing PDF: {e}")
        raise ValueError(f"Unable to parse PDF document: {str(e)}")
