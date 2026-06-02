"""EveAgent — der Conversation-Loop mit Tool-Calling und Chat-Memory.

Channel-agnostisch: nimmt eine `IncomingMessage`, returnt eine `OutgoingMessage`.
Der MessageRouter macht den Channel-Dispatch.

Pattern:
  1. Chat-History für die Session laden
  2. System-Prompt rendern (mit aktuellem Datum)
  3. LLM.run_with_tools() laufen lassen (Multi-Turn-Tool-Loop)
  4. User-Message + Final-Response in History persistieren
  5. OutgoingMessage zurückgeben
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from eve.agent.tools import ToolRegistry
from eve.core.entities import (
    ChatTurn,
    IncomingMessage,
    LLMMessage,
    MessageRole,
    OutgoingMessage,
)
from eve.core.ports import ChatMemory, LLMProvider, PromptRepository

log = logging.getLogger(__name__)


class EveAgent:
    """Eve's Conversation-Loop. Channel-agnostisch."""

    def __init__(
        self,
        *,
        llm: LLMProvider,
        prompts: PromptRepository,
        chat_memory: ChatMemory,
        tools: ToolRegistry,
        profile_id: str,
        model: str = "claude-opus-4-7",
        max_iterations: int = 10,
        history_window: int = 30,
    ) -> None:
        self.llm = llm
        self.prompts = prompts
        self.chat_memory = chat_memory
        self.tools = tools
        self.profile_id = profile_id
        self.model = model
        self.max_iterations = max_iterations
        self.history_window = history_window

    async def handle(self, incoming: IncomingMessage) -> OutgoingMessage:
        """Nimmt eine User-Message, gibt Eves Antwort zurück."""
        # 1. History laden
        history = await self.chat_memory.load(
            incoming.session_id, limit=self.history_window
        )

        # 2. System-Prompt mit aktuellem Datum rendern
        system_body = await self._render_system_prompt()

        # 3. LLM-Messages bauen: history + neue user message
        llm_messages: list[LLMMessage] = [
            LLMMessage(role=t.role.value, content=t.content)
            for t in history
        ]
        llm_messages.append(LLMMessage(role="user", content=incoming.text))

        # 4. Tool-Loop
        log.info(
            "Agent handle: session=%s, history_turns=%d, tools=%s",
            incoming.session_id, len(history), self.tools.names,
        )
        response = await self.llm.run_with_tools(
            messages=llm_messages,
            model=self.model,
            system=system_body,
            tools=[self._tool_def_to_anthropic(d) for d in self.tools.definitions],
            tool_executor=self.tools.execute,
            max_iterations=self.max_iterations,
        )

        final_text = response.content or "(leere Antwort)"

        # 5. History persistieren (user + assistant)
        now = datetime.utcnow()
        await self.chat_memory.append(
            ChatTurn(
                session_id=incoming.session_id,
                source=incoming.source,
                role=MessageRole.USER,
                content=incoming.text,
                metadata={"user_id": incoming.user_id},
                created_at=now,
            )
        )
        await self.chat_memory.append(
            ChatTurn(
                session_id=incoming.session_id,
                source=incoming.source,
                role=MessageRole.ASSISTANT,
                content=final_text,
                metadata={
                    "model": response.model,
                    "usage": dict(response.usage),
                    "finish_reason": response.finish_reason,
                },
                created_at=datetime.utcnow(),
            )
        )

        return OutgoingMessage.reply_to_message(incoming, text=final_text)

    # ------------------------------------------------------------------
    async def _render_system_prompt(self) -> str:
        now = datetime.now()
        weekday_de = [
            "Montag", "Dienstag", "Mittwoch", "Donnerstag",
            "Freitag", "Samstag", "Sonntag",
        ][now.weekday()]
        rendered = await self.prompts.render(
            "eve_system",
            profile_id=self.profile_id,
            extra_context={
                "now_weekday": weekday_de,
                "now_week": now.isocalendar().week,
                "now_iso": now.isoformat(),
            },
        )
        return rendered.body

    @staticmethod
    def _tool_def_to_anthropic(tool_def) -> dict[str, Any]:
        """Wandelt unsere provider-agnostische ToolDefinition in Anthropic-Format."""
        return {
            "name": tool_def.name,
            "description": tool_def.description,
            "input_schema": tool_def.input_schema,
        }
