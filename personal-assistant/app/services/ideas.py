"""
Ideas Vault service: save, retrieve, search, update, delete ideas.
Simple text search (ILIKE) - no vector DB needed for MVP.
"""
import logging
from typing import Optional

from sqlalchemy import select, or_, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Idea
from app.database.session import get_session

logger = logging.getLogger(__name__)


async def save_idea(
    user_id: int,
    title: str,
    description: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> Idea:
    async with get_session() as session:
        idea = Idea(
            user_id=user_id,
            title=title,
            description=description,
            tags=tags or [],
        )
        session.add(idea)
        await session.flush()
        await session.refresh(idea)
        return idea


async def list_ideas(user_id: int, limit: int = 50) -> list[Idea]:
    async with get_session() as session:
        result = await session.execute(
            select(Idea)
            .where(Idea.user_id == user_id)
            .order_by(Idea.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()


async def get_idea(idea_id: int, user_id: int) -> Optional[Idea]:
    async with get_session() as session:
        result = await session.execute(
            select(Idea).where(
                Idea.id == idea_id,
                Idea.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()


async def search_ideas(user_id: int, query: str) -> list[Idea]:
    """
    Simple keyword search across title, description, and tags.
    Good enough for personal use with hundreds of ideas.
    """
    term = f"%{query.lower()}%"
    async with get_session() as session:
        result = await session.execute(
            select(Idea).where(
                Idea.user_id == user_id,
                or_(
                    Idea.title.ilike(term),
                    Idea.description.ilike(term),
                    cast(Idea.tags, String).ilike(term),
                )
            ).order_by(Idea.created_at.desc())
        )
        return result.scalars().all()


async def delete_idea(idea_id: int, user_id: int) -> bool:
    async with get_session() as session:
        result = await session.execute(
            select(Idea).where(
                Idea.id == idea_id,
                Idea.user_id == user_id,
            )
        )
        idea = result.scalar_one_or_none()
        if not idea:
            return False
        await session.delete(idea)
        return True


async def edit_idea(
    idea_id: int,
    user_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> Optional[Idea]:
    async with get_session() as session:
        result = await session.execute(
            select(Idea).where(
                Idea.id == idea_id,
                Idea.user_id == user_id,
            )
        )
        idea = result.scalar_one_or_none()
        if not idea:
            return None
        if title is not None:
            idea.title = title
        if description is not None:
            idea.description = description
        if tags is not None:
            idea.tags = tags
        await session.flush()
        await session.refresh(idea)
        return idea
