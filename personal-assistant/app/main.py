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
    await _bot_app.updater.start_polling(drop_pending_updates=False)
    # Keep running until the process ends
    await asyncio.Event().wait()


@web_app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Personal AI Assistant</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
            .card { background: #1e293b; padding: 2.5rem; border-radius: 1rem; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); text-align: center; max-width: 420px; }
            .badge { display: inline-block; padding: 0.25rem 0.75rem; background: #065f46; color: #34d399; border-radius: 9999px; font-size: 0.875rem; font-weight: 600; margin-bottom: 1rem; }
            h1 { margin: 0.5rem 0; font-size: 1.5rem; }
            p { color: #94a3b8; line-height: 1.5; }
            a.btn { display: inline-block; margin-top: 1.25rem; padding: 0.75rem 1.5rem; background: #2563eb; color: white; text-decoration: none; border-radius: 0.5rem; font-weight: 600; }
            a.btn:hover { background: #1d4ed8; }
        </style>
    </head>
    <body>
        <div class="card">
            <span class="badge">● Online & Healthy</span>
            <h1>🤖 Personal AI Assistant</h1>
            <p>Your assistant server is live and actively connected to Telegram, Gmail, and Google Calendar.</p>
            <a class="btn" href="https://t.me/AI_Personal_Support_bot" target="_blank">Open Telegram Bot</a>
        </div>
    </body>
    </html>
    """


@web_app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "ok", "service": "personal-ai-assistant"}


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
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "app.main:web_app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
