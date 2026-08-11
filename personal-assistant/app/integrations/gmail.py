"""Gmail API wrapper — read, search, summarize, draft."""
import base64
import logging
from email.mime.text import MIMEText
from typing import Optional

from googleapiclient.discovery import build

from app.integrations.oauth import get_credentials

logger = logging.getLogger(__name__)


def _gmail_service(creds):
    return build("gmail", "v1", credentials=creds)


async def search_emails(user_id: int, query: str, max_results: int = 10) -> list[dict]:
    creds = await get_credentials(user_id)
    if not creds:
        raise PermissionError("Google account not connected.")
    service = _gmail_service(creds)
    result = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    messages = result.get("messages", [])
    emails = []
    for msg in messages:
        detail = service.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
        emails.append({
            "id": msg["id"],
            "subject": headers.get("Subject", "(no subject)"),
            "from": headers.get("From", ""),
            "date": headers.get("Date", ""),
            "snippet": detail.get("snippet", ""),
        })
    return emails


async def get_email(user_id: int, email_id: str) -> dict:
    creds = await get_credentials(user_id)
    if not creds:
        raise PermissionError("Google account not connected.")
    service = _gmail_service(creds)
    detail = service.users().messages().get(
        userId="me", id=email_id, format="full"
    ).execute()
    headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
    body = _extract_body(detail.get("payload", {}))
    return {
        "id": email_id,
        "subject": headers.get("Subject", "(no subject)"),
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
        "date": headers.get("Date", ""),
        "body": body,
        "snippet": detail.get("snippet", ""),
    }


async def create_draft(user_id: int, to: str, subject: str, body: str,
                       reply_to_id: Optional[str] = None) -> dict:
    creds = await get_credentials(user_id)
    if not creds:
        raise PermissionError("Google account not connected.")
    service = _gmail_service(creds)

    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject

    if reply_to_id:
        original = service.users().messages().get(
            userId="me", id=reply_to_id, format="metadata",
            metadataHeaders=["Message-ID", "Subject"]
        ).execute()
        orig_headers = {h["name"]: h["value"] for h in original.get("payload", {}).get("headers", [])}
        if orig_mid := orig_headers.get("Message-ID"):
            message["In-Reply-To"] = orig_mid
            message["References"] = orig_mid

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft_body = {"message": {"raw": raw}}
    if reply_to_id:
        draft_body["message"]["threadId"] = service.users().messages().get(
            userId="me", id=reply_to_id, format="minimal"
        ).execute().get("threadId")

    draft = service.users().drafts().create(userId="me", body=draft_body).execute()
    return {"draft_id": draft["id"], "to": to, "subject": subject, "body": body}


async def send_draft(user_id: int, draft_id: str) -> bool:
    creds = await get_credentials(user_id)
    if not creds:
        raise PermissionError("Google account not connected.")
    service = _gmail_service(creds)
    service.users().drafts().send(userId="me", body={"id": draft_id}).execute()
    return True


async def delete_draft(user_id: int, draft_id: str) -> bool:
    creds = await get_credentials(user_id)
    if not creds:
        raise PermissionError("Google account not connected.")
    service = _gmail_service(creds)
    try:
        service.users().drafts().delete(userId="me", id=draft_id).execute()
    except Exception as e:
        logger.debug(f"Could not delete Gmail draft {draft_id}: {e}")
    return True


async def get_recent_emails(user_id: int, max_results: int = 5) -> list[dict]:
    return await search_emails(user_id, "in:inbox is:unread", max_results)


def _extract_body(payload: dict) -> str:
    """Recursively extract plain text body from a Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text
    return payload.get("snippet", "")
