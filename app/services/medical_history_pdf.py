"""Build a private, source-labelled medical handover PDF."""
from datetime import datetime, timezone
from html import escape
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, KeepTogether)


def build_medical_history_pdf(payload: dict[str, Any], sections: list[str]) -> bytes:
    output = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Brand", parent=styles["Title"], textColor=colors.HexColor("#0f766e"), alignment=TA_CENTER, spaceAfter=4))
    styles.add(ParagraphStyle(name="SectionHeading", parent=styles["Heading2"], textColor=colors.HexColor("#0f766e"), spaceBefore=12, spaceAfter=6, keepWithNext=True))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8, leading=11, textColor=colors.HexColor("#475569")))
    styles.add(ParagraphStyle(name="Cell", parent=styles["BodyText"], fontSize=8, leading=10, wordWrap="CJK"))
    story = [Paragraph("DischargeBuddy", styles["Brand"]),
             Paragraph("Medical History for a New Consultation", styles["Heading1"]),
             Paragraph(f"Generated {datetime.now(timezone.utc).astimezone().strftime('%d %b %Y, %H:%M %Z')}", styles["Small"]), Spacer(1, 8)]

    def para(value: Any) -> Paragraph:
        text = "Not recorded" if value is None or value == "" else str(value)
        return Paragraph(escape(text).replace("\n", "<br/>"), styles["BodyText"])

    def section(title: str, enabled: bool) -> None:
        if enabled:
            story.append(Paragraph(escape(title), styles["SectionHeading"]))

    def facts_table(headers: list[str], rows: list[list[Any]]) -> None:
        data = [[Paragraph(f"<b>{escape(str(cell))}</b>", styles["Cell"]) for cell in headers]]
        data.extend([[para(cell) for cell in row] for row in rows] or [[para("No information recorded")] + [para("") for _ in headers[1:]]])
        table = Table(data, colWidths=[(A4[0] - 36 * mm) / len(headers)] * len(headers), repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ccfbf1")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#134e4a")),
            ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([table, Spacer(1, 5)])

    sections_set = set(sections)
    if "patient" in sections_set:
        section("Patient information", True)
        patient = payload.get("patient", {})
        facts_table(["Field", "Recorded information"], [[key, patient.get(key)] for key in
            ["Full name", "Age / date of birth", "Sex", "Contact", "Patient ID", "Treating doctor / specialists"]])
    if "history" in sections_set:
        section("Medical history and timeline", True)
        for item in payload.get("history", []):
            story.append(KeepTogether([Paragraph(escape(item.get("heading", "Medical record")), styles["Heading3"]),
                para(item.get("details")), Paragraph(escape("Source: " + item.get("source", "Not recorded")), styles["Small"]), Spacer(1, 5)]))
        if not payload.get("history"):
            story.append(para("No processed discharge history is available."))
    if "allergies" in sections_set:
        section("Allergies and adverse reactions", True)
        facts_table(["Documented allergy / status", "Verification", "Source"], payload.get("allergies", []))
    if "medications" in sections_set:
        section("Medication list", True)
        facts_table(["Medicine", "Instructions", "Status / verification", "Source"], payload.get("medications", []))
    if "followups" in sections_set:
        section("Follow-up history and consultation notes", True)
        facts_table(["Date", "Appointment", "Clinician / location", "Source"], payload.get("appointments", []))
        for label, key in [("Caregiver / patient observations", "observations"), ("Questions for the doctor", "questions")]:
            story.extend([Paragraph(escape(label), styles["Heading3"]), para(payload.get("notes", {}).get(key))])
            if payload.get("notes", {}).get("updated_at"):
                story.append(Paragraph("User-entered · Updated " + escape(payload["notes"]["updated_at"]), styles["Small"]))
        story.append(Paragraph("Previous visit notes (user-entered)", styles["Heading3"]))
        previous = payload.get("previous_consultation_notes", [])
        for note in previous:
            story.append(Paragraph(escape(f"{note.get('created_at', 'Date not recorded')} · {note.get('outgoing_name', 'Patient/caregiver')} to {note.get('incoming_name', 'Clinician')}: {note.get('notes', '')}"), styles["BodyText"]))
        if not previous:
            story.append(para("No previous visit notes recorded."))
    if "care" in sections_set:
        section("Current care requirements", True)
        for line in payload.get("care", []) or ["No care requirements were extracted from available records."]:
            story.append(Paragraph("• " + escape(str(line)), styles["BodyText"]))
    if "consultation" in sections_set:
        section("Notes for the Upcoming Consultation", True)
        notes = payload.get("notes", {})
        for label, key in [("Reason for consultation", "reason"), ("Main concerns / recent changes", "concerns"),
                           ("Questions for the doctor", "questions"), ("Pending investigations", "pending_investigations"),
                           ("Medication-related questions", "medication_questions"), ("Additional notes", "additional_notes")]:
            story.extend([Paragraph(escape(label), styles["Heading3"]), para(notes.get(key))])
    if "investigations" in sections_set:
        section("Investigations and reports", True)
        facts_table(["Investigation", "Date", "Recorded result", "Source"], payload.get("investigations", []))
    if "sources" in sections_set:
        section("Original source documents", True)
        for doc in payload.get("sources", []):
            story.append(Paragraph("• " + escape(f"{doc.get('filename') or doc.get('title')} — {doc.get('uploaded_at')} — {doc.get('status')}"), styles["BodyText"]))
    story.extend([Spacer(1, 10), Paragraph("AI-assisted medical history summary. This document does not replace original medical records or clinician assessment. Medication continuation and unclear details should be verified with the treating clinician.", styles["Small"])])

    def page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#99f6e4"))
        canvas.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#475569"))
        canvas.drawString(18 * mm, 10 * mm, "DischargeBuddy · Confidential medical information")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
                                 topMargin=16 * mm, bottomMargin=22 * mm, title="DischargeBuddy Medical History")
    document.build(story, onFirstPage=page, onLaterPages=page)
    return output.getvalue()
