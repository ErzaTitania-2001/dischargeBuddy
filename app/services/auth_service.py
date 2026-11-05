"""Persistent account, session, and patient-data store.

SQLite is intended for local development and a single instance with a persistent
volume. Cloud deployments should use PostgreSQL through DATABASE_URL.
"""
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.config import settings
from app.models import DischargeAnalysisResponse, FollowUpTask


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_hex, expected_hex = encoded.split("$", 2)
        if algorithm != "pbkdf2_sha256":
            return hmac.compare_digest(encoded, hashlib.sha256(password.encode("utf-8")).hexdigest())
        actual = hash_password(password, bytes.fromhex(salt_hex)).split("$")[-1]
        return hmac.compare_digest(actual, expected_hex)
    except (ValueError, TypeError):
        return False


class User(BaseModel):
    id: str
    account_id: str
    email: str
    name: str
    preferred_language: str = "en"
    is_demo: bool = False
    email_notifications_enabled: bool = False
    email_verified: bool = False
    timezone: str = "Asia/Kolkata"
    created_at: str


class DocumentRecord(BaseModel):
    id: str
    title: str
    filename: Optional[str] = None
    uploaded_at: str
    raw_text: str = ""
    status: str = "uploaded"
    analysis: Optional[DischargeAnalysisResponse] = None
    pending_analysis: Optional[DischargeAnalysisResponse] = None
    pending_review_id: Optional[str] = None
    extraction_status: str = "pending"
    ai_status: str = "pending"
    error_detail: Optional[str] = None
    mime_type: Optional[str] = None
    storage_path: Optional[str] = Field(None, exclude=True)
    content_sha256: Optional[str] = None


class UserStore:
    def __init__(self, db_path: Optional[Path | str] = None):
        self.database_url = "" if db_path is not None else settings.DATABASE_URL
        self.db_path = Path(db_path or settings.DATABASE_PATH).resolve() if not self.database_url else None
        if self.db_path:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()
        self.reconcile_interrupted_processing()

    @contextmanager
    def _connect(self) -> sqlite3.Connection:
        if self.database_url:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as error:
                raise RuntimeError("DATABASE_URL requires the psycopg dependency") from error
            connection = psycopg.connect(self.database_url.replace("postgres://", "postgresql://", 1), row_factory=dict_row)
            class PostgresAdapter:
                def __init__(self, raw): self.raw = raw
                def execute(self, sql, params=()):
                    sql = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO").replace("?", "%s")
                    if "INSERT INTO schema_migrations" in sql and "ON CONFLICT" not in sql:
                        sql = sql.rstrip().rstrip(";") + " ON CONFLICT(version) DO NOTHING"
                    return self.raw.execute(sql, params)
                def executescript(self, script):
                    for statement in script.split(";"):
                        if statement.strip(): self.raw.execute(statement)
            adapter = PostgresAdapter(connection)
            try:
                yield adapter
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()
            return
        connection = sqlite3.connect(str(self.db_path), timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 20000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _migrate(self) -> None:
        with self._connect() as db:
            if not self.database_url:
                db.execute("PRAGMA journal_mode = WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                    email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
                    name TEXT NOT NULL, preferred_language TEXT NOT NULL DEFAULT 'en',
                    is_demo INTEGER NOT NULL DEFAULT 0,
                    email_notifications_enabled INTEGER NOT NULL DEFAULT 0,
                    email_verified INTEGER NOT NULL DEFAULT 0,
                    timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_users_account ON users(account_id);
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL, expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL, filename TEXT, uploaded_at TEXT NOT NULL, raw_text TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL, extraction_status TEXT NOT NULL, ai_status TEXT NOT NULL,
                    error_detail TEXT, mime_type TEXT, storage_path TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL, analysis_json TEXT, pending_analysis_json TEXT,
                    pending_review_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(account_id, content_sha256)
                );
                CREATE INDEX IF NOT EXISTS idx_documents_account_created ON documents(account_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS discharge_summaries (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                    document_id TEXT NOT NULL UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
                    data_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_summaries_account ON discharge_summaries(account_id);
                CREATE TABLE IF NOT EXISTS medicines (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    data_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_medicines_account ON medicines(account_id);
                CREATE INDEX IF NOT EXISTS idx_medicines_document ON medicines(document_id);
                CREATE TABLE IF NOT EXISTS appointments (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    data_json TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0, completed_at TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_appointments_account ON appointments(account_id);
                CREATE INDEX IF NOT EXISTS idx_appointments_document ON appointments(document_id);
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    data_json TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0, completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_account ON tasks(account_id);
                CREATE INDEX IF NOT EXISTS idx_tasks_document ON tasks(document_id);
                CREATE TABLE IF NOT EXISTS recovery_entries (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                    score INTEGER NOT NULL, note TEXT, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_recovery_account_created ON recovery_entries(account_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS handover_events (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                    data_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_handover_account_created ON handover_events(account_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS pending_reviews (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    data_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reminder_deliveries (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                    appointment_id TEXT NOT NULL, notification_type TEXT NOT NULL,
                    scheduled_send_date TEXT NOT NULL, attempt_timestamp TEXT NOT NULL,
                    delivery_status TEXT NOT NULL, provider_message_id TEXT, error_details TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 1, retryable INTEGER NOT NULL DEFAULT 0,
                    retry_deadline TEXT,
                    UNIQUE(appointment_id, notification_type, scheduled_send_date)
                );
                CREATE INDEX IF NOT EXISTS idx_reminders_account ON reminder_deliveries(account_id, attempt_timestamp DESC);
                CREATE TABLE IF NOT EXISTS email_verification_tokens (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL, created_at TEXT NOT NULL, used_at TEXT
                );
            """)
            if self.database_url:
                columns = {row["column_name"] for row in db.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='users'").fetchall()}
            else:
                columns = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}
            if "email_notifications_enabled" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN email_notifications_enabled INTEGER NOT NULL DEFAULT 0")
            if "timezone" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata'")
            if "email_verified" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
            if self.database_url:
                reminder_columns = {row["column_name"] for row in db.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='reminder_deliveries'").fetchall()}
            else:
                reminder_columns = {row["name"] for row in db.execute("PRAGMA table_info(reminder_deliveries)").fetchall()}
            if "retry_deadline" not in reminder_columns:
                db.execute("ALTER TABLE reminder_deliveries ADD COLUMN retry_deadline TEXT")
            db.execute("INSERT INTO schema_migrations(version, applied_at) VALUES(1, ?) ON CONFLICT(version) DO NOTHING", (self._now(),))
            db.execute("INSERT INTO schema_migrations(version, applied_at) VALUES(2, ?) ON CONFLICT(version) DO NOTHING", (self._now(),))
            db.execute("INSERT INTO schema_migrations(version, applied_at) VALUES(3, ?) ON CONFLICT(version) DO NOTHING", (self._now(),))

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _user(row: sqlite3.Row) -> User:
        return User(id=row["id"], account_id=row["account_id"], email=row["email"], name=row["name"],
                    preferred_language=row["preferred_language"], is_demo=bool(row["is_demo"]),
                    email_notifications_enabled=bool(row["email_notifications_enabled"]), timezone=row["timezone"],
                    email_verified=bool(row["email_verified"]),
                    created_at=row["created_at"])

    @staticmethod
    def _document_from_row(row: sqlite3.Row) -> DocumentRecord:
        analysis = DischargeAnalysisResponse.model_validate_json(row["analysis_json"]) if row["analysis_json"] else None
        pending = DischargeAnalysisResponse.model_validate_json(row["pending_analysis_json"]) if row["pending_analysis_json"] else None
        return DocumentRecord(id=row["id"], title=row["title"], filename=row["filename"], uploaded_at=row["uploaded_at"],
                              raw_text=row["raw_text"], status=row["status"], analysis=analysis,
                              pending_analysis=pending, pending_review_id=row["pending_review_id"],
                              extraction_status=row["extraction_status"], ai_status=row["ai_status"],
                              error_detail=row["error_detail"], mime_type=row["mime_type"],
                              storage_path=row["storage_path"], content_sha256=row["content_sha256"])

    def _create_account_user(self, db: sqlite3.Connection, email: str, password: str, name: str,
                             language: str, is_demo: bool = False, user_id: Optional[str] = None) -> User:
        user_id = user_id or f"user-{uuid.uuid4().hex}"
        now = self._now()
        created = datetime.now(timezone.utc).strftime("%b %d, %Y")
        db.execute("INSERT INTO accounts(id, created_at) VALUES(?, ?)", (user_id, now))
        db.execute("INSERT INTO users(id, account_id, email, password_hash, name, preferred_language, is_demo, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (user_id, user_id, email.lower(), hash_password(password), name, language, int(is_demo), created, now))
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return self._user(row)

    def _new_session(self, db: sqlite3.Connection, user_id: str) -> str:
        token = secrets.token_urlsafe(48)
        created = datetime.now(timezone.utc)
        expires = created + timedelta(days=settings.SESSION_TTL_DAYS)
        db.execute("INSERT INTO sessions(token, user_id, created_at, expires_at) VALUES(?, ?, ?, ?)",
                   (token, user_id, created.isoformat(), expires.isoformat()))
        return token

    def _init_demo_user(self) -> None:
        email = "demonstration@dischargebuddy.com"
        with self._connect() as db:
            if db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                return
            self._create_account_user(db, email, secrets.token_urlsafe(32), "Demonstration account", "en", True, "user-empty-demo")

    def reconcile_interrupted_processing(self) -> None:
        """Mark synchronous jobs interrupted by a process restart as retryable failures."""
        with self._connect() as db:
            db.execute("UPDATE documents SET status='failed',ai_status='failed',error_detail='Processing was interrupted by a server restart. Retry processing.',updated_at=? WHERE ai_status='processing'", (self._now(),))
            db.execute("UPDATE documents SET status='failed',extraction_status='failed',error_detail='Extraction was interrupted by a server restart. Retry extraction.',updated_at=? WHERE extraction_status='pending' AND status='uploaded'", (self._now(),))
            db.execute("UPDATE reminder_deliveries SET delivery_status='uncertain',retryable=0,error_details='Reminder process stopped before recording the provider result; automatic resend was suppressed to avoid a duplicate.' WHERE delivery_status='sending'")

    def register(self, email: str, password: str, name: str, preferred_language: str = "en") -> tuple[User, str]:
        clean_email = email.strip().lower()
        try:
            with self._connect() as db:
                user = self._create_account_user(db, clean_email, password, name.strip(), preferred_language)
                token = self._new_session(db, user.id)
            return user, token
        except Exception as exc:
            if isinstance(exc, sqlite3.IntegrityError) or exc.__class__.__name__ == "UniqueViolation":
                raise ValueError("An account with this email address already exists. Please sign in.") from exc
            raise

    def login(self, email: str, password: str) -> tuple[User, str]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
            if not row or not verify_password(password, row["password_hash"]):
                raise ValueError("Email or password is incorrect. Please try again.")
            token = self._new_session(db, row["id"])
            return self._user(row), token

    def demo_login(self) -> tuple[User, str]:
        # Each demo session gets its own durable account so one visitor cannot see
        # another visitor's uploaded clinical documents.
        with self._connect() as db:
            suffix = uuid.uuid4().hex
            user = self._create_account_user(db, f"demo+{suffix}@dischargebuddy.local",
                                             secrets.token_urlsafe(32), "Demonstration account", "en", True,
                                             f"user-demo-{suffix}")
            token = self._new_session(db, user.id)
            return user, token

    def get_user_by_token(self, token: Optional[str]) -> Optional[User]:
        if not token:
            return None
        with self._connect() as db:
            row = db.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires_at>?", (token, self._now())).fetchone()
            return self._user(row) if row else None

    def refresh_session(self, token: Optional[str]) -> tuple[Optional[User], Optional[str]]:
        user = self.get_user_by_token(token)
        if user and token:
            expires = (datetime.now(timezone.utc) + timedelta(days=settings.SESSION_TTL_DAYS)).isoformat()
            with self._connect() as db:
                db.execute("UPDATE sessions SET expires_at=? WHERE token=?", (expires, token))
        return (user, token) if user and token else (None, None)

    def logout(self, token: Optional[str]) -> None:
        if token:
            with self._connect() as db:
                db.execute("DELETE FROM sessions WHERE token=?", (token,))

    def update_profile(self, user_id: str, name: Optional[str] = None, preferred_language: Optional[str] = None,
                       email_notifications_enabled: Optional[bool] = None,
                       timezone_name: Optional[str] = None) -> User:
        with self._connect() as db:
            if name and name.strip():
                db.execute("UPDATE users SET name=?, updated_at=? WHERE id=?", (name.strip(), self._now(), user_id))
            if preferred_language in ("en", "hi", "bn"):
                db.execute("UPDATE users SET preferred_language=?, updated_at=? WHERE id=?", (preferred_language, self._now(), user_id))
            if email_notifications_enabled is not None:
                db.execute("UPDATE users SET email_notifications_enabled=?, updated_at=? WHERE id=?",
                           (int(email_notifications_enabled), self._now(), user_id))
            if timezone_name:
                db.execute("UPDATE users SET timezone=?, updated_at=? WHERE id=?", (timezone_name, self._now(), user_id))
            row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not row:
                raise ValueError("User not found")
            return self._user(row)

    def get_documents(self, user_id: str) -> List[DocumentRecord]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM documents WHERE account_id=(SELECT account_id FROM users WHERE id=?) ORDER BY created_at DESC", (user_id,)).fetchall()
            return [self._document_from_row(row) for row in rows]

    def get_document(self, user_id: str, doc_id: str) -> Optional[DocumentRecord]:
        with self._connect() as db:
            row = db.execute("SELECT d.* FROM documents d JOIN users u ON d.account_id=u.account_id WHERE u.id=? AND d.id=?", (user_id, doc_id)).fetchone()
            return self._document_from_row(row) if row else None

    def find_document_by_hash(self, user_id: str, content_hash: str) -> Optional[DocumentRecord]:
        with self._connect() as db:
            row = db.execute("SELECT d.* FROM documents d JOIN users u ON d.account_id=u.account_id WHERE u.id=? AND d.content_sha256=?", (user_id, content_hash)).fetchone()
            return self._document_from_row(row) if row else None

    def add_document(self, user_id: str, doc: DocumentRecord) -> tuple[DocumentRecord, bool]:
        now = self._now()
        self._scope_task_ids(doc)
        with self._connect() as db:
            user = db.execute("SELECT account_id FROM users WHERE id=?", (user_id,)).fetchone()
            if not user:
                raise ValueError("User not found")
            account_id = user["account_id"]
            if doc.content_sha256:
                existing = db.execute("SELECT * FROM documents WHERE account_id=? AND content_sha256=?", (account_id, doc.content_sha256)).fetchone()
                if existing:
                    return self._document_from_row(existing), False
            db.execute("""INSERT INTO documents(id,account_id,user_id,title,filename,uploaded_at,raw_text,status,
                extraction_status,ai_status,error_detail,mime_type,storage_path,content_sha256,analysis_json,
                pending_analysis_json,pending_review_id,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (doc.id, account_id, user_id, doc.title, doc.filename, doc.uploaded_at, doc.raw_text, doc.status,
                 doc.extraction_status, doc.ai_status, doc.error_detail, doc.mime_type, doc.storage_path or "",
                 doc.content_sha256 or secrets.token_hex(32), doc.analysis.model_dump_json() if doc.analysis else None,
                 doc.pending_analysis.model_dump_json() if doc.pending_analysis else None, doc.pending_review_id, now, now))
            if doc.analysis:
                self._replace_tasks(db, account_id, doc)
                self._persist_extracted_data(db, account_id, doc)
            row = db.execute("SELECT * FROM documents WHERE id=?", (doc.id,)).fetchone()
            return self._document_from_row(row), True

    def update_document(self, user_id: str, doc: DocumentRecord) -> Optional[DocumentRecord]:
        self._scope_task_ids(doc)
        with self._connect() as db:
            user = db.execute("SELECT account_id FROM users WHERE id=?", (user_id,)).fetchone()
            if not user:
                return None
            db.execute("""UPDATE documents SET title=?,filename=?,uploaded_at=?,raw_text=?,status=?,
                extraction_status=?,ai_status=?,error_detail=?,mime_type=?,storage_path=?,content_sha256=?,
                analysis_json=?,pending_analysis_json=?,pending_review_id=?,updated_at=?
                WHERE id=? AND account_id=?""",
                (doc.title, doc.filename, doc.uploaded_at, doc.raw_text, doc.status, doc.extraction_status,
                 doc.ai_status, doc.error_detail, doc.mime_type, doc.storage_path or "", doc.content_sha256 or "",
                 doc.analysis.model_dump_json() if doc.analysis else None,
                 doc.pending_analysis.model_dump_json() if doc.pending_analysis else None, doc.pending_review_id,
                 self._now(), doc.id, user["account_id"]))
            if doc.analysis:
                self._replace_tasks(db, user["account_id"], doc)
                self._persist_extracted_data(db, user["account_id"], doc)
            row = db.execute("SELECT * FROM documents WHERE id=? AND account_id=?", (doc.id, user["account_id"])).fetchone()
            return self._document_from_row(row) if row else None

    def _replace_tasks(self, db: sqlite3.Connection, account_id: str, doc: DocumentRecord) -> None:
        old_rows = db.execute("SELECT data_json,completed,completed_at FROM tasks WHERE document_id=?", (doc.id,)).fetchall()
        old_state = {}
        for row in old_rows:
            old_task = FollowUpTask.model_validate_json(row["data_json"])
            old_state[self._task_identity(old_task)] = (bool(row["completed"]), row["completed_at"])
        db.execute("DELETE FROM tasks WHERE document_id=?", (doc.id,))
        for index, task in enumerate(doc.analysis.follow_up_tasks if doc.analysis else []):
            task.document_id = doc.id
            identity = self._task_identity(task)
            task.id = f"{doc.id}-{hashlib.sha256(f'{identity}|{index}'.encode()).hexdigest()[:20]}"
            if identity in old_state:
                task.completed, task.completed_at = old_state[identity]
            db.execute("INSERT INTO tasks(id,account_id,document_id,data_json,completed,completed_at) VALUES(?,?,?,?,?,?)",
                       (task.id, account_id, doc.id, task.model_dump_json(), int(task.completed), task.completed_at))

    @staticmethod
    def _task_identity(task: FollowUpTask) -> str:
        return "|".join((re.sub(r"\s+", " ", task.title.casefold()).strip(), task.type,
                         re.sub(r"\s+", " ", (task.date_sort_key or task.date_time or "").casefold()).strip(),
                         re.sub(r"\s+", " ", (task.provider or "").casefold()).strip()))

    def _persist_extracted_data(self, db: sqlite3.Connection, account_id: str, doc: DocumentRecord) -> None:
        if not doc.analysis:
            return
        now = self._now()
        db.execute("""INSERT INTO discharge_summaries(id,account_id,document_id,data_json,created_at,updated_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(document_id) DO UPDATE SET data_json=excluded.data_json,updated_at=excluded.updated_at""",
            (f"summary-{doc.id}", account_id, doc.id, doc.analysis.model_dump_json(), now, now))
        db.execute("DELETE FROM medicines WHERE document_id=?", (doc.id,))
        for index, medicine in enumerate(doc.analysis.medication_instructions):
            db.execute("INSERT INTO medicines(id,account_id,document_id,data_json,created_at) VALUES(?,?,?,?,?)",
                       (f"{doc.id}-medicine-{index}", account_id, doc.id, medicine.model_dump_json(), now))
        db.execute("DELETE FROM appointments WHERE document_id=?", (doc.id,))
        for task in doc.analysis.follow_up_tasks:
            if task.type == "appointment":
                db.execute("INSERT INTO appointments(id,account_id,document_id,data_json,completed,completed_at,created_at) VALUES(?,?,?,?,?,?,?)",
                           (task.id, account_id, doc.id, task.model_dump_json(), int(task.completed), task.completed_at, now))

    @staticmethod
    def _scope_task_ids(doc: DocumentRecord) -> None:
        if not doc.analysis:
            return
        for index, task in enumerate(doc.analysis.follow_up_tasks):
            task.document_id = doc.id
            identity = UserStore._task_identity(task)
            task.id = f"{doc.id}-{hashlib.sha256(f'{identity}|{index}'.encode()).hexdigest()[:20]}"

    def remove_document(self, user_id: str, doc_id: str) -> tuple[bool, int, int, Optional[str]]:
        with self._connect() as db:
            account = db.execute("SELECT account_id FROM users WHERE id=?", (user_id,)).fetchone()
            row = db.execute("SELECT storage_path FROM documents WHERE id=? AND account_id=?", (doc_id, account["account_id"] if account else "")).fetchone()
            if not row:
                return False, self._count(db, "documents", account["account_id"] if account else ""), self._count(db, "tasks", account["account_id"] if account else ""), None
            file_path = row["storage_path"]
            db.execute("DELETE FROM documents WHERE id=? AND account_id=?", (doc_id, account["account_id"]))
            return True, self._count(db, "documents", account["account_id"]), self._count(db, "tasks", account["account_id"]), file_path

    @staticmethod
    def _count(db: sqlite3.Connection, table: str, account_id: str) -> int:
        return int(db.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE account_id=?", (account_id,)).fetchone()["count"])

    def get_tasks(self, user_id: str) -> List[FollowUpTask]:
        with self._connect() as db:
            rows = db.execute("SELECT t.* FROM tasks t JOIN users u ON t.account_id=u.account_id WHERE u.id=? ORDER BY t.document_id, t.id", (user_id,)).fetchall()
            result = []
            for row in rows:
                task = FollowUpTask.model_validate_json(row["data_json"])
                task.completed = bool(row["completed"])
                task.completed_at = row["completed_at"]
                result.append(task)
            return result

    def get_reminder_candidates(self) -> List[dict]:
        with self._connect() as db:
            rows = db.execute("""SELECT a.id AS appointment_id,a.account_id,a.data_json,u.id AS user_id,
                u.email,u.email_verified,u.email_notifications_enabled,u.timezone
                FROM appointments a JOIN users u ON u.account_id=a.account_id
                WHERE a.completed=0 AND u.email_notifications_enabled=1 AND u.email_verified=1""").fetchall()
            return [{**dict(row), "appointment": json.loads(row["data_json"])} for row in rows]

    def create_email_verification(self, user_id: str, token_hash: str, expires_at: str) -> bool:
        with self._connect() as db:
            if not db.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
                return False
            db.execute("UPDATE email_verification_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL",
                       (self._now(), user_id))
            db.execute("INSERT INTO email_verification_tokens(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)",
                       (token_hash, user_id, expires_at, self._now()))
            return True

    def verify_email_token(self, token_hash: str) -> Optional[User]:
        with self._connect() as db:
            row = db.execute("SELECT user_id FROM email_verification_tokens WHERE token_hash=? AND used_at IS NULL AND expires_at>?",
                             (token_hash, self._now())).fetchone()
            if not row:
                return None
            user_id = row["user_id"]
            db.execute("UPDATE email_verification_tokens SET used_at=? WHERE token_hash=?", (self._now(), token_hash))
            db.execute("UPDATE users SET email_verified=1,updated_at=? WHERE id=?", (self._now(), user_id))
            return self._user(db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())

    def start_reminder_delivery(self, account_id: str, appointment_id: str, send_date: str) -> Optional[dict]:
        now = self._now()
        retry_deadline = (datetime.now(timezone.utc) + timedelta(minutes=25)).isoformat()
        notification_type = "appointment_3_day_reminder"
        with self._connect() as db:
            result = db.execute("""INSERT INTO reminder_deliveries
                (id,account_id,appointment_id,notification_type,scheduled_send_date,attempt_timestamp,delivery_status,attempt_count,retryable,retry_deadline)
                VALUES(?,?,?,?,?,?,'sending',1,0,?)
                ON CONFLICT(appointment_id,notification_type,scheduled_send_date) DO NOTHING""",
                (str(uuid.uuid4()), account_id, appointment_id, notification_type, send_date, now, retry_deadline))
            if result.rowcount == 1:
                row = db.execute("SELECT * FROM reminder_deliveries WHERE appointment_id=? AND notification_type=? AND scheduled_send_date=?",
                                 (appointment_id, notification_type, send_date)).fetchone()
                return dict(row)
            existing = db.execute("SELECT * FROM reminder_deliveries WHERE appointment_id=? AND notification_type=? AND scheduled_send_date=?",
                                  (appointment_id, notification_type, send_date)).fetchone()
            if not existing or existing["delivery_status"] != "failed" or not existing["retryable"] or not existing["retry_deadline"] or existing["retry_deadline"] <= now:
                return None
            updated = db.execute("""UPDATE reminder_deliveries SET attempt_timestamp=?,delivery_status='sending',
                attempt_count=attempt_count+1,retryable=0,error_details=NULL
                WHERE id=? AND delivery_status='failed' AND retryable=1""", (now, existing["id"]))
            if updated.rowcount != 1:
                return None
            return dict(db.execute("SELECT * FROM reminder_deliveries WHERE id=?", (existing["id"],)).fetchone())

    def finish_reminder_delivery(self, delivery_id: str, status: str, retryable: bool = False,
                                 provider_message_id: Optional[str] = None, error: Optional[str] = None) -> None:
        with self._connect() as db:
            db.execute("""UPDATE reminder_deliveries SET delivery_status=?,retryable=?,
                provider_message_id=?,error_details=? WHERE id=?""",
                (status, int(retryable), provider_message_id, error[:2000] if error else None, delivery_id))

    def get_reminder_deliveries(self, user_id: str) -> List[dict]:
        with self._connect() as db:
            rows = db.execute("""SELECT n.* FROM reminder_deliveries n JOIN users u ON u.account_id=n.account_id
                WHERE u.id=? ORDER BY n.attempt_timestamp DESC LIMIT 20""", (user_id,)).fetchall()
            return [dict(row) for row in rows]

    def toggle_task(self, user_id: str, task_id: str) -> Optional[FollowUpTask]:
        with self._connect() as db:
            user = db.execute("SELECT account_id FROM users WHERE id=?", (user_id,)).fetchone()
            if not user:
                return None
            row = db.execute("SELECT * FROM tasks WHERE account_id=? AND id=?", (user["account_id"], task_id)).fetchone()
            if not row:
                return None
            completed = not bool(row["completed"])
            completed_at = self._now() if completed else None
            task = FollowUpTask.model_validate_json(row["data_json"])
            task.completed = completed
            task.completed_at = completed_at
            db.execute("UPDATE tasks SET completed=?,completed_at=?,data_json=? WHERE id=?",
                       (int(completed), completed_at, task.model_dump_json(), task_id))
            appointment_row = db.execute("SELECT data_json FROM appointments WHERE id=?", (task_id,)).fetchone()
            if appointment_row:
                appointment_data = FollowUpTask.model_validate_json(appointment_row["data_json"])
                appointment_data.completed = completed
                appointment_data.completed_at = completed_at
                db.execute("UPDATE appointments SET completed=?,completed_at=?,data_json=? WHERE id=?",
                           (int(completed), completed_at, appointment_data.model_dump_json(), task_id))
            doc_row = db.execute("SELECT analysis_json FROM documents WHERE id=? AND account_id=?",
                                 (row["document_id"], user["account_id"])).fetchone()
            if doc_row and doc_row["analysis_json"]:
                analysis = DischargeAnalysisResponse.model_validate_json(doc_row["analysis_json"])
                for analysis_task in analysis.follow_up_tasks:
                    if analysis_task.id == task_id:
                        analysis_task.completed = completed
                        analysis_task.completed_at = completed_at
                db.execute("UPDATE documents SET analysis_json=?,updated_at=? WHERE id=? AND account_id=?",
                           (analysis.model_dump_json(), self._now(), row["document_id"], user["account_id"]))
                db.execute("UPDATE discharge_summaries SET data_json=?,updated_at=? WHERE document_id=? AND account_id=?",
                           (analysis.model_dump_json(), self._now(), row["document_id"], user["account_id"]))
            return task

    def add_pain_entry(self, user_id: str, score: int, note: Optional[str] = None) -> dict:
        entry = {"id": f"pain-{uuid.uuid4().hex}", "score": score, "note": note, "created_at": self._now()}
        with self._connect() as db:
            account = db.execute("SELECT account_id FROM users WHERE id=?", (user_id,)).fetchone()
            if not account:
                raise ValueError("User not found")
            db.execute("INSERT INTO recovery_entries(id,account_id,score,note,created_at) VALUES(?,?,?,?,?)",
                       (entry["id"], account["account_id"], score, note, entry["created_at"]))
        return entry

    def get_pain_entries(self, user_id: str) -> List[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT r.* FROM recovery_entries r JOIN users u ON r.account_id=u.account_id WHERE u.id=? ORDER BY r.created_at DESC", (user_id,)).fetchall()
            return [{"id": row["id"], "score": row["score"], "note": row["note"], "created_at": row["created_at"]} for row in rows]

    def add_handover_event(self, user_id: str, event: dict) -> dict:
        saved = {"id": f"handover-{uuid.uuid4().hex}", "created_at": self._now(), **event}
        with self._connect() as db:
            account = db.execute("SELECT account_id FROM users WHERE id=?", (user_id,)).fetchone()
            if not account:
                raise ValueError("User not found")
            db.execute("INSERT INTO handover_events(id,account_id,data_json,created_at) VALUES(?,?,?,?)",
                       (saved["id"], account["account_id"], json.dumps(saved), saved["created_at"]))
        return saved

    def get_handover_events(self, user_id: str) -> List[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT h.data_json FROM handover_events h JOIN users u ON h.account_id=u.account_id WHERE u.id=? ORDER BY h.created_at DESC", (user_id,)).fetchall()
            return [json.loads(row["data_json"]) for row in rows]

    def add_pending_review(self, user_id: str, review: dict) -> str:
        review_id = f"review-{uuid.uuid4().hex}"
        data = json.dumps(review)
        with self._connect() as db:
            document = db.execute("SELECT id FROM documents WHERE id=? AND user_id=?", (review["document_id"], user_id)).fetchone()
            if not document:
                raise ValueError("Document not found for this account")
            db.execute("DELETE FROM pending_reviews WHERE document_id=? AND user_id=?", (review["document_id"], user_id))
            db.execute("INSERT INTO pending_reviews(id,user_id,document_id,data_json,created_at) VALUES(?,?,?,?,?)",
                       (review_id, user_id, review["document_id"], data, self._now()))
            db.execute("UPDATE documents SET pending_analysis_json=?,pending_review_id=?,status='reviewing',ai_status='reviewing',updated_at=? WHERE id=? AND user_id=?",
                       (json.dumps(review["analysis"]), review_id, self._now(), review["document_id"], user_id))
        return review_id

    def get_pending_review(self, user_id: str, review_id: str) -> Optional[dict]:
        with self._connect() as db:
            row = db.execute("SELECT data_json FROM pending_reviews WHERE id=? AND user_id=?", (review_id, user_id)).fetchone()
            return json.loads(row["data_json"]) if row else None

    def complete_pending_review(self, user_id: str, review_id: str, analysis: DischargeAnalysisResponse) -> Optional[DocumentRecord]:
        with self._connect() as db:
            pending = db.execute("SELECT document_id FROM pending_reviews WHERE id=? AND user_id=?", (review_id, user_id)).fetchone()
            if not pending:
                return None
            doc_row = db.execute("SELECT * FROM documents WHERE id=? AND user_id=?", (pending["document_id"], user_id)).fetchone()
            if not doc_row:
                return None
            doc = self._document_from_row(doc_row)
            doc.analysis = analysis
            self._scope_task_ids(doc)
            doc.pending_analysis = None
            doc.pending_review_id = None
            doc.status = "completed"
            doc.ai_status = "completed"
            doc.error_detail = None
            db.execute("UPDATE documents SET analysis_json=?,pending_analysis_json=NULL,pending_review_id=NULL,status='completed',ai_status='completed',error_detail=NULL,updated_at=? WHERE id=? AND user_id=?",
                       (analysis.model_dump_json(), self._now(), doc.id, user_id))
            db.execute("DELETE FROM pending_reviews WHERE id=? AND user_id=?", (review_id, user_id))
            self._replace_tasks(db, doc_row["account_id"], doc)
            self._persist_extracted_data(db, doc_row["account_id"], doc)
            return doc

    def discard_pending_review(self, user_id: str, review_id: str) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT document_id FROM pending_reviews WHERE id=? AND user_id=?", (review_id, user_id)).fetchone()
            if not row:
                return False
            db.execute("DELETE FROM pending_reviews WHERE id=? AND user_id=?", (review_id, user_id))
            db.execute("UPDATE documents SET pending_analysis_json=NULL,pending_review_id=NULL,status='uploaded',ai_status='pending',updated_at=? WHERE id=? AND user_id=?",
                       (self._now(), row["document_id"], user_id))
            return True


user_store = UserStore()
