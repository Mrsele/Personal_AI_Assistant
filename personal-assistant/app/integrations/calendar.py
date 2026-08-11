"""Google Calendar API wrapper."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from googleapiclient.discovery import build

from app.integrations.oauth import get_credentials

logger = logging.getLogger(__name__)


def _cal_service(creds):
    return build("calendar", "v3", credentials=creds)


async def get_events(user_id: int, start: datetime, end: datetime) -> list[dict]:
    creds = await get_credentials(user_id)
    if not creds:
        raise PermissionError("Google account not connected.")
    service = _cal_service(creds)

    result = service.events().list(
        calendarId="primary",
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=20,
    ).execute()

    events = []
    for e in result.get("items", []):
        start_raw = e.get("start", {})
        start_str = start_raw.get("dateTime") or start_raw.get("date", "")
        # Format nicely
        try:
            dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            start_fmt = dt.strftime("%I:%M %p") if "T" in start_str else "All day"
        except Exception:
            start_fmt = start_str

        events.append({
            "id": e["id"],
            "summary": e.get("summary", "Untitled"),
            "start": start_fmt,
            "start_raw": start_str,
            "location": e.get("location", ""),
            "description": e.get("description", ""),
        })
    return events


async def create_event(user_id: int, title: str, start: datetime, end: datetime,
                       description: Optional[str] = None) -> dict:
    creds = await get_credentials(user_id)
    if not creds:
        raise PermissionError("Google account not connected.")
    service = _cal_service(creds)

    body = {
        "summary": title,
        "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
    }
    if description:
        body["description"] = description

    event = service.events().insert(calendarId="primary", body=body).execute()
    return {
        "id": event["id"],
        "summary": event.get("summary"),
        "start": event.get("start", {}).get("dateTime"),
        "link": event.get("htmlLink"),
    }


async def delete_event(user_id: int, event_id: str) -> bool:
    creds = await get_credentials(user_id)
    if not creds:
        raise PermissionError("Google account not connected.")
    service = _cal_service(creds)
    service.events().delete(calendarId="primary", eventId=event_id).execute()
    return True


async def get_today_events(user_id: int) -> list[dict]:
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end = now + timedelta(days=1)
    return await get_events(user_id, now, end)


async def get_tomorrow_events(user_id: int) -> list[dict]:
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = now + timedelta(days=1)
    end = now + timedelta(days=2)
    return await get_events(user_id, start, end)
