"""
Entry point.
- FastAPI handles the Google OAuth callback.
- python-telegram-bot runs in polling mode (or webhook).
- APScheduler runs reminder checks and briefings.
"""
import asyncio
import logging
import sys

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from app.config import settings
from app.database.session import create_tables
from app.bot.handlers import build_application
from app.scheduler.jobs import init_scheduler
from app.integrations.oauth import verify_oauth_state, exchange_code_and_save
from app.services.users import get_user_by_telegram_id

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Global bot application and background task
_bot_app = None
_bot_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bot_app, _bot_task
    logger.info("Starting up...")
    await create_tables()
    _bot_app = build_application(settings.telegram_bot_token)
    await _bot_app.initialize()

    scheduler = init_scheduler(_bot_app)
    scheduler.start()
    logger.info("Scheduler started.")

    # Start bot in polling mode in background task
    _bot_task = asyncio.create_task(_run_bot())
    logger.info("Bot started.")
    yield


# FastAPI for OAuth callbacks
web_app = FastAPI(title="Personal Assistant", lifespan=lifespan)


async def _run_bot():
    await _bot_app.start()
    await _bot_app.updater.start_polling(drop_pending_updates=True)
    # Keep running until the process ends
    await asyncio.Event().wait()


@web_app.get("/health")
async def health():
    return {"status": "ok"}


@web_app.get("/auth/google/callback")
async def google_oauth_callback(request: Request, code: str = None, state: str = None,
                                 error: str = None):
    if error:
        return HTMLResponse(
            "<h2>Authorization failed.</h2><p>Please return to Telegram and try again.</p>",
            status_code=400,
        )
    if not code or not state:
        return HTMLResponse("<h2>Invalid request.</h2>", status_code=400)

    telegram_id = verify_oauth_state(state)
    if not telegram_id:
        return HTMLResponse("<h2>Invalid or expired link.</h2>", status_code=400)

    user = await get_user_by_telegram_id(telegram_id)
    if not user:
        return HTMLResponse("<h2>User not found. Please start the bot first.</h2>", status_code=404)

    try:
        email = await exchange_code_and_save(code, user.id)
    except Exception as e:
        logger.error(f"OAuth exchange failed: {e}")
        return HTMLResponse(
            "<h2>Failed to connect account.</h2><p>Please try again.</p>", status_code=500
        )

    # Notify user in Telegram
    if _bot_app:
        try:
            await _bot_app.bot.send_message(
                chat_id=telegram_id,
                text=f"✅ Google account connected!\n📧 {email}\n\nYou can now use Gmail and Calendar features.",
            )
        except Exception as e:
            logger.warning(f"Could not notify user {telegram_id}: {e}")

    return HTMLResponse("""
    <html><body style="font-family:sans-serif;text-align:center;padding:50px">
    <h2>✅ Google account connected!</h2>
    <p>You can close this window and return to Telegram.</p>
    </body></html>
    """)


def main():
    uvicorn.run(
        "app.main:web_app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
