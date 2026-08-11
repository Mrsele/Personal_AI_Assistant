"""Routines & Habits tracker service."""
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from app.database.models import Routine
from app.database.session import get_session

logger = logging.getLogger(__name__)


async def create_routine(user_id: int, title: str, frequency: str = "daily", time_of_day: str = "Morning") -> Routine:
    async with get_session() as session:
        routine = Routine(
            user_id=user_id,
            title=title,
            frequency=frequency,
            time_of_day=time_of_day,
        )
        session.add(routine)
        await session.flush()
        await session.refresh(routine)
        return routine


async def list_routines(user_id: int) -> list[Routine]:
    async with get_session() as session:
        result = await session.execute(
            select(Routine)
            .where(Routine.user_id == user_id)
            .order_by(Routine.created_at.desc())
        )
        return result.scalars().all()


async def mark_routine_done(routine_id: int, user_id: int) -> Optional[Routine]:
    async with get_session() as session:
        result = await session.execute(
            select(Routine).where(Routine.id == routine_id, Routine.user_id == user_id)
        )
        routine = result.scalar_one_or_none()
        if routine:
            routine.completed_today = True
            routine.streak = (routine.streak or 0) + 1
            routine.last_completed_at = datetime.utcnow()
            await session.flush()
            await session.refresh(routine)
        return routine


async def delete_routine(routine_id: int, user_id: int) -> bool:
    async with get_session() as session:
        result = await session.execute(
            select(Routine).where(Routine.id == routine_id, Routine.user_id == user_id)
        )
        routine = result.scalar_one_or_none()
        if not routine:
            return False
        await session.delete(routine)
        return True
