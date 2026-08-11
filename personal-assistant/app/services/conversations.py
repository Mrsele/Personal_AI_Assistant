"""Store and retrieve conversation history for AI context."""
from sqlalchemy import select, delete

from app.database.models import Conversation
from app.database.session import get_session
from app.config import settings


async def add_message(user_id: int, role: str, content: str) -> None:
    async with get_session() as session:
        msg = Conversation(user_id=user_id, role=role, content=content)
        session.add(msg)


async def get_history(user_id: int) -> list[dict]:
    """Return last N turns as OpenAI message dicts."""
    limit = settings.max_conversation_turns * 2  # user+assistant pairs
    async with get_session() as session:
        result = await session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
    # Reverse to chronological order
    return [{"role": r.role, "content": r.content} for r in reversed(rows)]


async def clear_history(user_id: int) -> None:
    async with get_session() as session:
        await session.execute(
            delete(Conversation).where(Conversation.user_id == user_id)
        )
