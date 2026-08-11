"""To-Do Tasks service."""
import logging
from typing import Optional
from sqlalchemy import select, and_
from app.database.models import Task
from app.database.session import get_session

logger = logging.getLogger(__name__)


async def create_task(user_id: int, title: str, category: str = "General", priority: str = "Medium") -> Task:
    async with get_session() as session:
        task = Task(
            user_id=user_id,
            title=title,
            category=category,
            priority=priority,
        )
        session.add(task)
        await session.flush()
        await session.refresh(task)
        return task


async def list_tasks(user_id: int, include_completed: bool = False) -> list[Task]:
    async with get_session() as session:
        conditions = [Task.user_id == user_id]
        if not include_completed:
            conditions.append(Task.completed == False)
        result = await session.execute(
            select(Task)
            .where(and_(*conditions))
            .order_by(Task.created_at.desc())
        )
        return result.scalars().all()


async def complete_task(task_id: int, user_id: int) -> Optional[Task]:
    async with get_session() as session:
        result = await session.execute(
            select(Task).where(Task.id == task_id, Task.user_id == user_id)
        )
        task = result.scalar_one_or_none()
        if task:
            task.completed = True
            await session.flush()
            await session.refresh(task)
        return task


async def delete_task(task_id: int, user_id: int) -> bool:
    async with get_session() as session:
        result = await session.execute(
            select(Task).where(Task.id == task_id, Task.user_id == user_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            return False
        await session.delete(task)
        return True
