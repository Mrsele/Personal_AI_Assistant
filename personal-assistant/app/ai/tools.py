"""
OpenAI function/tool definitions + dispatcher.
Each tool maps to a service or integration function.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.integrations import gmail, calendar as gcal, web_search, image_gen
from app.services import reminders, ideas, confirmations, todos, routines, plans
from app.database.models import User

logger = logging.getLogger(__name__)

# ── Tool schemas for OpenAI ────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    # Image Generation
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "Generate an AI image based on a prompt (e.g. 'G Wagen car', 'sunset over mountains').",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Descriptive English prompt of what image to generate"},
                },
                "required": ["prompt"],
            },
        },
    },
    # To-Do Lists & Tasks
    {
        "type": "function",
        "function": {
            "name": "create_todo",
            "description": "Create a new to-do task for the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Task description/title"},
                    "priority": {"type": "string", "enum": ["High", "Medium", "Low"], "default": "Medium"},
                    "category": {"type": "string", "default": "General"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_todos",
            "description": "List all active or completed to-do tasks.",
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
            "name": "complete_todo",
            "description": "Mark a to-do task as completed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "integer"},
                },
                "required": ["todo_id"],
            },
        },
    },
    # Routines & Habits
    {
        "type": "function",
        "function": {
            "name": "create_routine",
            "description": "Create a daily or weekly recurring routine / habit tracker.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Routine name (e.g. 'Morning Meditation', 'Workout')"},
                    "frequency": {"type": "string", "enum": ["daily", "weekly"], "default": "daily"},
                    "time_of_day": {"type": "string", "default": "Morning"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_routines",
            "description": "List all recurring routines and habits with their streaks.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_routine_done",
            "description": "Mark a daily routine as completed today and increment streak.",
            "parameters": {
                "type": "object",
                "properties": {
                    "routine_id": {"type": "integer"},
                },
                "required": ["routine_id"],
            },
        },
    },
    # Plans & Trip Itineraries
    {
        "type": "function",
        "function": {
            "name": "create_plan",
            "description": "Create a structured plan, trip itinerary, study plan, or project outline.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Plan title (e.g. '3-Day Paris Trip', 'Python Study Plan')"},
                    "content": {"type": "string", "description": "Detailed plan steps, schedule, or itinerary"},
                    "category": {"type": "string", "default": "Trip"},
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_plans",
            "description": "List saved plans, itineraries, and project outlines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Filter by category ('Trip', 'Study', 'Project', 'Work')"},
                },
            },
        },
    },
    # Web Search
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the public web for news, websites, car sellers, contact emails, prices, articles, or general information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for news, car sellers, topics, etc."},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
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
                        "enum": ["daily", "weekly", "monthly", "none"],
                        "description": "Recurrence interval ('daily', 'weekly', 'monthly', or 'none' if non-recurring).",
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
            # ── Image Generation ──
            case "generate_image":
                img_url = await image_gen.generate_image(args["prompt"])
                return ToolResult({"prompt": args["prompt"], "image_url": img_url})

            # ── To-Do Tasks ──
            case "create_todo":
                task = await todos.create_task(uid, args["title"], args.get("category", "General"), args.get("priority", "Medium"))
                return ToolResult({"id": task.id, "title": task.title, "priority": task.priority})

            case "list_todos":
                items = await todos.list_tasks(uid, args.get("include_completed", False))
                return ToolResult([{"id": t.id, "title": t.title, "priority": t.priority, "completed": t.completed} for t in items])

            case "complete_todo":
                task = await todos.complete_task(args["todo_id"], uid)
                return ToolResult({"status": "completed", "id": args["todo_id"]} if task else {"error": "Not found"})

            # ── Routines & Habits ──
            case "create_routine":
                rt = await routines.create_routine(uid, args["title"], args.get("frequency", "daily"), args.get("time_of_day", "Morning"))
                return ToolResult({"id": rt.id, "title": rt.title, "frequency": rt.frequency})

            case "list_routines":
                items = await routines.list_routines(uid)
                return ToolResult([{"id": r.id, "title": r.title, "streak": r.streak, "completed_today": r.completed_today} for r in items])

            case "mark_routine_done":
                rt = await routines.mark_routine_done(args["routine_id"], uid)
                return ToolResult({"status": "done", "streak": rt.streak} if rt else {"error": "Not found"})

            # ── Plans & Trip Itineraries ──
            case "create_plan":
                pl = await plans.create_plan(uid, args["title"], args["content"], args.get("category", "Trip"))
                return ToolResult({"id": pl.id, "title": pl.title, "category": pl.category})

            case "list_plans":
                items = await plans.list_plans(uid, args.get("category"))
                return ToolResult([{"id": p.id, "title": p.title, "category": p.category, "content": p.content[:200]} for p in items])

            # ── Web Search ──
            case "search_web":
                data = await web_search.search_web(args["query"], args.get("max_results", 5))
                return ToolResult(data)

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
                now_year = datetime.now().year
                if due_at.year < now_year:
                    due_at = due_at.replace(year=now_year)
                rec = args.get("recurrence")
                if rec and str(rec).lower() in ("none", "null", "false", ""):
                    rec = None
                reminder = await reminders.create_reminder(
                    uid, args["title"], due_at, rec
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
