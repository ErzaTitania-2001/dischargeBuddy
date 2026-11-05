"""Idempotent appointment reminders delivered through Brevo."""
import argparse
import hashlib
import html
import re
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from email.utils import parseaddr
from typing import Callable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.config import settings
from app.services.auth_service import User, user_store


class BrevoDeliveryError(RuntimeError):
    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


def _valid_email(value: str) -> bool:
    address = parseaddr(value or "")[1]
    return bool(address and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", address))


def _appointment_date(appointment: dict) -> Optional[date]:
    for value in (appointment.get("date_sort_key"), appointment.get("date_time")):
        if not value:
            continue
        match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:$|[T\s])", str(value).strip())
        if match:
            try:
                return date.fromisoformat(match.group(1))
            except ValueError:
                return None
    return None


def _email_content(appointment: dict, scheduled_date: date) -> tuple[str, str, str]:
    subject = "Reminder: Your follow-up appointment is in 3 days"
    date_label = scheduled_date.strftime("%d %B %Y")
    time_value = appointment.get("appointment_time") or appointment.get("time_of_day")
    provider = appointment.get("provider")
    clinic = appointment.get("location")
    rows = [f"<p>Appointment date: {html.escape(date_label)}</p>"]
    text_rows = [f"Appointment date: {date_label}"]
    if time_value:
        rows.append(f"<p>Time: {html.escape(str(time_value))}</p>")
        text_rows.append(f"Time: {time_value}")
    if provider:
        rows.append(f"<p>Doctor / Department: {html.escape(str(provider))}</p>")
        text_rows.append(f"Doctor / Department: {provider}")
    if clinic:
        rows.append(f"<p>Hospital / Clinic: {html.escape(str(clinic))}</p>")
        text_rows.append(f"Hospital / Clinic: {clinic}")
    html_body = (
        "<html><body style='font-family:Arial,sans-serif;line-height:1.5;color:#172033'>"
        "<p>Hello,</p><p>This is a reminder that you have a follow-up appointment scheduled in three days.</p>"
        + "".join(rows)
        + f"<p>Please open <a href='{html.escape(settings.APP_BASE_URL, quote=True)}'>DischargeBuddy</a> to review your appointment details and care plan.</p>"
        + "<p>Regards,<br>DischargeBuddy</p></body></html>"
    )
    text_body = ("Hello,\n\nThis is a reminder that you have a follow-up appointment scheduled in three days.\n\n"
                 + "\n".join(text_rows) + f"\n\nPlease open {settings.APP_BASE_URL} to review your appointment details and care plan.\n\nRegards,\nDischargeBuddy")
    return subject, html_body, text_body


def send_brevo_email(recipient: str, subject: str, html_body: str, text_body: str,
                     idempotency_key: Optional[str] = None) -> str:
    if not settings.BREVO_API_KEY or not settings.BREVO_SENDER_EMAIL or not _valid_email(settings.BREVO_SENDER_EMAIL):
        raise BrevoDeliveryError("Brevo API key and a valid sender email must be configured.", retryable=False)
    payload = {
        "sender": {"name": settings.BREVO_SENDER_NAME, "email": settings.BREVO_SENDER_EMAIL},
        "to": [{"email": recipient}],
        "subject": subject,
        "htmlContent": html_body,
        "textContent": text_body,
    }
    if idempotency_key:
        payload["headers"] = {"IdempotencyKey": idempotency_key}
    try:
        response = httpx.post("https://api.brevo.com/v3/smtp/email", headers={
            "api-key": settings.BREVO_API_KEY, "accept": "application/json", "content-type": "application/json"
        }, json=payload, timeout=15)
    except httpx.RequestError as error:
        # The provider may have accepted a request before the connection timed out.
        raise TimeoutError("Brevo delivery result is unknown; not retrying to avoid a duplicate message.") from error
    if response.status_code >= 400:
        if "duplicate_parameter" in response.text.lower() and idempotency_key:
            return "brevo-idempotent-replay"
        raise BrevoDeliveryError(f"Brevo returned HTTP {response.status_code}: {response.text[:500]}",
                                 retryable=response.status_code in (425, 429) or response.status_code >= 500)
    return str(response.json().get("messageId") or "")


def dispatch_due_reminders(now: Optional[datetime] = None,
                           sender: Callable[[str, str, str, str], str] = send_brevo_email) -> dict:
    """Send reminders to opted-in, verified accounts whose local time is 9 AM."""
    if not settings.EMAIL_NOTIFICATIONS_ENABLED:
        return {"status": "disabled", "sent": 0, "failed": 0, "skipped": 0}
    if not settings.BREVO_API_KEY or not _valid_email(settings.BREVO_SENDER_EMAIL):
        raise RuntimeError("Brevo is enabled but BREVO_API_KEY or a valid BREVO_SENDER_EMAIL is missing.")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    results = {"status": "completed", "sent": 0, "failed": 0, "skipped": 0}
    for candidate in user_store.get_reminder_candidates():
        try:
            account_zone = ZoneInfo(candidate.get("timezone") or "Asia/Kolkata")
        except ZoneInfoNotFoundError:
            results["skipped"] += 1
            continue
        local_now = now.astimezone(account_zone)
        if local_now.hour != 9:
            continue
        appointment = candidate["appointment"]
        target_date = local_now.date() + timedelta(days=3)
        if appointment.get("completed") or appointment.get("cancelled"):
            continue
        if _appointment_date(appointment) != target_date:
            continue
        recipient = candidate.get("email", "")
        if not _valid_email(recipient):
            claim = user_store.start_reminder_delivery(candidate["account_id"], candidate["appointment_id"], local_now.date().isoformat())
            if claim:
                user_store.finish_reminder_delivery(claim["id"], "skipped", error="Account email is missing or invalid.")
            results["skipped"] += 1
            continue
        subject, body_html, body_text = _email_content(appointment, target_date)
        for attempt in range(3):
            claim = user_store.start_reminder_delivery(candidate["account_id"], candidate["appointment_id"], local_now.date().isoformat())
            if not claim:
                break
            try:
                if sender is send_brevo_email:
                    message_id = sender(recipient, subject, body_html, body_text, claim["id"])
                else:
                    message_id = sender(recipient, subject, body_html, body_text)
                user_store.finish_reminder_delivery(claim["id"], "sent", provider_message_id=message_id or None)
                results["sent"] += 1
                break
            except BrevoDeliveryError as error:
                retry = error.retryable and attempt < 2
                user_store.finish_reminder_delivery(claim["id"], "failed", retryable=retry, error=str(error))
                if retry:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                results["failed"] += 1
                break
            except TimeoutError as error:
                user_store.finish_reminder_delivery(claim["id"], "uncertain", error=str(error))
                results["failed"] += 1
                break
            except Exception as error:
                user_store.finish_reminder_delivery(claim["id"], "failed", error=str(error))
                results["failed"] += 1
                break
    return results


def create_verification_token(user: User) -> str:
    token = secrets.token_urlsafe(40)
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    user_store.create_email_verification(user.id, hashlib.sha256(token.encode()).hexdigest(), expires.isoformat())
    return token


def verify_email_token(token: str) -> Optional[User]:
    if not token or len(token) > 200:
        return None
    return user_store.verify_email_token(hashlib.sha256(token.encode()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run appointment reminder dispatch (for local development)")
    parser.add_argument("--run-once", action="store_true")
    args = parser.parse_args()
    if args.run_once:
        print(dispatch_due_reminders())
    else:
        parser.error("Use --run-once; schedule this command externally for reliable recurring delivery.")
