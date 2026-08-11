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


async def _analyze_and_auto_draft(user, email: dict) -> dict:
    """Analyze incoming email with LLM, summarize, and generate auto reply / cover letter draft."""
    try:
        from app.ai.agent import _create_chat_completion
        import json
        import re

        sender = email.get("from", "")
        subject = email.get("subject", "")
        snippet = email.get("snippet", "") or email.get("body", "")[:500]

        prompt = f"""You are an AI assistant analyzing an incoming email for {user.name or 'the user'}.

Email Details:
From: {sender}
Subject: {subject}
Content Snippet: {snippet}

Task:
1. Provide a 1-sentence summary of the email.
2. Assess priority (High, Medium, Low).
3. Check if this is a LinkedIn job recommendation, job alert, or recruiter/job email (set is_job=true/false).
4. Determine if this email requires or benefits from a reply or job application draft (true/false).
5. If this is a LinkedIn job alert, job recommendation, or recruiter email:
   - Write a compelling, highly professional Cover Letter & Application Email body for {user.name or 'the user'}.
6. If it is a standard email needing a reply, write a polite, concise professional reply draft.

Return ONLY a JSON object in this format:
{{
    "summary": "...",
    "priority": "High",
    "is_job": true,
    "requires_reply": true,
    "suggested_reply": "..."
}}"""

        response = await _create_chat_completion(
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content or ""
        content = re.sub(r"```json|```", "", content).strip()
        return json.loads(content)
    except Exception as e:
        logger.debug(f"Email analysis error: {e}")
        return {
            "summary": email.get("snippet", ""),
            "priority": "Medium",
            "is_job": False,
            "requires_reply": False,
            "suggested_reply": "",
        }


async def check_and_notify_google_updates():
    """Poll connected Google accounts for new unread emails and upcoming calendar events."""
    if not _bot_app:
        return
    try:
        import re
        from app.services.users import get_all_connected_users
        from app.integrations.gmail import search_emails, get_email, create_draft
        from app.integrations.calendar import get_events
        from app.services import confirmations
        from app.bot import keyboards

        users = await get_all_connected_users("google")
        for user in users:
            # 1. Check unread emails with AI analysis & auto-drafting
            try:
                emails = await search_emails(user.id, "in:inbox is:unread", max_results=5)
                for email in emails:
                    email_id = email["id"]
                    if email_id not in _notified_emails:
                        _notified_emails.add(email_id)
                        if len(_notified_emails) > 1000:
                            _notified_emails.pop()

                        # Get full detail for deep AI analysis
                        full_email = await get_email(user.id, email_id)
                        analysis = await _analyze_and_auto_draft(user, full_email)

                        sender = full_email.get("from", "Unknown")
                        subject = full_email.get("subject", "(no subject)")
                        summary = analysis.get("summary", full_email.get("snippet", ""))
                        priority = analysis.get("priority", "Medium")

                        if analysis.get("requires_reply") and analysis.get("suggested_reply"):
                            # Extract email address
                            match = re.search(r'<([^>]+)>', sender)
                            to_addr = match.group(1) if match else sender

                            # Create draft automatically in Gmail
                            draft = await create_draft(
                                user.id,
                                to=to_addr,
                                subject=f"Re: {subject}",
                                body=analysis["suggested_reply"],
                                reply_to_id=email_id,
                            )
                            action = await confirmations.create_pending_action(user.id, "send_email", draft)

                            header = "💼 *LinkedIn / Job Recommendation Analyzed*" if analysis.get("is_job") else "📩 *New Email Analyzed*"
                            preview_header = "✍️ *Auto-Drafted Cover Letter Preview*:" if analysis.get("is_job") else "✍️ *Auto-Drafted Reply Preview*:"

                            text = (
                                f"{header}\n\n"
                                f"👤 *From*: {sender}\n"
                                f"📌 *Subject*: {subject}\n"
                                f"⚡️ *Priority*: {priority}\n"
                                f"💡 *AI Summary*: {summary}\n\n"
                                f"{preview_header}\n"
                                f"_{analysis['suggested_reply']}_"
                            )
                            keyboard = keyboards.email_draft_keyboard(action.id)
                            try:
                                await _bot_app.bot.send_message(
                                    chat_id=user.telegram_id,
                                    text=text,
                                    reply_markup=keyboard,
                                    parse_mode="Markdown",
                                )
                            except Exception:
                                await _bot_app.bot.send_message(
                                    chat_id=user.telegram_id,
                                    text=f"📩 New Email from {sender}\nSubject: {subject}\nSummary: {summary}\n\nSuggested Reply:\n{analysis['suggested_reply']}",
                                    reply_markup=keyboard,
                                )
                        else:
                            text = (
                                f"📩 *New Email Received*\n\n"
                                f"👤 *From*: {sender}\n"
                                f"📌 *Subject*: {subject}\n"
                                f"💡 *AI Summary*: {summary}"
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
                                    text=f"📩 New Email from {sender}: {subject}",
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
