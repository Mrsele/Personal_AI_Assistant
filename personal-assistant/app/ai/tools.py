"""
OpenAI function/tool definitions + dispatcher.
Each tool maps to a service or integration function.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.integrations import gmail, calendar as gcal
from app.services import reminders, ideas, confirmations
from app.database.models import User

logger = logging.getLogger(__name__)

# ── Tool schemas for OpenAI ────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    # Gmail
    {
        "type": "function",
        "function": {
            "name": "search_emails",
            "description": "Search the user's Gmail inbox. Use Gmail search syntax (e.g. 'from:john subject:meeting').",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Gmail search query"},
                    "max_results": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_email",
            "description": "Get the full content of a specific email by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "email_id": {"type": "string"},
                },
                "required": ["email_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_email_draft",
            "description": "Create a draft email reply. This queues for user confirmation before sending.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "reply_to_id": {"type": "string", "description": "Email ID being replied to (optional)"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_email_drafts",
            "description": "List all pending email drafts that are ready to send or edit.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    # Calendar
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": "Get calendar events in a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "ISO datetime (e.g. 2024-01-15T00:00:00)"},
                    "end": {"type": "string", "description": "ISO datetime"},
                },
                "required": ["start", "end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Create a calendar event. Queues for user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "start": {"type": "string", "description": "ISO datetime"},
                    "end": {"type": "string", "description": "ISO datetime"},
                    "description": {"type": "string"},
                },
                "required": ["title", "start", "end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_calendar_event",
            "description": "Delete a calendar event. Queues for user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                    "event_title": {"type": "string", "description": "Human-readable title for confirmation message"},
                },
                "required": ["event_id", "event_title"],
            },
        },
    },
    # Reminders
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": "Create a reminder with a due date/time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "due_at": {"type": "string", "description": "ISO datetime in UTC"},
                    "recurrence": {
                        "type": "string",
                        "enum": ["daily", "weekly", "monthly"],
                        "description": "Optional recurrence",
                    },
                },
                "required": ["title", "due_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "List the user's active reminders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_completed": {"type": "boolean", "default": False},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_reminder",
            "description": "Mark a reminder as completed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {"type": "integer"},
                },
                "required": ["reminder_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_reminder",
            "description": "Delete a reminder. Queues for user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {"type": "integer"},
                    "reminder_title": {"type": "string"},
                },
                "required": ["reminder_id", "reminder_title"],
            },
        },
    },
    # Ideas
    {
        "type": "function",
        "function": {
            "name": "save_idea",
            "description": "Save a new idea to the Ideas Vault.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_ideas",
            "description": "Search saved ideas by keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_ideas",
            "description": "List all saved ideas.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_idea",
            "description": "Delete an idea. Queues for user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "idea_id": {"type": "integer"},
                    "idea_title": {"type": "string"},
                },
                "required": ["idea_id", "idea_title"],
            },
        },
    },
]


# ── Tool dispatcher ────────────────────────────────────────────────────────────

class ToolResult:
    def __init__(self, data: Any, pending_action_id: int | None = None,
                 action_type: str | None = None):
        self.data = data
        self.pending_action_id = pending_action_id
        self.action_type = action_type  # 'email_draft' | 'confirm' | None


async def dispatch_tool(name: str, args: dict, user: User) -> ToolResult:
    """Route a tool call to the right function. Returns ToolResult."""
    uid = user.id
    try:
        match name:
            # ── Gmail ──
            case "search_emails":
                data = await gmail.search_emails(uid, args["query"], args.get("max_results", 10))
                return ToolResult(data)

            case "get_email":
                data = await gmail.get_email(uid, args["email_id"])
                return ToolResult(data)

            case "create_email_draft":
                # Create draft in Gmail first, then queue confirmation
                draft = await gmail.create_draft(
                    uid, args["to"], args["subject"], args["body"],
                    args.get("reply_to_id")
                )
                action = await confirmations.create_pending_action(
                    uid, "send_email", draft
                )
                return ToolResult(draft, pending_action_id=action.id, action_type="email_draft")

            case "list_email_drafts":
                actions = await confirmations.get_pending_actions_by_type(uid, "send_email")
                return ToolResult([{"action_id": a.id, "to": a.payload.get("to"), "subject": a.payload.get("subject"), "body": a.payload.get("body")} for a in actions])

            # ── Calendar ──
            case "get_calendar_events":
                start = datetime.fromisoformat(args["start"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(args["end"].replace("Z", "+00:00"))
                data = await gcal.get_events(uid, start, end)
                return ToolResult(data)

            case "create_calendar_event":
                start = datetime.fromisoformat(args["start"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(args["end"].replace("Z", "+00:00"))
                payload = {"title": args["title"], "start": args["start"],
                           "end": args["end"], "description": args.get("description", "")}
                action = await confirmations.create_pending_action(uid, "create_calendar_event", payload)
                return ToolResult(payload, pending_action_id=action.id, action_type="confirm")

            case "delete_calendar_event":
                payload = {"event_id": args["event_id"], "event_title": args.get("event_title", "event")}
                action = await confirmations.create_pending_action(uid, "delete_calendar_event", payload)
                return ToolResult(payload, pending_action_id=action.id, action_type="confirm")

            # ── Reminders ──
            case "create_reminder":
                due_at = datetime.fromisoformat(args["due_at"].replace("Z", "+00:00"))
                reminder = await reminders.create_reminder(
                    uid, args["title"], due_at, args.get("recurrence")
                )
                return ToolResult({"id": reminder.id, "title": reminder.title,
                                   "due_at": str(reminder.due_at)})

            case "list_reminders":
                items = await reminders.list_reminders(uid, args.get("include_completed", False))
                return ToolResult([{"id": r.id, "title": r.title, "due_at": str(r.due_at),
                                    "recurrence": r.recurrence} for r in items])

            case "complete_reminder":
                await reminders.complete_reminder(args["reminder_id"], uid)
                return ToolResult({"status": "completed"})

            case "delete_reminder":
                payload = {"reminder_id": args["reminder_id"],
                           "reminder_title": args.get("reminder_title", "reminder")}
                action = await confirmations.create_pending_action(uid, "delete_reminder", payload)
                return ToolResult(payload, pending_action_id=action.id, action_type="confirm")

            # ── Ideas ──
            case "save_idea":
                idea = await ideas.save_idea(uid, args["title"],
                                             args.get("description"), args.get("tags"))
                return ToolResult({"id": idea.id, "title": idea.title})

            case "search_ideas":
                items = await ideas.search_ideas(uid, args["query"])
                return ToolResult([{"id": i.id, "title": i.title, "tags": i.tags} for i in items])

            case "list_ideas":
                items = await ideas.list_ideas(uid)
                return ToolResult([{"id": i.id, "title": i.title, "tags": i.tags} for i in items])

            case "delete_idea":
                payload = {"idea_id": args["idea_id"],
                           "idea_title": args.get("idea_title", "idea")}
                action = await confirmations.create_pending_action(uid, "delete_idea", payload)
                return ToolResult(payload, pending_action_id=action.id, action_type="confirm")

            case _:
                return ToolResult({"error": f"Unknown tool: {name}"})

    except PermissionError as e:
        return ToolResult({"error": str(e), "needs_google_connect": True})
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}", exc_info=True)
        return ToolResult({"error": f"Tool failed: {str(e)}"})
