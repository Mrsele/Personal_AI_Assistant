"""Plans, Itineraries, and Work Plans service."""
import logging
from typing import Optional
from sqlalchemy import select, and_
from app.database.models import Plan
from app.database.session import get_session

logger = logging.getLogger(__name__)


async def create_plan(user_id: int, title: str, content: str, category: str = "General") -> Plan:
    async with get_session() as session:
        plan = Plan(
            user_id=user_id,
            title=title,
            content=content,
            category=category,
        )
        session.add(plan)
        await session.flush()
        await session.refresh(plan)
        return plan


async def list_plans(user_id: int, category: Optional[str] = None) -> list[Plan]:
    async with get_session() as session:
        conditions = [Plan.user_id == user_id]
        if category:
            conditions.append(Plan.category == category)
        result = await session.execute(
            select(Plan)
            .where(and_(*conditions))
            .order_by(Plan.created_at.desc())
        )
        return result.scalars().all()


async def get_plan(plan_id: int, user_id: int) -> Optional[Plan]:
    async with get_session() as session:
        result = await session.execute(
            select(Plan).where(Plan.id == plan_id, Plan.user_id == user_id)
        )
        return result.scalar_one_or_none()


async def delete_plan(plan_id: int, user_id: int) -> bool:
    async with get_session() as session:
        result = await session.execute(
            select(Plan).where(Plan.id == plan_id, Plan.user_id == user_id)
        )
        plan = result.scalar_one_or_none()
        if not plan:
            return False
        await session.delete(plan)
        return True
