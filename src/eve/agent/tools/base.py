"""Tool Protocol + ToolDefinition — provider-agnostisch.

Eve's Tools werden vom LLM (Anthropic) per Tool-Use aufgerufen. Jedes Tool
hat eine `ToolDefinition` (Name, Beschreibung, JSON-Schema für Argumente)
und eine `execute(args)`-Coroutine, die einen Text als Resultat zurückgibt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolDefinition:
    """Provider-agnostische Tool-Definition.

    Adapter (z.B. AnthropicProvider) übersetzt dies in das jeweilige
    provider-spezifische Format.
    """

    name: str
    description: str
    input_schema: dict[str, Any]  # JSON Schema (für Anthropic input_schema kompatibel)


@runtime_checkable
class Tool(Protocol):
    """Vertrag, den jedes Eve-Tool erfüllen muss."""

    @property
    def definition(self) -> ToolDefinition: ...

    async def execute(self, args: dict[str, Any]) -> str:
        """Führt das Tool aus. Returns String (wird als tool_result zurück
        an den Agent gegeben). Fehler dürfen sich als Text manifestieren
        — der Agent kann damit umgehen ("entschuldige, das ging nicht…")."""
        ...


class ToolRegistry:
    """Sammlung von Tools, die der Agent zur Verfügung hat.

    Lookup per name → execute. Der LLM-Provider iteriert über `.definitions`
    um sie an die API zu schicken.
    """

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for t in tools or []:
            self.register(t)

    def register(self, tool: Tool) -> None:
        self._tools[tool.definition.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    @property
    def definitions(self) -> list[ToolDefinition]:
        return [t.definition for t in self._tools.values()]

    @property
    def names(self) -> list[str]:
        return list(self._tools.keys())

    async def execute(self, name: str, args: dict[str, Any]) -> str:
        tool = self.get(name)
        if tool is None:
            return f"Tool '{name}' ist nicht verfügbar. Verfügbare Tools: {self.names}"
        return await tool.execute(args)
