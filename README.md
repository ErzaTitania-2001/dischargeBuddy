# DischargeBuddy 🏥
> **Your recovery, made simpler.**  
> An AI-powered post-discharge healthcare companion translating complex hospital paperwork into clear, actionable recovery plans.

Built using Meta Muse Spark, FastAPI, and Stitch-generated clinical design tokens.

---

## 🌟 Product Highlights

- **Clinical Clarity & Reassurance:** High-contrast, clean medical UI designed with soft teal accents, generous breathing room, and optical comfort for recovering patients.
- **Verbatim Medication Verification:** Side-by-side split cards comparing the doctor's exact clinical order with simple, comforting patient instructions (dosage, schedule, food guidance, safety limits).
- **Hospital Red-Flag Protocol:** Priority-tiered warning sign detection (Immediate ER, Call 911, Contact Surgeon) with 1-tap call triggers.
- **Multilingual Support:** Instant translations in **English**, **Hindi (हिन्दी)**, and **Bengali (বাংলা)** while safeguarding clinical dosages and emergency numbers.
- **Interactive Recovery Checklist:** Dynamic adherence tracking, progress bar, 30-second exercise guidance video modal, and refrigerator printable checklist.
- **Meta Muse Spark:** Uses the configured Muse Spark API for document extraction. Synthetic clinical data is limited to the explicitly selected demo account; real document analysis errors are surfaced for verification.

---

## 🚀 Quick Start (Local Run)

### 1. Requirements
- Python 3.10+ (or use the built-in `.venv` environment)

### 2. Configure API Key
Copy `.env.example` to `.env` and add your Meta Model API key:
```bash
cp .env.example .env
# Set MODEL_API_KEY=your_meta_model_api_key
```
Without an API key, use the explicitly labeled demo account for synthetic data. Real document analysis requires a configured Muse Spark API key.

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
  --set-env-vars MODEL_API_KEY="YOUR_META_MODEL_API_KEY",MODEL_NAME="muse-spark-1.3",MODEL_API_BASE_URL="https://api.meta.ai/v1"
```

Cloud Run will automatically build the container using the provided `Dockerfile` and serve it on a secure HTTPS URL.

---

## 🛡️ Clinical AI Safety & Privacy Guarantees

1. **Untrusted Input Resilience:** Uploaded text is treated strictly as passive clinical data to prevent prompt injection.
2. **Preserve Verbatim Accuracy:** Exact medication names, dosages, and administration routes are never hallucinated or altered.
3. **No Treatment Discontinuation:** The AI explicitly advises patients never to stop or modify regimens without consulting their physician.
4. **Physician Precedence:** Hospital documentation and attending clinicians always take precedence over AI summaries.
5. **Zero Persistent Storage:** Uploaded summaries are processed in memory and never written to permanent disk storage.
