"""
Pending actions: store proposed destructive/external actions,
let the user confirm or cancel via Telegram buttons.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PendingAction
from app.database.session import get_session

logger = logging.getLogger(__name__)

# Actions expire after 30 minutes
ACTION_TTL_MINUTES = 30


async def create_pending_action(
    user_id: int,
    action_type: str,
    payload: dict,
) -> PendingAction:
    expires_at = datetime.utcnow() + timedelta(minutes=ACTION_TTL_MINUTES)
    async with get_session() as session:
        action = PendingAction(
            user_id=user_id,
            action_type=action_type,
            payload=payload,
            expires_at=expires_at,
        )
        session.add(action)
        await session.flush()
        await session.refresh(action)
        return action


async def get_pending_action(action_id: int, user_id: int) -> Optional[PendingAction]:
    async with get_session() as session:
        result = await session.execute(
            select(PendingAction).where(
                PendingAction.id == action_id,
                PendingAction.user_id == user_id,
                PendingAction.expires_at > datetime.utcnow(),
            )
        )
        return result.scalar_one_or_none()


async def delete_pending_action(action_id: int, user_id: int) -> bool:
    async with get_session() as session:
        result = await session.execute(
            select(PendingAction).where(
                PendingAction.id == action_id,
                PendingAction.user_id == user_id,
            )
        )
        action = result.scalar_one_or_none()
        if not action:
            return False
        await session.delete(action)
        return True


async def cleanup_expired_actions() -> int:
    """Remove expired pending actions. Called periodically by scheduler."""
    async with get_session() as session:
        result = await session.execute(
            select(PendingAction).where(
                PendingAction.expires_at <= datetime.utcnow()
            )
        )
        actions = result.scalars().all()
        count = len(actions)
        for action in actions:
            await session.delete(action)
        return count


async def update_pending_action_payload(action_id: int, user_id: int, new_payload: dict) -> Optional[PendingAction]:
    async with get_session() as session:
        result = await session.execute(
            select(PendingAction).where(
                PendingAction.id == action_id,
                PendingAction.user_id == user_id,
            )
        )
        action = result.scalar_one_or_none()
        if action:
            action.payload = new_payload
            await session.flush()
            await session.refresh(action)
        return action


async def get_latest_pending_action(user_id: int) -> Optional[PendingAction]:
    """Get the most recent active pending action for a user."""
    async with get_session() as session:
        result = await session.execute(
            select(PendingAction)
            .where(
                PendingAction.user_id == user_id,
                PendingAction.expires_at > datetime.utcnow(),
            )
            .order_by(PendingAction.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
