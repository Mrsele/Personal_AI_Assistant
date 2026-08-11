"""
Single AI agent with OpenAI function calling.
Runs one conversation turn: takes user message, calls tools as needed,
returns a final text response + any pending actions for confirmation.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings
from app.ai.prompts import get_system_prompt
from app.ai.tools import TOOL_DEFINITIONS, dispatch_tool, ToolResult
from app.database.models import User
from app.services.conversations import add_message, get_history

logger = logging.getLogger(__name__)


def _clean_response_text(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<function=[^>]*>.*?(?:</function>|$)", "", text, flags=re.DOTALL)
    cleaned = re.sub(r" +", " ", cleaned).strip()
    return cleaned

client_kwargs = {"api_key": settings.openai_api_key}
if settings.openai_base_url:
    client_kwargs["base_url"] = settings.openai_base_url

client = AsyncOpenAI(**client_kwargs)


@dataclass
class AgentResponse:
    text: str
    pending_action_id: Optional[int] = None
    action_type: Optional[str] = None  # 'email_draft' | 'confirm' | None
    action_payload: Optional[dict] = None


async def _create_chat_completion(messages: list, tools=None, tool_choice=None):
    """Create completion with automatic fallback to secondary models if 429 rate limit occurs."""
    models = [settings.openai_model, "llama-3.1-8b-instant", "mixtral-8x7b-32768"]
    seen = set()
    models = [m for m in models if m and not (m in seen or seen.add(m))]

    last_error = None
    kwargs = {"messages": messages}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice or "auto"

    for model in models:
        try:
            return await client.chat.completions.create(model=model, **kwargs)
        except Exception as e:
            err_str = str(e).lower()
            if "rate_limit" in err_str or "429" in err_str or "limit" in err_str:
                logger.warning(f"Model {model} hit rate limit, attempting fallback model...")
                last_error = e
            else:
                raise e

    if last_error:
        raise last_error


async def run_agent(user: User, user_message: str) -> AgentResponse:
    """
    Process one user message through the AI agent.
    Returns the final text response and any pending confirmation.
    """
    # Save user message to history
    await add_message(user.id, "user", user_message)

    # Build message list: system + history
    history = await get_history(user.id)
    messages = [{"role": "system", "content": get_system_prompt(user)}] + history

    pending_action_id = None
    action_type = None
    action_payload = None

    # Agent loop: up to 5 tool call rounds
    for _ in range(5):
        response = await _create_chat_completion(
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
        )

        message = response.choices[0].message

        # No tool calls → final answer
        if not message.tool_calls:
            final_text = _clean_response_text(message.content or "")
            await add_message(user.id, "assistant", final_text)
            return AgentResponse(
                text=final_text,
                pending_action_id=pending_action_id,
                action_type=action_type,
                action_payload=action_payload,
            )

        # Process tool calls
        messages.append(message)  # add assistant message with tool_calls

        for tool_call in message.tool_calls:
            name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}

            logger.info(f"Tool call: {name}({args}) for user {user.id}")
            result: ToolResult = await dispatch_tool(name, args, user)

            # Track the last pending action (most tools only create one)
            if result.pending_action_id:
                pending_action_id = result.pending_action_id
                action_type = result.action_type
                action_payload = result.data if isinstance(result.data, dict) else None

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result.data, default=str),
            })

    # Fallback if we hit the loop limit
    fallback = "I've gathered the information. Let me know if you need anything else."
    await add_message(user.id, "assistant", fallback)
    return AgentResponse(text=fallback, pending_action_id=pending_action_id,
                         action_type=action_type, action_payload=action_payload)
