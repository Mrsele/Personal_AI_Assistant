"""APScheduler jobs: reminder notifications, daily briefing, cleanup."""
import logging
from datetime import datetime, timezone

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
