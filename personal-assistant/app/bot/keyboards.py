from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu shown on /start or when user requests the menu."""
    buttons = [
        [
            InlineKeyboardButton("📥 Inbox", callback_data="menu:inbox"),
            InlineKeyboardButton("📝 Drafts", callback_data="menu:drafts"),
        ],
        [
            InlineKeyboardButton("⏰ Reminders", callback_data="menu:reminders"),
            InlineKeyboardButton("📌 To-Dos", callback_data="menu:todos"),
        ],
        [
            InlineKeyboardButton("🔄 Routines", callback_data="menu:routines"),
            InlineKeyboardButton("📅 Calendar", callback_data="menu:calendar"),
        ],
        [
            InlineKeyboardButton("🗺️ Plans", callback_data="menu:plans"),
            InlineKeyboardButton("💡 My Ideas", callback_data="menu:ideas"),
        ],
        [
            InlineKeyboardButton("🎨 Image Gen", callback_data="menu:image_gen"),
            InlineKeyboardButton("☀️ Briefing", callback_data="menu:briefing"),
            InlineKeyboardButton("⚙️ Settings", callback_data="menu:settings"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def todo_list_keyboard(tasks: list) -> InlineKeyboardMarkup:
    buttons = []
    for t in tasks[:6]:
        status = "✅" if t.completed else "☐"
        buttons.append([
            InlineKeyboardButton(f"{status} {t.title[:25]}", callback_data=f"todo:complete:{t.id}"),
            InlineKeyboardButton("🗑", callback_data=f"todo:delete:{t.id}"),
        ])
    buttons.append([InlineKeyboardButton("« Main Menu", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def routine_list_keyboard(routines_list: list) -> InlineKeyboardMarkup:
    buttons = []
    for r in routines_list[:6]:
        status = "🔥" if r.completed_today else "⚡️"
        buttons.append([
            InlineKeyboardButton(f"{status} {r.title[:20]} ({r.streak}d streak)", callback_data=f"routine:done:{r.id}"),
            InlineKeyboardButton("🗑", callback_data=f"routine:delete:{r.id}"),
        ])
    buttons.append([InlineKeyboardButton("« Main Menu", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def plans_list_keyboard(plans_list: list) -> InlineKeyboardMarkup:
    buttons = []
    for p in plans_list[:6]:
        buttons.append([
            InlineKeyboardButton(f"🗺️ {p.title[:25]}", callback_data=f"plan:view:{p.id}"),
            InlineKeyboardButton("🗑", callback_data=f"plan:delete:{p.id}"),
        ])
    buttons.append([InlineKeyboardButton("« Main Menu", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def drafts_list_keyboard(draft_actions: list) -> InlineKeyboardMarkup:
    """Inline keyboard for viewing/editing/sending/deleting queued drafts."""
    buttons = []
    for action in draft_actions:
        payload = action.payload or {}
        label = (payload.get("to") or "draft")[:15]
        buttons.append([
            InlineKeyboardButton(f"📤 Send ({label})", callback_data=f"send_email:{action.id}"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit_draft:{action.id}"),
            InlineKeyboardButton("🗑 Remove", callback_data=f"cancel:{action.id}"),
        ])
    buttons.append([InlineKeyboardButton("« Main Menu", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def confirm_action_keyboard(action_id: int, action_label: str) -> InlineKeyboardMarkup:
    """Generic confirm/cancel for pending actions."""
    buttons = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"confirm:{action_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{action_id}"),
        ],
        [InlineKeyboardButton("« Main Menu", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(buttons)


def email_draft_keyboard(action_id: int) -> InlineKeyboardMarkup:
    """Send / Edit / Cancel for email drafts."""
    buttons = [
        [
            InlineKeyboardButton("📤 Send", callback_data=f"send_email:{action_id}"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit_draft:{action_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{action_id}"),
        ],
        [InlineKeyboardButton("« Main Menu", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(buttons)


def reminder_detected_keyboard(action_id: int) -> InlineKeyboardMarkup:
    """Shown when AI detects a potential task in an email."""
    buttons = [
        [
            InlineKeyboardButton("⏰ Create Reminder", callback_data=f"confirm:{action_id}"),
            InlineKeyboardButton("Ignore", callback_data=f"cancel:{action_id}"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def reminder_list_keyboard(reminders: list) -> InlineKeyboardMarkup:
    """Inline keyboard for a list of reminders with complete/delete actions."""
    buttons = []
    for r in reminders:
        label = r.title[:30] + ("…" if len(r.title) > 30 else "")
        buttons.append([
            InlineKeyboardButton(f"✅ {label}", callback_data=f"complete_reminder:{r.id}"),
            InlineKeyboardButton("🗑", callback_data=f"delete_reminder:{r.id}"),
        ])
    buttons.append([InlineKeyboardButton("« Back", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def ideas_list_keyboard(ideas: list) -> InlineKeyboardMarkup:
    """Inline keyboard for a list of ideas."""
    buttons = []
    for idea in ideas:
        label = idea.title[:35] + ("…" if len(idea.title) > 35 else "")
        buttons.append([
            InlineKeyboardButton(f"💡 {label}", callback_data=f"view_idea:{idea.id}"),
            InlineKeyboardButton("🗑", callback_data=f"delete_idea_confirm:{idea.id}"),
        ])
    buttons.append([InlineKeyboardButton("« Back", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def idea_detail_keyboard(idea_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit_idea:{idea_id}"),
            InlineKeyboardButton("🗑 Delete", callback_data=f"delete_idea_confirm:{idea_id}"),
        ],
        [InlineKeyboardButton("« Back to Ideas", callback_data="menu:ideas")],
    ]
    return InlineKeyboardMarkup(buttons)


def settings_keyboard(google_connected: bool) -> InlineKeyboardMarkup:
    google_label = "✅ Google Connected" if google_connected else "🔗 Connect Google"
    google_data = "settings:disconnect_google" if google_connected else "settings:connect_google"
    buttons = [
        [InlineKeyboardButton(google_label, callback_data=google_data)],
        [InlineKeyboardButton("🕐 Set Timezone", callback_data="settings:timezone")],
        [InlineKeyboardButton("☀️ Daily Briefing Time", callback_data="settings:briefing_time")],
        [InlineKeyboardButton("« Back", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(buttons)


def back_to_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("« Main Menu", callback_data="menu:main")]])


def google_oauth_keyboard(auth_url: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🔗 Authorize Google Account", url=auth_url)],
        [InlineKeyboardButton("« Main Menu", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(buttons)
