# 🤖 Personal AI Assistant (Telegram)

A personal AI assistant that lives in Telegram. Combines Gmail, Google Calendar, reminders, and an ideas vault into one simple chat interface.

## Features

- 📥 **Gmail** — read, search, summarize emails; draft replies
- 📅 **Google Calendar** — view, create, delete events
- ⏰ **Reminders** — create, list, complete; recurring reminders; Telegram notifications
- 💡 **Ideas Vault** — save, search, tag personal ideas
- ☀️ **Daily Briefing** — morning summary of emails, calendar, reminders
- 🤖 **AI Agent** — natural language for everything (OpenAI function calling)

---

## Setup

### 1. Prerequisites

- Docker + Docker Compose
- A domain with HTTPS (for Google OAuth redirect)
- Telegram account
- OpenAI API key
- Google Cloud project

---

### 2. Create a Telegram Bot

1. Open Telegram → search `@BotFather`
2. Send `/newbot` and follow prompts
3. Copy the **bot token**

---

### 3. Get OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Create a new key
3. Copy it

---

### 4. Set Up Google OAuth

1. Go to https://console.cloud.google.com/
2. Create a new project (or use existing)
3. Enable these APIs:
   - **Gmail API**
   - **Google Calendar API**
   - **Google OAuth2 API**
4. Go to **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
5. Application type: **Web application**
6. Authorized redirect URI: `https://yourdomain.com/auth/google/callback`
7. Copy **Client ID** and **Client Secret**
8. Go to **OAuth consent screen** → add yourself as a test user

---

### 5. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and fill in all values:

```env
TELEGRAM_BOT_TOKEN=...
OPENAI_API_KEY=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://yourdomain.com/auth/google/callback
SECRET_KEY=<run: python -c "import secrets; print(secrets.token_hex(32))">
BASE_URL=https://yourdomain.com
POSTGRES_PASSWORD=choose_a_strong_password
DATABASE_URL=postgresql+asyncpg://assistant:choose_a_strong_password@db:5432/assistant
```

---

### 6. Deploy

```bash
docker compose up -d --build
```

That's it. The app will:
1. Start PostgreSQL
2. Run database migrations
3. Start the bot (polling mode)
4. Start the FastAPI server on port 8000

Make sure port 8000 is accessible from the internet (for Google OAuth callback).

---

## Usage

Open your bot in Telegram and send `/start`.

### Menu buttons
- **📥 Inbox** — recent unread emails
- **⏰ Reminders** — list and manage reminders
- **📅 Calendar** — today's events
- **💡 My Ideas** — browse saved ideas
- **☀️ Daily Briefing** — on-demand morning summary
- **⚙️ Settings** — connect Google, set timezone, configure briefing time

### Natural language examples

```
What do I need to do today?
Remind me to call John tomorrow at 4 PM
What meetings do I have this week?
Save this idea: build a habit tracker app
Show me my ideas about AI
Find the email from Sarah about the contract
Draft a reply to John saying Friday works
Create a meeting with David tomorrow at 3 PM
What important emails did I get today?
```

### Connect Google

1. Go to **⚙️ Settings** → **🔗 Connect Google**
2. Click the OAuth link
3. Authorize in your browser
4. Return to Telegram — you'll see a confirmation message

---

## Project Structure

```
app/
├── main.py              # Entry point (FastAPI + bot + scheduler)
├── config.py            # Settings from .env
├── bot/
│   ├── handlers.py      # All Telegram handlers
│   ├── keyboards.py     # InlineKeyboard builders
│   └── messages.py      # Message formatters
├── ai/
│   ├── agent.py         # OpenAI agent loop
│   ├── prompts.py       # System prompt
│   └── tools.py         # Tool definitions + dispatcher
├── integrations/
│   ├── gmail.py         # Gmail API wrapper
│   ├── calendar.py      # Google Calendar API wrapper
│   └── oauth.py         # OAuth flow + token refresh
├── services/
│   ├── reminders.py     # Reminder CRUD
│   ├── ideas.py         # Ideas CRUD
│   ├── briefing.py      # Daily briefing assembler
│   ├── confirmations.py # Pending action queue
│   ├── conversations.py # Chat history for AI context
│   └── users.py         # User management
├── database/
│   ├── models.py        # SQLAlchemy models
│   ├── session.py       # Async session factory
│   └── migrations/      # Alembic migrations
└── scheduler/
    └── jobs.py          # APScheduler (reminders, briefing)
```

---

## Customization

### Change AI model
Set `OPENAI_MODEL=gpt-4o-mini` in `.env` for lower cost.

### Daily briefing time
In Telegram: **⚙️ Settings** → **☀️ Daily Briefing Time** → send `08:00`

### Timezone
In Telegram: **⚙️ Settings** → **🕐 Set Timezone** → send e.g. `America/New_York`

---

## Development (without Docker)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start PostgreSQL separately, then:
cp .env.example .env  # fill in values
alembic upgrade head
python -m app.main
```

---

## Security Notes

- Never commit `.env` to git (it's in `.gitignore`)
- OAuth tokens are stored in the database — use a strong `POSTGRES_PASSWORD`
- Each user can only access their own data
- Destructive actions always require user confirmation via Telegram buttons
- The AI can never directly execute code or raw SQL
