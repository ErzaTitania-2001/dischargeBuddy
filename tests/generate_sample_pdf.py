import os
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
pdf_path = FIXTURE_DIR / "sample_discharge_summary.pdf"

doc = SimpleDocTemplate(
    str(pdf_path),
    pagesize=letter,
    rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
)

styles = getSampleStyleSheet()

header_style = ParagraphStyle(
    'HospitalHeader',
    parent=styles['Normal'],
    fontName='Helvetica-Bold',
    fontSize=18,
    leading=22,
    textColor=colors.HexColor('#00685f')
)

sub_style = ParagraphStyle(
    'SubHeader',
    parent=styles['Normal'],
    fontName='Helvetica-Bold',
    fontSize=12,
    leading=16,
    textColor=colors.HexColor('#131b2e')
)

section_title_style = ParagraphStyle(
    'SectionTitle',
    parent=styles['Normal'],
    fontName='Helvetica-Bold',
    fontSize=11,
    leading=15,
    textColor=colors.HexColor('#00685f'),
    spaceAfter=4
)

body_style = ParagraphStyle(
    'ClinicalBody',
    parent=styles['Normal'],
    fontName='Helvetica',
    fontSize=9,
    leading=13,
    textColor=colors.HexColor('#131b2e')
)

story = []

# Title & Hospital Header
story.append(Paragraph("ST. JUDE MEMORIAL HOSPITAL", header_style))
story.append(Paragraph("SURGICAL DISCHARGE SUMMARY & INSTRUCTIONS", sub_style))
story.append(Spacer(1, 8))
story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#00685f'), spaceBefore=2, spaceAfter=8))

# Patient Metadata Table
patient_data = [
    [Paragraph("<b>Patient Name:</b> Jenkins, Sarah", body_style), Paragraph("<b>MRN / Record:</b> #SJM-84920", body_style)],
    [Paragraph("<b>DOB:</b> 04/12/1988 (Age 36)", body_style), Paragraph("<b>Discharge Date:</b> October 24, 2024", body_style)],
    [Paragraph("<b>Attending:</b> Dr. Robert Chen, MD", body_style), Paragraph("<b>Service:</b> Orthopedic Surgery", body_style)],
    [Paragraph("<b>Procedure:</b> Right Knee Arthroscopy, Partial Medial Meniscectomy", body_style), Paragraph("<b>Status:</b> Discharged Home", body_style)]
]
t = Table(patient_data, colWidths=[270, 260])
t.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f2f3ff')),
    ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#bcc9c6')),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ('TOPPADDING', (0,0), (-1,-1), 4),
    ('LEFTPADDING', (0,0), (-1,-1), 8),
    ('RIGHTPADDING', (0,0), (-1,-1), 8),
]))
story.append(t)
story.append(Spacer(1, 10))

# Clinical Summary
story.append(Paragraph("1. HOSPITAL COURSE & CLINICAL SUMMARY", section_title_style))
summary_text = (
    "Patient underwent elective right knee diagnostic and operative arthroscopy with partial medial meniscectomy. "
    "Procedure was tolerated well without intraoperative complications. Stable in PACU. Vital signs afebrile and stable. "
    "Voided spontaneously. Patient ambulated 50 feet with bilateral crutches bearing weight as tolerated. Surgical dressing "
    "is intact, dry, and clean. Discharged home in stable condition into the care of husband."
)
story.append(Paragraph(summary_text, body_style))
story.append(Spacer(1, 8))

# Medications Table
story.append(Paragraph("2. PRESCRIBED DISCHARGE MEDICATIONS (VERBATIM ORDERS)", section_title_style))
meds_data = [
    [Paragraph("<b>Medication & Dosage</b>", body_style), Paragraph("<b>Frequency & Route</b>", body_style), Paragraph("<b>Duration / Instructions</b>", body_style)],
    [
        Paragraph("<b>Cephalexin 500 MG</b><br/>Oral Capsule", body_style),
        Paragraph("1 capsule q6h (every 6 hours)<br/>Oral", body_style),
        Paragraph("Take for 7 days until complete.<br/>Prophylaxis against surgical site infection.", body_style)
    ],
    [
        Paragraph("<b>Acetaminophen 500 MG</b><br/>Oral Tablet", body_style),
        Paragraph("1-2 tablets q8h PRN (as needed)<br/>Oral", body_style),
        Paragraph("For mild/moderate pain. Max 3,000 mg in 24 hours. Do not combine with APAP products.", body_style)
    ],
    [
        Paragraph("<b>Enoxaparin (Lovenox) 40 MG / 0.4ML</b><br/>Pre-filled Syringe", body_style),
        Paragraph("0.4 mL SubQ once daily<br/>Subcutaneous", body_style),
        Paragraph("Inject into abdomen every morning for 10 days for DVT prophylaxis.", body_style)
    ]
]
mt = Table(meds_data, colWidths=[170, 160, 200])
mt.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#eaedff')),
    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#bcc9c6')),
    ('TOPPADDING', (0,0), (-1,-1), 4),
    ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ('LEFTPADDING', (0,0), (-1,-1), 6),
    ('RIGHTPADDING', (0,0), (-1,-1), 6),
]))
story.append(mt)
story.append(Spacer(1, 8))

# Activity & Wound Care
story.append(Paragraph("3. POST-OPERATIVE ACTIVITY & WOUND CARE", section_title_style))
activity_text = (
    "• <b>Weight Bearing:</b> Weight bearing as tolerated (WBAT) with bilateral crutches.<br/>"
    "• <b>Elevation & Cryo:</b> Keep knee elevated above heart level on pillows while resting. Apply ice pack for 20 minutes every 2 hours.<br/>"
    "• <b>Dressing:</b> Waterproof surgical dressing must remain clean, dry, and undisturbed until follow-up suture inspection. Do not soak in bath."
)
story.append(Paragraph(activity_text, body_style))
story.append(Spacer(1, 8))

# Follow-Up Appointments
story.append(Paragraph("4. MANDATORY FOLLOW-UP APPOINTMENTS", section_title_style))
fup_text = (
    "• <b>Dr. Robert Chen, MD:</b> Suture Removal & Range-of-Motion Test — Thursday, October 31, 2024 at 10:30 AM (Suite 410, West Medical Pavilion).<br/>"
    "• <b>Physical Therapy Evaluation:</b> Initial Rehab Session — Monday, November 4, 2024 at 2:00 PM (St. Jude Rehabilitation Annex, Ground Floor)."
)
story.append(Paragraph(fup_text, body_style))
story.append(Spacer(1, 8))

# Red Flags
story.append(Paragraph("5. RED-FLAG WARNING SIGNS (SEEK IMMEDIATE MEDICAL CARE)", section_title_style))
warnings_text = (
    "<font color='#ba1a1a'><b>EMERGENCY WARNINGS:</b></font><br/>"
    "1. Oral fever greater than 101.4°F (38.5°C) or persistent shaking chills.<br/>"
    "2. Severe localized calf pain, warmth, redness, or swelling in lower right leg (DVT signs).<br/>"
    "3. Persistent soaking drainage, heavy bleeding, or foul odor from surgical dressing.<br/>"
    "4. Acute shortness of breath or sharp chest pain upon inspiration (Call 911 immediately)."
)
story.append(Paragraph(warnings_text, body_style))
story.append(Spacer(1, 8))

# Sign-off
story.append(Paragraph("<b>Attending Physician Signature:</b> <i>Dr. Robert Chen, MD (Electronically Signed 10/24/2024 09:45 EST)</i>", body_style))
story.append(Paragraph("<b>Orthopedic Triage Line:</b> (555) 019-2834 | <b>Emergency:</b> 911", body_style))

doc.build(story)
print(f"Sample PDF generated successfully at: {pdf_path}")
