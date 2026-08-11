"""
Single AI agent with OpenAI function calling.
Runs one conversation turn: takes user message, calls tools as needed,
returns a final text response + any pending actions for confirmation.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings
from app.ai.prompts import get_system_prompt
from app.ai.tools import TOOL_DEFINITIONS, dispatch_tool, ToolResult
from app.database.models import User
from app.services.conversations import add_message, get_history

logger = logging.getLogger(__name__)

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
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
        )

        message = response.choices[0].message

        # No tool calls → final answer
        if not message.tool_calls:
            final_text = message.content or ""
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
