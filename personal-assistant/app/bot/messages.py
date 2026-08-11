"""
Helpers that produce nicely formatted Telegram message strings.
All output uses Telegram MarkdownV2 or plain text (caller chooses).
We use plain text by default to avoid escaping headaches.
"""
from datetime import datetime
from typing import Optional
from app.database.models import Reminder, Idea


def welcome_message(name: Optional[str] = None) -> str:
    greeting = f"Hi {name}!" if name else "Hello!"
    return (
        f"🤖 *Personal Assistant*\n\n"
        f"{greeting} I'm your personal AI assistant.\n\n"
        "I can help you with:\n"
        "• 📥 Reading and summarizing emails\n"
        "• ⏰ Managing reminders\n"
        "• 📅 Checking your calendar\n"
        "• 💡 Saving and searching ideas\n"
        "• ☀️ Daily briefings\n\n"
        "Use the menu below or just type naturally, like:\n"
        "_\"What do I need to do today?\"_\n"
        "_\"Remind me to call John tomorrow at 4 PM.\"_"
    )


def reminder_created(reminder: Reminder) -> str:
    due = reminder.due_at.strftime("%A, %b %d at %I:%M %p")
    recur = f"\n🔁 Repeats {reminder.recurrence}" if reminder.recurrence else ""
    return f"⏰ Reminder set!\n\n*{reminder.title}*\n📅 {due}{recur}"


def reminder_list(reminders: list[Reminder]) -> str:
    if not reminders:
        return "⏰ *Reminders*\n\nNo active reminders. Say _\"Remind me to...\"_ to create one."
    lines = ["⏰ *Reminders*\n"]
    for r in reminders:
        due = r.due_at.strftime("%b %d, %I:%M %p")
        recur = f" 🔁 {r.recurrence}" if r.recurrence else ""
        lines.append(f"• {r.title} — _{due}{recur}_")
    return "\n".join(lines)


def idea_saved(idea: Idea) -> str:
    tags = " ".join(f"#{t}" for t in idea.tags) if idea.tags else ""
    return f"💡 Idea saved!\n\n*{idea.title}*\n{tags}"


def idea_detail(idea: Idea) -> str:
    tags = " ".join(f"#{t}" for t in idea.tags) if idea.tags else "No tags"
    desc = idea.description or "_No description_"
    created = idea.created_at.strftime("%b %d, %Y")
    return (
        f"💡 *{idea.title}*\n\n"
        f"{desc}\n\n"
        f"🏷 {tags}\n"
        f"📅 Saved {created}"
    )


def ideas_list(ideas: list[Idea]) -> str:
    if not ideas:
        return "💡 *My Ideas*\n\nNo ideas saved yet. Say _\"Save this idea: ...\"_ to add one."
    lines = ["💡 *My Ideas*\n"]
    for i, idea in enumerate(ideas, 1):
        tags = f" ({', '.join(idea.tags[:2])})" if idea.tags else ""
        lines.append(f"{i}. {idea.title}{tags}")
    return "\n".join(lines)


def error_message(user_facing: str) -> str:
    return f"⚠️ {user_facing}"


def google_connect_prompt() -> str:
    return (
        "🔗 *Connect Google Account*\n\n"
        "Click the button below to authorize access to your Gmail and Google Calendar.\n\n"
        "_You will be redirected back automatically after authorization._"
    )


def settings_message(google_connected: bool, email: Optional[str], timezone: str,
                     briefing_time: Optional[str]) -> str:
    google_status = f"✅ Connected ({email})" if google_connected else "❌ Not connected"
    briefing = briefing_time or "Disabled"
    return (
        "⚙️ *Settings*\n\n"
        f"📧 Google: {google_status}\n"
        f"🕐 Timezone: {timezone}\n"
        f"☀️ Daily briefing: {briefing}"
    )


def email_summary(emails: list[dict]) -> str:
    if not emails:
        return "📥 No recent emails found."
    lines = ["📥 *Recent Emails*\n"]
    for e in emails[:10]:
        sender = e.get("from", "Unknown")[:40]
        subject = e.get("subject", "(no subject)")[:60]
        lines.append(f"• *{subject}*\n  From: {sender}")
    return "\n\n".join(lines)


def calendar_events(events: list[dict], label: str = "Upcoming") -> str:
    if not events:
        return f"📅 No events {label.lower()}."
    lines = [f"📅 *{label}*\n"]
    for e in events:
        start = e.get("start", "")
        title = e.get("summary", "Untitled")
        lines.append(f"• {start} — {title}")
    return "\n".join(lines)


def task_detected_message(title: str, deadline: Optional[str]) -> str:
    deadline_line = f"\n⏰ Deadline: {deadline}" if deadline else ""
    return (
        f"📧 *Possible task detected*\n\n"
        f"{title}{deadline_line}\n\n"
        "Would you like to create a reminder?"
    )
