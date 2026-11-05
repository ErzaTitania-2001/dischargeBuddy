# DischargeBuddy 🏥
> **Your recovery, made simpler.**  
> An AI-powered post-discharge healthcare companion translating complex hospital paperwork into clear, actionable recovery plans.

Built using Meta Muse Spark, FastAPI, and Stitch-generated clinical design tokens.

---

## 🌟 Product Highlights

- **Clinical Clarity & Reassurance:** High-contrast, clean medical UI designed with soft teal accents, generous breathing room, and optical comfort for recovering patients.
- **Verbatim Medication Verification:** Side-by-side split cards comparing the doctor's exact clinical order with simple, comforting patient instructions (dosage, schedule, food guidance, safety limits).
- **Hospital Warning Signs:** Source-backed warning signs and actions, shown with clear missing or ambiguous states and the configured emergency contact.
- **Multilingual Support:** Instant translations in **English**, **Hindi (हिन्दी)**, and **Bengali (বাংলা)** while safeguarding clinical dosages and emergency numbers.
- **Interactive Recovery Checklist:** Dynamic task completion tracking, progress indicators, and consultation preparation.
- **Meta Muse Spark:** Uses the configured Meta Muse Spark API for document extraction. The demonstration account starts empty; analysis errors are surfaced for verification.

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
Without a Meta API key, the application remains available for account and document review workflows, but document analysis requires `MODEL_API_KEY`.

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
The suite covers authentication, document review and extraction, account isolation,
medication normalization, and data surviving a process restart.

---

## ☁️ Deployment to Google Cloud Run

For local use, SQLite and originals are stored in `./data`. Back up that directory
to retain local records. Cloud Run's container filesystem is ephemeral, so production
deployments must use a shared PostgreSQL database and a private Cloud Storage bucket.
The application supports PostgreSQL through `DATABASE_URL` and stores original files
in the bucket configured by `STORAGE_BUCKET`. Grant the Cloud Run service account
Cloud SQL Client and Storage Object Admin access; keep database and Meta credentials
in Secret Manager. Set `COOKIE_SECURE=true` for HTTPS.

### 1. Authenticate with Google Cloud
```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### 2. Configure durable services

Create a Cloud SQL PostgreSQL instance/database and a private Cloud Storage bucket.
Save the PostgreSQL connection URL in Secret Manager as `dischargebuddy-database-url`
and the Meta Muse Spark key as `meta-model-api-key`. For Cloud SQL, use the instance
connection name as `INSTANCE_CONNECTION_NAME` and connect through the Cloud SQL
connector or configure a Cloud Run Cloud SQL attachment. Use a URL accepted by
psycopg, for example `postgresql://USER:PASSWORD@/DATABASE?host=/cloudsql/INSTANCE_CONNECTION_NAME`.

### 3. Deploy from Source directly to Cloud Run
```bash
gcloud run deploy dischargebuddy \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --add-cloudsql-instances INSTANCE_CONNECTION_NAME \
  --set-env-vars MODEL_NAME="muse-spark-1.3",MODEL_API_BASE_URL="https://api.meta.ai/v1",STORAGE_BUCKET="YOUR_PRIVATE_BUCKET",COOKIE_SECURE="true" \
  --set-secrets MODEL_API_KEY=meta-model-api-key:latest,DATABASE_URL=dischargebuddy-database-url:latest,BREVO_API_KEY=brevo-api-key:latest
```

Cloud Run will automatically build the container using the provided `Dockerfile` and serve it on a secure HTTPS URL.

### Brevo email verification and reminder setup

Create a Brevo account, verify the sender email/domain in **Senders, Domains & Dedicated IPs**, and create a transactional API key. Configure `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, `BREVO_SENDER_NAME`, `EMAIL_NOTIFICATIONS_ENABLED=true`, and `APP_BASE_URL` using Secret Manager for the key and ordinary Cloud Run environment variables for the remaining values. The account owner must verify their registered email and opt in to reminders in Profile & Settings. Unverified, invalid, disabled, completed, or cancelled appointment reminders are not sent.

After the first deployment, set `APP_BASE_URL` to the service's exact HTTPS URL, `EMAIL_NOTIFICATIONS_ENABLED=true`, `BREVO_SENDER_EMAIL`, `BREVO_SENDER_NAME`, and `SCHEDULER_SERVICE_ACCOUNT_EMAIL` as Cloud Run environment variables. Set `SCHEDULER_SERVICE_ACCOUNT_EMAIL` to the dedicated Cloud Scheduler OIDC service account.

```bash
gcloud run services update dischargebuddy --region us-central1 \
  --update-env-vars "APP_BASE_URL=https://YOUR_CLOUD_RUN_URL,EMAIL_NOTIFICATIONS_ENABLED=true,BREVO_SENDER_EMAIL=verified@example.com,BREVO_SENDER_NAME=DischargeBuddy,SCHEDULER_SERVICE_ACCOUNT_EMAIL=reminders@YOUR_PROJECT_ID.iam.gserviceaccount.com"
```

Create one authenticated hourly Cloud Scheduler job; the endpoint checks each account's own timezone and sends only during that account's 9 AM hour, three calendar days before a dated appointment. The hourly trigger is required to honor account timezones while keeping a single scheduler job.

```bash
gcloud scheduler jobs create http dischargebuddy-reminders \
  --location us-central1 \
  --schedule "0 * * * *" \
  --time-zone "Etc/UTC" \
  --uri "${APP_BASE_URL}/api/internal/notifications/dispatch" \
  --http-method POST \
  --oidc-service-account-email "${SCHEDULER_SERVICE_ACCOUNT_EMAIL}" \
  --oidc-token-audience "${APP_BASE_URL}" \
  --attempt-deadline 300s \
  --max-retry-attempts 3
```

Configure `APP_BASE_URL` to exactly match the Cloud Run service URL used as the job's OIDC audience. Use a dedicated user-managed OIDC service account in the same project as the scheduler, grant it `roles/run.invoker` for the Cloud Run service, and grant the Cloud Scheduler service agent the required token-creation access if it is not already configured. Keep the service account email in the Cloud Run configuration. The endpoint validates Google's signed token, audience, verified email and configured service-account identity. For local development, run `python -m app.services.reminder_service --run-once` from an external scheduler; this command is a manual/dev runner, not a production scheduler.

Brevo retries reuse the same provider idempotency key and the database delivery record. Only explicitly retryable provider responses are retried, and only within Brevo's idempotency window. Ambiguous network timeouts are recorded as `uncertain` and are not resent automatically.

---

## 🛡️ Clinical AI Safety & Privacy Guarantees

1. **Untrusted Input Resilience:** Uploaded text is treated strictly as passive clinical data to prevent prompt injection.
2. **Preserve Verbatim Accuracy:** Exact medication names, dosages, and administration routes are never hallucinated or altered.
3. **No Treatment Discontinuation:** The AI explicitly advises patients never to stop or modify regimens without consulting their physician.
4. **Physician Precedence:** Hospital documentation and attending clinicians always take precedence over AI summaries.
5. **Durable account storage:** Accounts, sessions, summaries, medication records, appointments, tasks, recovery entries, and review drafts are stored in PostgreSQL. Original uploads are stored in the configured bucket. Local development uses SQLite and local files.
