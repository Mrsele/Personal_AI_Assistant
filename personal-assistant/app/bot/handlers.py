"""
Telegram bot handlers: commands, menu buttons, free-text messages,
and callback query handlers for confirmation buttons.
"""
import logging
import re
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

from app.bot import keyboards, messages
from app.ai.agent import run_agent
from app.services import users as user_svc, confirmations
from app.services import todos as todo_svc, routines as routine_svc, plans as plan_svc
from app.services.reminders import list_reminders, complete_reminder, delete_reminder
from app.services.ideas import list_ideas, get_idea, delete_idea
from app.services.briefing import get_daily_briefing
from app.integrations import gmail as gmail_svc, calendar as gcal_svc
from app.integrations.oauth import build_auth_url, make_oauth_state

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_user(update: Update):
    tg_user = update.effective_user
    return await user_svc.get_or_create_user(
        telegram_id=tg_user.id,
        name=tg_user.first_name,
    )


async def _reply(update: Update, text: str, keyboard=None, parse_mode=ParseMode.MARKDOWN):
    kwargs = {"text": text, "parse_mode": parse_mode}
    if keyboard:
        kwargs["reply_markup"] = keyboard
    target = update.callback_query.message if update.callback_query else update.message
    try:
        await target.reply_text(**kwargs)
    except Exception as e:
        if "parse" in str(e).lower() or "entity" in str(e).lower():
            kwargs["parse_mode"] = None
            await target.reply_text(**kwargs)
        else:
            raise


# ── Commands ───────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user(update)
    text = messages.welcome_message(user.name)
    await _reply(update, text, keyboards.main_menu_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *Personal Assistant Help*\n\n"
        "Just type naturally! Examples:\n"
        "• _\"What do I need to do today?\"_\n"
        "• _\"Remind me to call John tomorrow at 4 PM\"_\n"
        "• _\"What meetings do I have this week?\"_\n"
        "• _\"Save this idea: build a habit tracker\"_\n"
        "• _\"Show me my ideas about AI\"_\n"
        "• _\"Find the email from Sarah\"_\n\n"
        "Use /menu to see the main menu."
    )
    await _reply(update, text)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _reply(update, "📋 *Main Menu*", keyboards.main_menu_keyboard())


# ── Free-text messages → AI agent ─────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user(update)
    user_text = update.message.text.strip()

    if not user_text:
        return

    # Check if user is currently editing an email draft
    editing_action_id = context.user_data.get("editing_action_id")
    if editing_action_id:
        clean_check = user_text.lower().strip()
        cancel_words = {"cancel", "stop", "nevermind", "exit", "no"}
        query_prefixes = ["search", "find", "give me", "show me", "show", "what", "how", "create", "remind", "save", "delete"]
        if clean_check in cancel_words or any(clean_check.startswith(w) for w in query_prefixes):
            context.user_data.pop("editing_action_id", None)
        else:
            context.user_data.pop("editing_action_id", None)
            action = await confirmations.get_pending_action(editing_action_id, user.id)
            if action and action.action_type == "send_email":
                payload = action.payload
                payload["body"] = user_text

                try:
                    draft = await gmail_svc.create_draft(
                        user.id,
                        to=payload["to"],
                        subject=payload["subject"],
                        body=user_text,
                        reply_to_id=payload.get("reply_to_id"),
                    )
                    payload["draft_id"] = draft["draft_id"]
                except Exception as e:
                    logger.warning(f"Could not update Gmail draft directly: {e}")

                await confirmations.update_pending_action_payload(action.id, user.id, payload)

                text = (
                    f"✍️ *Updated Email Draft Preview*\n\n"
                    f"👤 *To*: {payload['to']}\n"
                    f"📌 *Subject*: {payload['subject']}\n\n"
                    f"_{user_text}_"
                )
                keyboard = keyboards.email_draft_keyboard(action.id)
                await _reply(update, text, keyboard)
                return

    # Check if user typed "send", "send it", "send now", "confirm", "yes send" when an active pending action exists
    send_keywords = {"send", "send it", "send now", "send email", "send this email", "confirm", "yes send", "send please", "send this", "send it please", "send now please"}
    clean_text = re.sub(r"[^\w\s]", "", user_text.lower()).strip()
    if clean_text in send_keywords or any(phrase in clean_text for phrase in ["send it", "send now", "send this email", "send email"]):
        latest_action = await confirmations.get_latest_pending_action(user.id)
        if latest_action:
            await _execute_confirmed_action(update, user, latest_action.id)
            return

    # Show typing indicator
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    try:
        response = await run_agent(user, user_text)
    except Exception as e:
        logger.error(f"Agent error for user {user.id}: {e}", exc_info=True)
        await _reply(update, "⚠️ Something went wrong. Please try again.")
        return

    # Determine keyboard based on pending action
    keyboard = None
    if response.pending_action_id:
        if response.action_type == "email_draft":
            keyboard = keyboards.email_draft_keyboard(response.pending_action_id)
        elif response.action_type == "confirm":
            payload = response.action_payload or {}
            label = (payload.get("title") or payload.get("reminder_title") or
                     payload.get("idea_title") or payload.get("event_title") or "this action")
            keyboard = keyboards.confirm_action_keyboard(response.pending_action_id, label)

    if not keyboard:
        keyboard = keyboards.back_to_main_keyboard()

    img_match = re.search(r"https://image\.pollinations\.ai/prompt/[^\s\)]+", response.text or "")
    if img_match:
        img_url = img_match.group(0)
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=img_url,
                caption=response.text[:1024],
                reply_markup=keyboard,
            )
            return
        except Exception as e:
            logger.warning(f"Could not send photo directly: {e}")

    await _reply(update, response.text or "Done!", keyboard)


# ── Callback query handler (buttons) ──────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user = await _get_user(update)

    try:
        # ── Main menu navigation ──
        if data == "menu:main":
            await query.message.edit_text(
                messages.welcome_message(user.name),
                reply_markup=keyboards.main_menu_keyboard(),
                parse_mode=ParseMode.MARKDOWN,
            )

        elif data == "menu:drafts":
            actions = await confirmations.get_pending_actions_by_type(user.id, "send_email")
            if not actions:
                text = "📝 *Email Drafts*\n\nNo pending email drafts. Ask me to draft an email anytime!"
                keyboard = keyboards.back_to_main_keyboard()
            else:
                lines = ["📝 *Pending Email Drafts*\n"]
                for i, act in enumerate(actions, 1):
                    p = act.payload or {}
                    lines.append(f"{i}. *To*: {p.get('to')}\n   *Subject*: {p.get('subject')}\n   _{p.get('body', '')[:120]}_")
                text = "\n\n".join(lines)
                keyboard = keyboards.drafts_list_keyboard(actions)
            await query.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

        elif data == "menu:todos":
            items = await todo_svc.list_tasks(user.id)
            if not items:
                text = "📌 *To-Do Tasks*\n\nNo pending tasks! Tell me e.g. _\"Add to-do: buy groceries\"_ to create one."
                keyboard = keyboards.back_to_main_keyboard()
            else:
                lines = ["📌 *Your To-Do List*\n"]
                for t in items:
                    status = "✅" if t.completed else "☐"
                    lines.append(f"{status} *{t.title}* [{t.priority}]")
                text = "\n".join(lines)
                keyboard = keyboards.todo_list_keyboard(items)
            await query.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

        elif data == "menu:routines":
            items = await routine_svc.list_routines(user.id)
            if not items:
                text = "🔄 *Routines & Habits*\n\nNo routines set! Tell me e.g. _\"Create a daily routine: Morning workout\"_."
                keyboard = keyboards.back_to_main_keyboard()
            else:
                lines = ["🔄 *Your Daily & Weekly Routines*\n"]
                for r in items:
                    status = "🔥" if r.completed_today else "⚡️"
                    lines.append(f"{status} *{r.title}* — {r.streak}d streak ({r.time_of_day})")
                text = "\n".join(lines)
                keyboard = keyboards.routine_list_keyboard(items)
            await query.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

        elif data == "menu:plans":
            items = await plan_svc.list_plans(user.id)
            if not items:
                text = "🗺️ *Plans & Itineraries*\n\nNo plans saved! Tell me e.g. _\"Plan a 3-day trip to Paris\"_ or _\"Create a study plan for Python\"_."
                keyboard = keyboards.back_to_main_keyboard()
            else:
                lines = ["🗺️ *Your Plans & Itineraries*\n"]
                for p in items:
                    lines.append(f"• *{p.title}* [{p.category}]\n  _{p.content[:100]}..._")
                text = "\n\n".join(lines)
                keyboard = keyboards.plans_list_keyboard(items)
            await query.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

        elif data == "menu:image_gen":
            text = "🎨 *AI Image Generator*\n\nSend me a message like:\n_\"Generate an image of a futuristic electric G-Wagen driving through a neon city at night\"_"
            await query.message.edit_text(text, reply_markup=keyboards.back_to_main_keyboard(), parse_mode=ParseMode.MARKDOWN)

        elif data.startswith("todo:complete:"):
            tid = int(data.split(":")[2])
            await todo_svc.complete_task(tid, user.id)
            items = await todo_svc.list_tasks(user.id)
            text = "✅ Task marked as completed!" if not items else "\n".join([f"{'✅' if t.completed else '☐'} *{t.title}*" for t in items])
            await query.message.edit_text(text, reply_markup=keyboards.todo_list_keyboard(items), parse_mode=ParseMode.MARKDOWN)

        elif data.startswith("todo:delete:"):
            tid = int(data.split(":")[2])
            await todo_svc.delete_task(tid, user.id)
            items = await todo_svc.list_tasks(user.id)
            text = "🗑 Task deleted." if not items else "\n".join([f"{'✅' if t.completed else '☐'} *{t.title}*" for t in items])
            await query.message.edit_text(text, reply_markup=keyboards.todo_list_keyboard(items), parse_mode=ParseMode.MARKDOWN)

        elif data.startswith("routine:done:"):
            rid = int(data.split(":")[2])
            rt = await routine_svc.mark_routine_done(rid, user.id)
            items = await routine_svc.list_routines(user.id)
            text = f"🔥 Routine done! Current streak: {rt.streak} days!" if rt else "Done!"
            await query.message.edit_text(text, reply_markup=keyboards.routine_list_keyboard(items), parse_mode=ParseMode.MARKDOWN)

        elif data.startswith("routine:delete:"):
            rid = int(data.split(":")[2])
            await routine_svc.delete_routine(rid, user.id)
            items = await routine_svc.list_routines(user.id)
            text = "🗑 Routine deleted." if not items else "\n".join([f"⚡️ *{r.title}*" for r in items])
            await query.message.edit_text(text, reply_markup=keyboards.routine_list_keyboard(items), parse_mode=ParseMode.MARKDOWN)

        elif data.startswith("plan:view:"):
            pid = int(data.split(":")[2])
            plan = await plan_svc.get_plan(pid, user.id)
            if plan:
                text = f"🗺️ *{plan.title}* [{plan.category}]\n\n{plan.content}"
            else:
                text = "⚠️ Plan not found."
            await query.message.edit_text(text, reply_markup=keyboards.back_to_main_keyboard(), parse_mode=ParseMode.MARKDOWN)

        elif data.startswith("plan:delete:"):
            pid = int(data.split(":")[2])
            await plan_svc.delete_plan(pid, user.id)
            items = await plan_svc.list_plans(user.id)
            text = "🗑 Plan deleted." if not items else "\n".join([f"• *{p.title}*" for p in items])
            await query.message.edit_text(text, reply_markup=keyboards.plans_list_keyboard(items), parse_mode=ParseMode.MARKDOWN)

        elif data == "menu:reminders":
            items = await list_reminders(user.id)
            text = messages.reminder_list(items)
            await query.message.edit_text(
                text, reply_markup=keyboards.reminder_list_keyboard(items),
                parse_mode=ParseMode.MARKDOWN,
            )

        elif data == "menu:ideas":
            items = await list_ideas(user.id)
            text = messages.ideas_list(items)
            await query.message.edit_text(
                text, reply_markup=keyboards.ideas_list_keyboard(items),
                parse_mode=ParseMode.MARKDOWN,
            )

        elif data == "menu:inbox":
            await query.message.edit_text("⏳ Fetching emails...", parse_mode=ParseMode.MARKDOWN)
            try:
                emails = await gmail_svc.get_recent_emails(user.id)
                text = messages.email_summary(emails)
            except PermissionError:
                text = "📧 Connect your Google account in ⚙️ Settings first."
            except Exception as e:
                text = messages.error_message("Couldn't fetch emails right now.")
                logger.error(f"Inbox fetch failed: {e}")
            await query.message.edit_text(
                text, reply_markup=keyboards.back_to_main_keyboard(),
                parse_mode=ParseMode.MARKDOWN,
            )

        elif data == "menu:calendar":
            await query.message.edit_text("⏳ Fetching calendar...", parse_mode=ParseMode.MARKDOWN)
            try:
                events = await gcal_svc.get_today_events(user.id)
                text = messages.calendar_events(events, "Today")
            except PermissionError:
                text = "📅 Connect your Google account in ⚙️ Settings first."
            except Exception as e:
                text = messages.error_message("Couldn't fetch calendar right now.")
                logger.error(f"Calendar fetch failed: {e}")
            await query.message.edit_text(
                text, reply_markup=keyboards.back_to_main_keyboard(),
                parse_mode=ParseMode.MARKDOWN,
            )

        elif data == "menu:briefing":
            await query.message.edit_text("⏳ Preparing your briefing...", parse_mode=ParseMode.MARKDOWN)
            briefing = await get_daily_briefing(user.id, user.name)
            await query.message.edit_text(
                briefing, reply_markup=keyboards.back_to_main_keyboard(),
                parse_mode=ParseMode.MARKDOWN,
            )

        elif data == "menu:settings":
            account = await user_svc.get_connected_account(user.id, "google")
            text = messages.settings_message(
                google_connected=bool(account),
                email=account.email if account else None,
                timezone=user.timezone,
                briefing_time=str(user.daily_briefing_time) if user.daily_briefing_time else None,
            )
            await query.message.edit_text(
                text,
                reply_markup=keyboards.settings_keyboard(bool(account)),
                parse_mode=ParseMode.MARKDOWN,
            )

        # ── Settings ──
        elif data == "settings:connect_google":
            state = make_oauth_state(user.telegram_id)
            context.user_data["oauth_state"] = state
            auth_url = build_auth_url(state)
            text = messages.google_connect_prompt()
            await query.message.edit_text(
                text,
                reply_markup=keyboards.google_oauth_keyboard(auth_url),
                parse_mode=ParseMode.MARKDOWN,
            )

        elif data == "settings:disconnect_google":
            await user_svc.delete_connected_account(user.id, "google")
            await query.message.edit_text(
                "✅ Google account disconnected.",
                reply_markup=keyboards.back_to_main_keyboard(),
                parse_mode=ParseMode.MARKDOWN,
            )

        elif data == "settings:timezone":
            await query.message.edit_text(
                "🕐 Send your timezone, e.g.:\n`America/New_York`\n`Europe/London`\n`Asia/Tokyo`",
                reply_markup=keyboards.back_to_main_keyboard(),
                parse_mode=ParseMode.MARKDOWN,
            )
            context.user_data["awaiting"] = "timezone"

        elif data == "settings:briefing_time":
            await query.message.edit_text(
                "☀️ Send your daily briefing time in 24h format:\nExample: `08:00`\n\nSend `off` to disable.",
                reply_markup=keyboards.back_to_main_keyboard(),
                parse_mode=ParseMode.MARKDOWN,
            )
            context.user_data["awaiting"] = "briefing_time"

        # ── Reminders ──
        elif data.startswith("complete_reminder:"):
            rid = int(data.split(":")[1])
            await complete_reminder(rid, user.id)
            items = await list_reminders(user.id)
            await query.message.edit_text(
                "✅ Reminder completed!\n\n" + messages.reminder_list(items),
                reply_markup=keyboards.reminder_list_keyboard(items),
                parse_mode=ParseMode.MARKDOWN,
            )

        elif data.startswith("delete_reminder:"):
            rid = int(data.split(":")[1])
            action = await confirmations.create_pending_action(
                user.id, "delete_reminder", {"reminder_id": rid, "reminder_title": "reminder"}
            )
            await query.message.edit_text(
                "🗑 Delete this reminder?",
                reply_markup=keyboards.confirm_action_keyboard(action.id, "delete reminder"),
                parse_mode=ParseMode.MARKDOWN,
            )

        # ── Ideas ──
        elif data.startswith("view_idea:"):
            idea_id = int(data.split(":")[1])
            idea = await get_idea(idea_id, user.id)
            if idea:
                await query.message.edit_text(
                    messages.idea_detail(idea),
                    reply_markup=keyboards.idea_detail_keyboard(idea.id),
                    parse_mode=ParseMode.MARKDOWN,
                )

        elif data.startswith("delete_idea_confirm:"):
            idea_id = int(data.split(":")[1])
            idea = await get_idea(idea_id, user.id)
            title = idea.title if idea else "idea"
            action = await confirmations.create_pending_action(
                user.id, "delete_idea", {"idea_id": idea_id, "idea_title": title}
            )
            await query.message.edit_text(
                f"🗑 Delete idea *{title}*?",
                reply_markup=keyboards.confirm_action_keyboard(action.id, title),
                parse_mode=ParseMode.MARKDOWN,
            )

        # ── Confirmation / cancellation / editing ──
        elif data.startswith("edit_draft:"):
            action_id = int(data.split(":")[1])
            action = await confirmations.get_pending_action(action_id, user.id)
            if not action:
                await query.message.edit_text(
                    "⚠️ This draft has expired.",
                    reply_markup=keyboards.back_to_main_keyboard(),
                    parse_mode=ParseMode.MARKDOWN,
                )
                return
            context.user_data["editing_action_id"] = action_id
            text = (
                f"✏️ *Editing Email Draft*\n\n"
                f"👤 *To*: {action.payload.get('to')}\n"
                f"📌 *Subject*: {action.payload.get('subject')}\n\n"
                f"Current Body:\n_{action.payload.get('body')}_\n\n"
                f"👇 *Please type and send your new email response text below:*"
            )
            await query.message.edit_text(
                text,
                reply_markup=keyboards.back_to_main_keyboard(),
                parse_mode=ParseMode.MARKDOWN,
            )

        elif data.startswith("confirm:"):
            action_id = int(data.split(":")[1])
            await _execute_confirmed_action(query, user, action_id)

        elif data.startswith("send_email:"):
            action_id = int(data.split(":")[1])
            await _execute_confirmed_action(query, user, action_id)

        elif data.startswith("cancel:"):
            action_id = int(data.split(":")[1])
            await confirmations.delete_pending_action(action_id, user.id)
            await query.message.edit_text(
                "❌ Cancelled.",
                reply_markup=keyboards.back_to_main_keyboard(),
                parse_mode=ParseMode.MARKDOWN,
            )

    except Exception as e:
        logger.error(f"Callback handler error ({data}): {e}", exc_info=True)
        await query.message.reply_text("⚠️ Something went wrong. Please try again.")


async def _execute_confirmed_action(target, user, action_id: int):
    """Execute a previously queued action after user confirmation."""
    action = await confirmations.get_pending_action(action_id, user.id)
    if not action:
        text = "⚠️ This action has expired. Please try again."
        if hasattr(target, "message") and hasattr(target.message, "edit_text"):
            await target.message.edit_text(text, reply_markup=keyboards.back_to_main_keyboard(), parse_mode=ParseMode.MARKDOWN)
        elif hasattr(target, "message") and target.message:
            await target.message.reply_text(text, reply_markup=keyboards.back_to_main_keyboard(), parse_mode=ParseMode.MARKDOWN)
        else:
            await _reply(target, text, keyboards.back_to_main_keyboard())
        return

    payload = action.payload
    result_text = "✅ Done!"

    try:
        match action.action_type:
            case "send_email":
                await gmail_svc.send_draft(user.id, payload["draft_id"])
                result_text = f"📤 Email sent to {payload['to']}!"

            case "create_calendar_event":
                from app.integrations.calendar import create_event
                from datetime import datetime
                start = datetime.fromisoformat(payload["start"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(payload["end"].replace("Z", "+00:00"))
                await create_event(user.id, payload["title"], start, end,
                                   payload.get("description"))
                result_text = f"📅 Event *{payload['title']}* created!"

            case "delete_calendar_event":
                await gcal_svc.delete_event(user.id, payload["event_id"])
                result_text = f"🗑 Event deleted."

            case "delete_reminder":
                await delete_reminder(payload["reminder_id"], user.id)
                result_text = "🗑 Reminder deleted."

            case "delete_idea":
                await delete_idea(payload["idea_id"], user.id)
                result_text = "🗑 Idea deleted."

    except Exception as e:
        logger.error(f"Confirmed action {action.action_type} failed: {e}")
        result_text = messages.error_message("Action failed. Please try again.")

    await confirmations.delete_pending_action(action_id, user.id)

    if hasattr(target, "message") and hasattr(target.message, "edit_text"):
        try:
            await target.message.edit_text(
                result_text, reply_markup=keyboards.back_to_main_keyboard(),
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        except Exception:
            pass

    if hasattr(target, "message") and target.message:
        await target.message.reply_text(
            result_text, reply_markup=keyboards.back_to_main_keyboard(),
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await _reply(target, result_text, keyboards.back_to_main_keyboard())


# ── App builder ────────────────────────────────────────────────────────────────

async def drafts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user(update)
    actions = await confirmations.get_pending_actions_by_type(user.id, "send_email")
    if not actions:
        text = "📝 *Email Drafts*\n\nNo pending email drafts. Ask me to draft an email anytime!"
        keyboard = keyboards.back_to_main_keyboard()
    else:
        lines = ["📝 *Pending Email Drafts*\n"]
        for i, act in enumerate(actions, 1):
            p = act.payload or {}
            lines.append(f"{i}. *To*: {p.get('to')}\n   *Subject*: {p.get('subject')}\n   _{p.get('body', '')[:120]}_")
        text = "\n\n".join(lines)
        keyboard = keyboards.drafts_list_keyboard(actions)
    await _reply(update, text, keyboard)


def build_application(token: str) -> Application:
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("drafts", drafts_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app
