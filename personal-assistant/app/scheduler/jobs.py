"""APScheduler jobs: reminder notifications, daily briefing, cleanup."""
import logging
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Telegram bot application — set at startup
_bot_app = None


def init_scheduler(bot_app) -> AsyncIOScheduler:
    global _bot_app
    _bot_app = bot_app

    scheduler = AsyncIOScheduler(timezone="UTC")

    # Check for due reminders every minute
    scheduler.add_job(
        check_and_send_reminders,
        IntervalTrigger(minutes=1),
        id="reminder_checker",
        replace_existing=True,
    )

    # Send daily briefings — check every minute, send if it's time for that user
    scheduler.add_job(
        send_scheduled_briefings,
        IntervalTrigger(minutes=1),
        id="briefing_sender",
        replace_existing=True,
    )

    # Check for new emails and upcoming calendar events every 5 minutes
    scheduler.add_job(
        check_and_notify_google_updates,
        IntervalTrigger(minutes=5),
        id="google_updates_checker",
        replace_existing=True,
    )

    # Clean up expired pending actions every hour
    scheduler.add_job(
        cleanup_expired_actions,
        IntervalTrigger(hours=1),
        id="cleanup",
        replace_existing=True,
    )

    return scheduler


async def check_and_send_reminders():
    """Find due reminders and send Telegram notifications."""
    if not _bot_app:
        return
    try:
        from app.services.reminders import get_due_reminders, mark_notified
        due = await get_due_reminders()
        for reminder, user in due:
            try:
                await _bot_app.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"⏰ *Reminder*\n\n{reminder.title}",
                    parse_mode="Markdown",
                )
                await mark_notified(reminder.id)
            except Exception as e:
                logger.error(f"Failed to send reminder {reminder.id}: {e}")
    except Exception as e:
        logger.error(f"Reminder checker error: {e}")


async def send_scheduled_briefings():
    """Send daily briefing to users whose briefing time matches current minute."""
    if not _bot_app:
        return
    try:
        from app.services.users import get_all_users_with_briefing
        from app.services.briefing import get_daily_briefing

        now = datetime.now(timezone.utc)
        users = await get_all_users_with_briefing()

        for user in users:
            if user.daily_briefing_time:
                bt = user.daily_briefing_time
                if bt.hour == now.hour and bt.minute == now.minute:
                    try:
                        briefing = await get_daily_briefing(user.id, user.name)
                        await _bot_app.bot.send_message(
                            chat_id=user.telegram_id,
                            text=briefing,
                            parse_mode="Markdown",
                        )
                    except Exception as e:
                        logger.error(f"Failed to send briefing to user {user.id}: {e}")
    except Exception as e:
        logger.error(f"Briefing sender error: {e}")


async def cleanup_expired_actions():
    try:
        from app.services.confirmations import cleanup_expired_actions as do_cleanup
        count = await do_cleanup()
        if count:
            logger.info(f"Cleaned up {count} expired pending actions")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")


_notified_emails = set()
_notified_events = set()


async def check_and_notify_google_updates():
    """Poll connected Google accounts for new unread emails and upcoming calendar events."""
    if not _bot_app:
        return
    try:
        from app.services.users import get_all_connected_users
        from app.integrations.gmail import search_emails
        from app.integrations.calendar import get_events

        users = await get_all_connected_users("google")
        for user in users:
            # 1. Check unread emails
            try:
                emails = await search_emails(user.id, "in:inbox is:unread", max_results=5)
                for email in emails:
                    email_id = email["id"]
                    if email_id not in _notified_emails:
                        _notified_emails.add(email_id)
                        if len(_notified_emails) > 1000:
                            _notified_emails.pop()

                        text = (
                            f"📩 *New Email Received*\n\n"
                            f"From: {email.get('from', 'Unknown')}\n"
                            f"Subject: *{email.get('subject', '(no subject)')}*\n\n"
                            f"_{email.get('snippet', '')}_"
                        )
                        try:
                            await _bot_app.bot.send_message(
                                chat_id=user.telegram_id,
                                text=text,
                                parse_mode="Markdown",
                            )
                        except Exception:
                            await _bot_app.bot.send_message(
                                chat_id=user.telegram_id,
                                text=f"📩 New Email from {email.get('from')}: {email.get('subject')}",
                            )
            except Exception as e:
                logger.debug(f"Email notification check failed for user {user.id}: {e}")

            # 2. Check upcoming calendar events starting in next 15 mins
            try:
                now = datetime.now(timezone.utc)
                end = now + timedelta(minutes=15)
                events = await get_events(user.id, now, end)
                for event in events:
                    event_id = event["id"]
                    if event_id not in _notified_events:
                        _notified_events.add(event_id)
                        if len(_notified_events) > 1000:
                            _notified_events.pop()

                        text = (
                            f"📅 *Upcoming Calendar Event (Starts Soon)*\n\n"
                            f"📌 *{event.get('summary')}*\n"
                            f"⏰ Time: {event.get('start')}"
                        )
                        try:
                            await _bot_app.bot.send_message(
                                chat_id=user.telegram_id,
                                text=text,
                                parse_mode="Markdown",
                            )
                        except Exception:
                            await _bot_app.bot.send_message(
                                chat_id=user.telegram_id,
                                text=f"📅 Upcoming Event: {event.get('summary')} at {event.get('start')}",
                            )
            except Exception as e:
                logger.debug(f"Calendar notification check failed for user {user.id}: {e}")
    except Exception as e:
        logger.error(f"Google notification check error: {e}")
