"""
Reminder service: create, list, complete, delete, edit.
All DB operations go through here; handlers and tools call this, not raw SQL.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Reminder, User
from app.database.session import get_session

logger = logging.getLogger(__name__)

VALID_RECURRENCES = {None, "daily", "weekly", "monthly"}


async def create_reminder(
    user_id: int,
    title: str,
    due_at: datetime,
    recurrence: Optional[str] = None,
) -> Reminder:
    if recurrence not in VALID_RECURRENCES:
        raise ValueError(f"Invalid recurrence '{recurrence}'. Use: daily, weekly, monthly, or null.")

    if due_at and due_at.tzinfo is not None:
        due_at = due_at.astimezone(timezone.utc).replace(tzinfo=None)

    async with get_session() as session:
        reminder = Reminder(
            user_id=user_id,
            title=title,
            due_at=due_at,
            recurrence=recurrence,
        )
        session.add(reminder)
        await session.flush()
        await session.refresh(reminder)
        return reminder


async def list_reminders(user_id: int, include_completed: bool = False) -> list[Reminder]:
    async with get_session() as session:
        conditions = [Reminder.user_id == user_id]
        if not include_completed:
            conditions.append(Reminder.completed == False)
        result = await session.execute(
            select(Reminder)
            .where(and_(*conditions))
            .order_by(Reminder.due_at)
        )
        return result.scalars().all()


async def get_reminder(reminder_id: int, user_id: int) -> Optional[Reminder]:
    async with get_session() as session:
        result = await session.execute(
            select(Reminder).where(
                Reminder.id == reminder_id,
                Reminder.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()


async def complete_reminder(reminder_id: int, user_id: int) -> Optional[Reminder]:
    async with get_session() as session:
        result = await session.execute(
            select(Reminder).where(
                Reminder.id == reminder_id,
                Reminder.user_id == user_id,
            )
        )
        reminder = result.scalar_one_or_none()
        if not reminder:
            return None

        reminder.completed = True

        # If recurring, schedule the next occurrence
        if reminder.recurrence:
            delta = {"daily": timedelta(days=1), "weekly": timedelta(weeks=1),
                     "monthly": timedelta(days=30)}[reminder.recurrence]
            next_reminder = Reminder(
                user_id=user_id,
                title=reminder.title,
                due_at=reminder.due_at + delta,
                recurrence=reminder.recurrence,
            )
            session.add(next_reminder)

        return reminder


async def delete_reminder(reminder_id: int, user_id: int) -> bool:
    async with get_session() as session:
        result = await session.execute(
            select(Reminder).where(
                Reminder.id == reminder_id,
                Reminder.user_id == user_id,
            )
        )
        reminder = result.scalar_one_or_none()
        if not reminder:
            return False
        await session.delete(reminder)
        return True


async def edit_reminder(
    reminder_id: int,
    user_id: int,
    title: Optional[str] = None,
    due_at: Optional[datetime] = None,
) -> Optional[Reminder]:
    async with get_session() as session:
        result = await session.execute(
            select(Reminder).where(
                Reminder.id == reminder_id,
                Reminder.user_id == user_id,
            )
        )
        reminder = result.scalar_one_or_none()
        if not reminder:
            return None
        if title:
            reminder.title = title
        if due_at:
            reminder.due_at = due_at
        await session.flush()
        await session.refresh(reminder)
        return reminder


async def get_due_reminders() -> list[tuple[Reminder, User]]:
    """Return reminders that are due (for the scheduler to notify)."""
    now = datetime.utcnow()
    async with get_session() as session:
        result = await session.execute(
            select(Reminder, User)
            .join(User, User.id == Reminder.user_id)
            .where(
                Reminder.completed == False,
                Reminder.notified == False,
                Reminder.due_at <= now,
            )
        )
        return result.all()


async def mark_notified(reminder_id: int) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(Reminder).where(Reminder.id == reminder_id)
        )
        reminder = result.scalar_one_or_none()
        if reminder:
            reminder.notified = True
