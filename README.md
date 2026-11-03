# DischargeBuddy 🏥
> **Your recovery, made simpler.**  
> An AI-powered post-discharge healthcare companion translating complex hospital paperwork into clear, actionable recovery plans.

Built for the Google AI Hackathon using Google Gemini 2.5 Flash, FastAPI, and Stitch-generated clinical design tokens.

---

## 🌟 Product Highlights

- **Clinical Clarity & Reassurance:** High-contrast, clean medical UI designed with soft teal accents, generous breathing room, and optical comfort for recovering patients.
- **Verbatim Medication Verification:** Side-by-side split cards comparing the doctor's exact clinical order with simple, comforting patient instructions (dosage, schedule, food guidance, safety limits).
- **Hospital Red-Flag Protocol:** Priority-tiered warning sign detection (Immediate ER, Call 911, Contact Surgeon) with 1-tap call triggers.
- **Multilingual Support:** Instant translations in **English**, **Hindi (हिन्दी)**, and **Bengali (বাংলা)** while safeguarding clinical dosages and emergency numbers.
- **Interactive Recovery Checklist:** Dynamic adherence tracking, progress bar, 30-second exercise guidance video modal, and refrigerator printable checklist.
- **Dual Mode AI Engine:** Works live with **Gemini 2.5 Flash**, with automatic, high-fidelity synthetic fallback when running offline or without an API key.

---

## 🚀 Quick Start (Local Run)

### 1. Requirements
- Python 3.10+ (or use the built-in `.venv` environment)

### 2. Configure API Key (Optional)
Copy `.env.example` to `.env` and add your Google Gemini API key:
```bash
cp .env.example .env
# Set GEMINI_API_KEY=your_gemini_api_key
```
*(Note: If no API key is provided, DischargeBuddy runs in demo mode with full interactive features using realistic synthetic data.)*

### 3. Run the Server
Launch the application with a single command:
```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```
Open your browser to: **[http://localhost:8080](http://localhost:8080)**

---

## 🧪 Automated Testing

Run the automated test suite with pytest:
```powershell
.\.venv\Scripts\python.exe -m pytest tests/
```
All 11 tests verify:
- Health check & AI engine status
- English, Hindi, and Bengali localization
- Real PDF parsing & text extraction
- Document validation & error handling
- Synthetic demo fallback resilience

---

## ☁️ Deployment to Google Cloud Run

DischargeBuddy is fully containerized and ready for Google Cloud Run:

### 1. Authenticate with Google Cloud
```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### 2. Deploy from Source directly to Cloud Run
```bash
gcloud run deploy dischargebuddy \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY="YOUR_GEMINI_API_KEY",GEMINI_MODEL="gemini-2.5-flash"
```

Cloud Run will automatically build the container using the provided `Dockerfile` and serve it on a secure HTTPS URL.

---

## 🛡️ Clinical AI Safety & Privacy Guarantees

1. **Untrusted Input Resilience:** Uploaded text is treated strictly as passive clinical data to prevent prompt injection.
2. **Preserve Verbatim Accuracy:** Exact medication names, dosages, and administration routes are never hallucinated or altered.
3. **No Treatment Discontinuation:** The AI explicitly advises patients never to stop or modify regimens without consulting their physician.
4. **Physician Precedence:** Hospital documentation and attending clinicians always take precedence over AI summaries.
5. **Zero Persistent Storage:** Uploaded summaries are processed in memory and never written to permanent disk storage.
