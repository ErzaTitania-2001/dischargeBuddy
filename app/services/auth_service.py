import uuid
import hashlib
from datetime import datetime, timezone
from typing import Dict, Optional, List
from pydantic import BaseModel
from app.models import DischargeAnalysisResponse, FollowUpTask
from app.services.sample_data import get_sample_discharge_data, SAMPLE_DISCHARGE_TEXT

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

class User(BaseModel):
    id: str
    email: str
    name: str
    preferred_language: str = "en"
    is_demo: bool = False
    created_at: str

class DocumentRecord(BaseModel):
    id: str
    title: str
    filename: Optional[str] = None
    uploaded_at: str
    raw_text: str
    status: str = "processed"  # "extracted", "reviewing", "processed", "error"
    analysis: Optional[DischargeAnalysisResponse] = None

class UserStore:
    def __init__(self):
        self.users: Dict[str, User] = {}  # user_id -> User
        self.passwords: Dict[str, str] = {}  # email -> hashed_password
        self.email_to_id: Dict[str, str] = {}  # email -> user_id
        self.sessions: Dict[str, str] = {}  # session_token -> user_id
        self.user_documents: Dict[str, List[DocumentRecord]] = {}  # user_id -> List[DocumentRecord]
        self.user_tasks: Dict[str, List[FollowUpTask]] = {}  # user_id -> List[FollowUpTask]

        # Initialize demo user
        self._init_demo_user()

    def _init_demo_user(self):
        demo_id = "user-demo-sarah"
        demo_email = "demo@dischargebuddy.com"
        demo_user = User(
            id=demo_id,
            email=demo_email,
            name="Sarah Jenkins (Demo)",
            preferred_language="en",
            is_demo=True,
            created_at=datetime.now(timezone.utc).strftime("%b %d, %Y")
        )
        self.users[demo_id] = demo_user
        self.passwords[demo_email] = hash_password("demo123")
        self.email_to_id[demo_email] = demo_id

        # Preload synthetic sample document for demo user
        sample_analysis = get_sample_discharge_data("en")
        demo_doc = DocumentRecord(
            id="doc-demo-knee",
            title="Knee Arthroscopy Discharge Packet",
            filename="knee_arthroscopy_discharge.pdf",
            uploaded_at=datetime.now(timezone.utc).strftime("%b %d, %Y • %I:%M %p"),
            raw_text=SAMPLE_DISCHARGE_TEXT.strip(),
            status="processed",
            analysis=sample_analysis
        )
        self.user_documents[demo_id] = [demo_doc]
        demo_tasks = []
        for task in sample_analysis.follow_up_tasks:
            t = task.model_copy()
            t.document_id = demo_doc.id
            demo_tasks.append(t)
        self.user_tasks[demo_id] = demo_tasks

    def register(self, email: str, password: str, name: str, preferred_language: str = "en") -> tuple[User, str]:
        email_clean = email.strip().lower()
        if email_clean in self.email_to_id:
            raise ValueError("An account with this email address already exists. Please sign in.")
        
        user_id = f"user-{uuid.uuid4().hex[:8]}"
        user = User(
            id=user_id,
            email=email_clean,
            name=name.strip(),
            preferred_language=preferred_language,
            is_demo=False,
            created_at=datetime.now(timezone.utc).strftime("%b %d, %Y")
        )
        self.users[user_id] = user
        self.passwords[email_clean] = hash_password(password)
        self.email_to_id[email_clean] = user_id
        
        # New users start with EMPTY documents and EMPTY tasks!
        self.user_documents[user_id] = []
        self.user_tasks[user_id] = []

        token = f"sess-{uuid.uuid4().hex}"
        self.sessions[token] = user_id
        return user, token

    def login(self, email: str, password: str) -> tuple[User, str]:
        email_clean = email.strip().lower()
        if email_clean not in self.email_to_id:
            raise ValueError("No account found with this email. Please check your spelling or sign up.")
        
        expected_hash = self.passwords.get(email_clean)
        if expected_hash != hash_password(password):
            raise ValueError("Incorrect password. Please try again.")

        user_id = self.email_to_id[email_clean]
        user = self.users[user_id]
        token = f"sess-{uuid.uuid4().hex}"
        self.sessions[token] = user_id
        return user, token

    def demo_login(self) -> tuple[User, str]:
        user_id = "user-demo-sarah"
        # Reset or ensure demo data is present
        if user_id not in self.users:
            self._init_demo_user()
        user = self.users[user_id]
        token = f"sess-{uuid.uuid4().hex}"
        self.sessions[token] = user_id
        return user, token

    def get_user_by_token(self, token: Optional[str]) -> Optional[User]:
        if not token or token not in self.sessions:
            return None
        user_id = self.sessions[token]
        return self.users.get(user_id)

    def logout(self, token: Optional[str]):
        if token and token in self.sessions:
            del self.sessions[token]

    def update_profile(self, user_id: str, name: Optional[str] = None, preferred_language: Optional[str] = None) -> User:
        user = self.users.get(user_id)
        if not user:
            raise ValueError("User not found")
        if name and name.strip():
            user.name = name.strip()
        if preferred_language and preferred_language in ["en", "hi", "bn"]:
            user.preferred_language = preferred_language
        return user

    def get_documents(self, user_id: str) -> List[DocumentRecord]:
        return self.user_documents.get(user_id, [])

    def get_document(self, user_id: str, doc_id: str) -> Optional[DocumentRecord]:
        docs = self.user_documents.get(user_id, [])
        for d in docs:
            if d.id == doc_id:
                return d
        return None

    def add_document(self, user_id: str, doc: DocumentRecord):
        if user_id not in self.user_documents:
            self.user_documents[user_id] = []
        self.user_documents[user_id].insert(0, doc)

        # Merge new follow-up tasks into user tasks and tag with document_id
        if doc.analysis and doc.analysis.follow_up_tasks:
            if user_id not in self.user_tasks:
                self.user_tasks[user_id] = []
            
            existing_ids = {t.id for t in self.user_tasks[user_id]}
            for task in doc.analysis.follow_up_tasks:
                t = task.model_copy()
                t.document_id = doc.id
                if t.id not in existing_ids:
                    self.user_tasks[user_id].append(t)

    def remove_document(self, user_id: str, doc_id: str) -> tuple[bool, int, int]:
        """
        Removes a document owned by user_id and cleans up tasks exclusively owned by that document.
        Returns (success, remaining_docs_count, remaining_tasks_count).
        """
        if user_id not in self.user_documents:
            return False, 0, 0
        
        target_doc = None
        for d in self.user_documents[user_id]:
            if d.id == doc_id:
                target_doc = d
                break
        
        if not target_doc:
            return False, len(self.user_documents.get(user_id, [])), len(self.user_tasks.get(user_id, []))
        
        # 1. Remove the document from user's document list
        self.user_documents[user_id] = [d for d in self.user_documents[user_id] if d.id != doc_id]

        # 2. Identify task IDs generated by this document
        doc_task_ids = set()
        if target_doc.analysis and target_doc.analysis.follow_up_tasks:
            doc_task_ids = {t.id for t in target_doc.analysis.follow_up_tasks}

        # 3. Identify task IDs that are still required by remaining documents
        remaining_shared_task_ids = set()
        for remaining_doc in self.user_documents[user_id]:
            if remaining_doc.analysis and remaining_doc.analysis.follow_up_tasks:
                for t in remaining_doc.analysis.follow_up_tasks:
                    remaining_shared_task_ids.add(t.id)

        # 4. Filter user tasks: keep task if it does not belong exclusively to removed document
        if user_id in self.user_tasks:
            self.user_tasks[user_id] = [
                task for task in self.user_tasks[user_id]
                if (task.document_id != doc_id and task.id not in doc_task_ids) or (task.id in remaining_shared_task_ids)
            ]

        remaining_docs_count = len(self.user_documents[user_id])
        remaining_tasks_count = len(self.user_tasks.get(user_id, []))
        return True, remaining_docs_count, remaining_tasks_count

    def get_tasks(self, user_id: str) -> List[FollowUpTask]:
        return self.user_tasks.get(user_id, [])

    def toggle_task(self, user_id: str, task_id: str) -> Optional[FollowUpTask]:
        tasks = self.user_tasks.get(user_id, [])
        for t in tasks:
            if t.id == task_id:
                t.completed = not t.completed
                return t
        return None

user_store = UserStore()
