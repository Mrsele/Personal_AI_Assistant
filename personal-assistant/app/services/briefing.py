"""Assemble the daily briefing from calendar, reminders, and emails."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.services import reminders as reminder_svc
from app.integrations import gmail, calendar as gcal
from app.services.users import get_connected_account

logger = logging.getLogger(__name__)


async def get_daily_briefing(user_id: int, user_name: Optional[str] = None) -> str:
    now = datetime.now(timezone.utc)
    greeting_name = f", {user_name}" if user_name else ""
    lines = [f"☀️ Good morning{greeting_name}!\n"]

    # Calendar events today
    try:
        google = await get_connected_account(user_id, "google")
        if google:
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)
            events = await gcal.get_events(user_id, today_start, today_end)
            if events:
                lines.append("📅 *Today's Calendar*")
                for e in events:
                    lines.append(f"  • {e['start']} — {e['summary']}")
            else:
                lines.append("📅 No calendar events today.")
            lines.append("")

            # Recent unread emails
            try:
                emails = await gmail.get_recent_emails(user_id, max_results=5)
                if emails:
                    lines.append("📧 *Unread Emails*")
                    for e in emails[:5]:
                        lines.append(f"  • {e['subject']} — _{e['from'].split('<')[0].strip()}_")
                else:
                    lines.append("📧 No new emails.")
                lines.append("")
            except Exception as e:
                logger.warning(f"Briefing: gmail failed for user {user_id}: {e}")
        else:
            lines.append("📧 _Connect Google in Settings to see emails & calendar._\n")

    except Exception as e:
        logger.warning(f"Briefing: google services failed for user {user_id}: {e}")

    # Reminders due today
    try:
        def _to_naive(dt):
            if dt is None:
                return None
            if dt.tzinfo is not None:
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt

        today_end = _to_naive(now.replace(hour=23, minute=59, second=59))
        all_reminders = await reminder_svc.list_reminders(user_id)
        due_today = [r for r in all_reminders if r.due_at and _to_naive(r.due_at) <= today_end]
        if due_today:
            lines.append("⏰ *Reminders Due Today*")
            for r in due_today:
                lines.append(f"  • {r.title}")
        else:
            lines.append("⏰ No reminders due today.")
        lines.append("")
    except Exception as e:
        logger.warning(f"Briefing: reminders failed for user {user_id}: {e}")

    lines.append("Have a great day! 🚀")
    return "\n".join(lines)
