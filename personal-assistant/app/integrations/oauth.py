"""Google OAuth2 flow for Gmail + Calendar access."""
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app.config import settings
from app.services.users import get_connected_account, save_connected_account

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

def get_redirect_uri() -> str:
    import os
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url:
        return f"{render_url.rstrip('/')}/auth/google/callback"
    if settings.google_redirect_uri and "localhost" not in settings.google_redirect_uri:
        return settings.google_redirect_uri
    if settings.base_url and "localhost" not in settings.base_url:
        return f"{settings.base_url.rstrip('/')}/auth/google/callback"
    return settings.google_redirect_uri or "http://localhost:8000/auth/google/callback"


def get_client_config():
    redirect_uri = get_redirect_uri()
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uris": [redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def build_auth_url(state: str) -> str:
    redirect_uri = get_redirect_uri()
    flow = Flow.from_client_config(get_client_config(), scopes=SCOPES)
    flow.redirect_uri = redirect_uri
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return auth_url


def make_oauth_state(telegram_id: int) -> str:
    """Create a signed state parameter to verify the callback."""
    nonce = secrets.token_hex(8)
    payload = f"{telegram_id}:{nonce}"
    sig = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_oauth_state(state: str) -> Optional[int]:
    """Verify state and return telegram_id if valid, else None."""
    try:
        parts = state.rsplit(":", 2)
        if len(parts) != 3:
            return None
        telegram_id_str, nonce, sig = parts
        payload = f"{telegram_id_str}:{nonce}"
        expected = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        return int(telegram_id_str)
    except Exception:
        return None


async def exchange_code_and_save(code: str, user_id: int) -> str:
    """Exchange auth code for tokens, fetch email, persist."""
    flow = Flow.from_client_config(get_client_config(), scopes=SCOPES)
    flow.redirect_uri = settings.google_redirect_uri
    flow.fetch_token(code=code)

    creds = flow.credentials
    email = _fetch_google_email(creds)

    expiry = creds.expiry
    if expiry and expiry.tzinfo is not None:
        expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)

    await save_connected_account(
        user_id=user_id,
        provider="google",
        access_token=creds.token,
        refresh_token=creds.refresh_token,
        token_expiry=expiry,
        email=email,
        scopes=list(creds.scopes or SCOPES),
    )
    return email or "your Google account"


def _fetch_google_email(creds: Credentials) -> Optional[str]:
    try:
        service = build("oauth2", "v2", credentials=creds)
        info = service.userinfo().get().execute()
        return info.get("email")
    except Exception as e:
        logger.warning(f"Could not fetch Google email: {e}")
        return None


async def get_credentials(user_id: int) -> Optional[Credentials]:
    """Get valid (auto-refreshed) credentials for a user."""
    account = await get_connected_account(user_id, "google")
    if not account:
        return None

    expiry = account.token_expiry
    if expiry and expiry.tzinfo is not None:
        expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)

    creds = Credentials(
        token=account.access_token,
        refresh_token=account.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=account.scopes,
        expiry=expiry,
    )

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            new_expiry = creds.expiry
            if new_expiry and new_expiry.tzinfo is not None:
                new_expiry = new_expiry.astimezone(timezone.utc).replace(tzinfo=None)
            await save_connected_account(
                user_id=user_id,
                provider="google",
                access_token=creds.token,
                refresh_token=creds.refresh_token,
                token_expiry=new_expiry,
                email=account.email,
                scopes=list(creds.scopes or []),
            )
        except Exception as e:
            logger.error(f"Token refresh failed for user {user_id}: {e}")
            return None

    return creds
