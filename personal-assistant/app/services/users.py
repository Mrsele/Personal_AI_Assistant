import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, ConnectedAccount
from app.database.session import get_session

logger = logging.getLogger(__name__)


async def get_or_create_user(telegram_id: int, name: Optional[str] = None) -> User:
    """Get existing user or create a new one."""
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            user = User(telegram_id=telegram_id, name=name)
            session.add(user)
            await session.flush()
            await session.refresh(user)
            logger.info(f"Created new user: telegram_id={telegram_id}")
        elif name and user.name != name:
            user.name = name
        return user


async def get_user_by_telegram_id(telegram_id: int) -> Optional[User]:
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def get_user_by_id(user_id: int) -> Optional[User]:
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()


async def update_user_timezone(user_id: int, timezone: str) -> Optional[User]:
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.timezone = timezone
            await session.flush()
            await session.refresh(user)
        return user


async def update_briefing_time(user_id: int, briefing_time) -> Optional[User]:
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.daily_briefing_time = briefing_time
            await session.flush()
            await session.refresh(user)
        return user


async def get_connected_account(user_id: int, provider: str = "google") -> Optional[ConnectedAccount]:
    async with get_session() as session:
        result = await session.execute(
            select(ConnectedAccount).where(
                ConnectedAccount.user_id == user_id,
                ConnectedAccount.provider == provider,
            )
        )
        return result.scalar_one_or_none()


async def save_connected_account(
    user_id: int,
    provider: str,
    access_token: str,
    refresh_token: Optional[str],
    token_expiry,
    email: Optional[str],
    scopes: list,
) -> ConnectedAccount:
    async with get_session() as session:
        result = await session.execute(
            select(ConnectedAccount).where(
                ConnectedAccount.user_id == user_id,
                ConnectedAccount.provider == provider,
            )
        )
        account = result.scalar_one_or_none()
        if account:
            account.access_token = access_token
            if refresh_token:
                account.refresh_token = refresh_token
            account.token_expiry = token_expiry
            account.email = email
            account.scopes = scopes
        else:
            account = ConnectedAccount(
                user_id=user_id,
                provider=provider,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expiry=token_expiry,
                email=email,
                scopes=scopes,
            )
            session.add(account)
        await session.flush()
        await session.refresh(account)
        return account


async def delete_connected_account(user_id: int, provider: str) -> bool:
    async with get_session() as session:
        result = await session.execute(
            select(ConnectedAccount).where(
                ConnectedAccount.user_id == user_id,
                ConnectedAccount.provider == provider,
            )
        )
        account = result.scalar_one_or_none()
        if not account:
            return False
        await session.delete(account)
        return True


async def get_all_users_with_briefing() -> list[User]:
    """Return users who have a daily briefing time configured."""
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.daily_briefing_time.isnot(None))
        )
        return result.scalars().all()


async def get_all_connected_users(provider: str = "google") -> list[User]:
    """Return all User objects that have a connected account for provider."""
    async with get_session() as session:
        result = await session.execute(
            select(User).join(ConnectedAccount, User.id == ConnectedAccount.user_id).where(
                ConnectedAccount.provider == provider
            )
        )
        return result.scalars().all()
