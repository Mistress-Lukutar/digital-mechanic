'''
File:   tools_base.py
Brief:  Tool foundation - context, errors, definitions and the registry.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

ToolDef pattern (JSON Schema + executor).
Every executor receives the parsed arguments dict plus a ToolContext
(the selected vehicle / session / user) and returns plain text for the
model or a ToolOutcome that may carry an extra UI event (ticket draft,
document page) forwarded to the chat stream by the loop.
'''

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from mechanic.llm import ToolSpec

# Executor: sync or async; returns a string or a ToolOutcome.
ToolExecutor = Callable[
    [dict, "ToolContext"],
    "ToolOutcome | str | Awaitable[ToolOutcome | str]",
]


class ToolError(Exception):
    '''Tool failure surfaced to the model as an error result.'''


@dataclass
class ToolContext:
    '''Per-turn context handed to every tool executor.'''

    vehicle_id: str
    session_id: str | None = None
    username: str = "mechanic"


@dataclass
class ToolOutcome:
    '''Result of one tool execution.

    ``content`` goes back to the model (and to the tool_result SSE event);
    ``event`` optionally names an extra UI event emitted right after the
    tool_result, e.g. ("ticket_draft", {...}) or ("document", {...}).
    '''

    content: str
    is_error: bool = False
    event: tuple[str, dict] | None = None


@dataclass
class ToolDef:
    '''One tool advertised to the model.

    ``confirmation`` is reserved for future approval flows; in this
    application mutating submissions (the real TOiR POST) happen from the
    UI button, not from tool execution, so executors only prepare drafts.
    '''

    name: str
    description: str
    parameters_json_schema: dict
    executor: ToolExecutor
    confirmation: str = "none"
    metadata: dict = field(default_factory=dict)


class ToolRegistry:
    '''Name-keyed registry of tools available to the agent.'''

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef) -> None:
        '''Add a tool; the last registration wins on name clashes.'''
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDef | None:
        '''Return the tool by name, or None when unknown.'''
        return self._tools.get(name)

    def names(self) -> list[str]:
        '''Return registered tool names in registration order.'''
        return list(self._tools)

    def specs(self) -> list[ToolSpec]:
        '''Return provider-facing ToolSpecs for all registered tools.'''
        return [
            ToolSpec(
                name=tool.name,
                description=tool.description,
                parameters_json_schema=tool.parameters_json_schema,
            )
            for tool in self._tools.values()
        ]
