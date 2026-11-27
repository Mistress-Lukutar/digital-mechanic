'''
File:   loop.py
Brief:  Bare tool-calling agent loop streaming chat events.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.2.0

A bare streaming loop: streams LLM output, executes the model's tool
calls through the registry, feeds results back and repeats until the
model ends the turn or an iteration cap trips. Persistence is kept
out of the loop on purpose; the conversation store is injected.

Events yielded as (name, payload) tuples:
    ("token",       {"text": ...})                     incremental answer text
    ("reasoning",   {"text": ...})                     thinking tokens, if any
    ("tool_start",  {"call_id", "name", "arguments"})  tool invocation begins
    ("tool_result", {"call_id", "name", "summary", "content", "is_error"})
    ("ticket_draft" / "document", {...})               extra ToolOutcome events
    ("turn_done",   {"stop_reason", "usage"})          turn ended
    ("error",       {"message"})                       turn failed
'''

from __future__ import annotations

import inspect
import json
import logging
from collections.abc import AsyncIterator, Callable

from mechanic.agent.conversations import ConversationStore
from mechanic.agent.tools_base import (
    ToolContext,
    ToolDef,
    ToolError,
    ToolOutcome,
    ToolRegistry,
)
from mechanic.llm import (
    ChatRequest,
    Endpoint,
    ReasoningDelta,
    StopReason,
    StreamError,
    TextDelta,
    TextPart,
    ToolCall,
    ToolCallsReady,
    ToolResult,
    TurnComplete,
)

logger = logging.getLogger(__name__)

# Hard cap on model turns per user message: diagnostics + a few searches +
# ticket assembly fits well within this; runaway loops stop here.
DEFAULT_MAX_TOOL_ITERATIONS = 8

# Tool results are truncated before they go back to the model.
TOOL_RESULT_LIMIT = 4000

PromptBuilder = Callable[[ToolContext], str]


class AgentLoop:
    '''Executes the stream → tool calls → stream cycle for one vehicle chat.'''

    def __init__(
        self,
        client: object,
        endpoint: Endpoint,
        registry: ToolRegistry,
        store: ConversationStore,
        system_prompt: str | PromptBuilder,
        temperature: float = 0.3,
        max_output_tokens: int | None = None,
        max_iterations: int = DEFAULT_MAX_TOOL_ITERATIONS,
        tool_services: object | None = None,
    ) -> None:
        '''Create the loop.

        Args:
            client: Object with ``stream_chat(request)`` (an LLM client).
            endpoint: Provider endpoint used for every request this turn.
            registry: Tools the model may call.
            store: Per-vehicle conversation store (mutated as the turn runs).
            system_prompt: Static text, or a callable receiving the
                ToolContext and returning the prompt (vehicle-aware prompt).
            temperature: Sampling temperature for the provider request.
            max_output_tokens: Output cap sent to the provider, if any.
            max_iterations: Safety cap on model turns per user message.
            tool_services: ServiceHub handed to every tool executor via
                ToolContext.services (live clients for fleet/ML/TOiR/RAG).
        '''
        self._client = client
        self._endpoint = endpoint
        self._registry = registry
        self._store = store
        self._system_prompt = system_prompt
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._max_iterations = max_iterations
        self._tool_services = tool_services

    # ------------------------------------------------------------------
    # Main entry point.
    # ------------------------------------------------------------------

    async def run(
        self,
        vehicle_id: str,
        text: str,
        session_id: str | None = None,
        username: str = "mechanic",
        image: str | None = None,
        store_key: str | None = None,
    ) -> AsyncIterator[tuple[str, dict]]:
        '''Run one user message through the loop, yielding events.

        Args:
            vehicle_id: Selected vehicle; keys ToolContext.
            text: The user's message.
            session_id: Session the message refers to (e.g. a check being
                discussed); passed to tool executors via ToolContext.
            username: Authenticated user, for tool context.
            image: Optional data-URL image for multimodal input.
            store_key: Key for conversation storage; defaults to vehicle_id.

        Yields:
            (event_name, payload) tuples; see module docstring.
        '''
        key = store_key or vehicle_id
        context = ToolContext(
            vehicle_id=vehicle_id,
            session_id=session_id,
            username=username,
            services=self._tool_services,
        )
        self._store.add_user_message(key, text, image=image)

        usage_input = 0
        usage_output = 0
        usage_reported = False

        for _iteration in range(self._max_iterations):
            prompt = (
                self._system_prompt(context)
                if callable(self._system_prompt)
                else self._system_prompt
            )
            request = ChatRequest(
                endpoint=self._endpoint,
                system_prompt=prompt,
                turns=self._store.history(key),
                tools=self._registry.specs(),
                temperature=self._temperature,
                max_tokens=self._max_output_tokens,
            )

            accumulated = ""
            calls_ready: ToolCallsReady | None = None
            stop: TurnComplete | None = None
            stream_error: StreamError | None = None

            stream = self._client.stream_chat(request)
            try:
                async for event in stream:
                    if isinstance(event, TextDelta):
                        accumulated += event.text
                        yield ("token", {"text": event.text})
                    elif isinstance(event, ReasoningDelta):
                        yield ("reasoning", {"text": event.text})
                    elif isinstance(event, ToolCallsReady):
                        calls_ready = event
                        # Real providers stream the preceding text via
                        # TextDelta before tool calls; only the tail that
                        # was NOT streamed is emitted here, so text is
                        # never duplicated for the UI.
                        if calls_ready.text and not accumulated.startswith(
                            calls_ready.text
                        ):
                            if calls_ready.text.startswith(accumulated):
                                remainder = calls_ready.text[len(accumulated):]
                            else:
                                remainder = calls_ready.text
                            if remainder:
                                accumulated += remainder
                                yield ("token", {"text": remainder})
                    elif isinstance(event, TurnComplete):
                        stop = event
                        if (
                            event.input_tokens is not None
                            or event.output_tokens is not None
                        ):
                            usage_reported = True
                            usage_input += event.input_tokens or 0
                            usage_output += event.output_tokens or 0
                    elif isinstance(event, StreamError):
                        stream_error = event
            finally:
                # Close provider streams deterministically.
                await stream.aclose()

            if stream_error is not None:
                if accumulated:
                    self._store.add_assistant_parts(
                        key, [TextPart(text=accumulated)]
                    )
                yield ("error", {"message": stream_error.message})
                return

            if calls_ready is not None:
                self._store.add_assistant_parts(
                    key,
                    self._assistant_call_parts(calls_ready),
                )
                for call in calls_ready.tool_calls:
                    yield ("tool_start", self._call_event(call))
                    outcome = await self._execute(call, context)
                    self._store.add_tool_results(
                        key,
                        [
                            ToolResult(
                                call_id=call.call_id,
                                name=call.name,
                                content=outcome.content,
                                is_error=outcome.is_error,
                            )
                        ],
                    )
                    yield (
                        "tool_result",
                        {
                            "call_id": call.call_id,
                            "name": call.name,
                            "summary": outcome.content[:200],
                            "content": outcome.content,
                            "is_error": outcome.is_error,
                        },
                    )
                    if outcome.event is not None:
                        yield outcome.event
                # Bail out when model requests tool use but provides no calls.
                if (
                    not calls_ready.tool_calls
                    and stop is not None
                    and stop.stop_reason == StopReason.TOOL_USE
                ):
                    yield (
                        "error",
                        {"message": "model requested tools but provided no tool calls"},
                    )
                    return
                continue

            if stop is not None and stop.stop_reason == StopReason.TOOL_USE:
                # TOOL_USE without parsable calls: bail out instead of looping.
                if accumulated:
                    self._store.add_assistant_parts(
                        key, [TextPart(text=accumulated)]
                    )
                yield (
                    "error",
                    {"message": "model requested tools but provided no tool calls"},
                )
                return

            if accumulated:
                self._store.add_assistant_parts(
                    key, [TextPart(text=accumulated)]
                )
            usage = (
                {"input_tokens": usage_input, "output_tokens": usage_output}
                if usage_reported
                else None
            )
            yield (
                "turn_done",
                {
                    "stop_reason": (
                        stop.stop_reason.value if stop else StopReason.OTHER.value
                    ),
                    "usage": usage,
                },
            )
            return

        yield ("error", {"message": "tool iteration limit reached"})

    # ------------------------------------------------------------------
    # Tool execution.
    # ------------------------------------------------------------------

    async def _execute(self, call: ToolCall, context: ToolContext) -> ToolOutcome:
        '''Execute one tool call, converting every failure into an outcome.'''
        tool: ToolDef | None = self._registry.get(call.name)
        if tool is None:
            return ToolOutcome(content=f"unknown tool: {call.name}", is_error=True)

        parsed = self._parse_arguments(call.arguments_json)
        if not isinstance(parsed, dict):
            return ToolOutcome(
                content=f"invalid arguments JSON for tool {call.name}",
                is_error=True,
            )

        try:
            result = tool.executor(parsed, context)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, ToolOutcome):
                return ToolOutcome(
                    content=self._truncate(result.content),
                    is_error=result.is_error,
                    event=result.event,
                )
            return ToolOutcome(content=self._truncate(str(result)))
        except ToolError as exc:
            return ToolOutcome(content=str(exc), is_error=True)
        except Exception:
            logger.exception("tool %s failed unexpectedly", call.name)
            return ToolOutcome(
                content=f"internal error while running tool {call.name}",
                is_error=True,
            )

    @staticmethod
    def _parse_arguments(raw: object) -> object:
        '''Parse a tool-call arguments JSON string; return the raw value on
        failure so the caller can report it.'''
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (TypeError, ValueError):
                return raw
        return raw

    @staticmethod
    def _assistant_call_parts(calls_ready: ToolCallsReady) -> list[TextPart | ToolCall]:
        '''Build the assistant turn parts for a tool-call model message.'''
        parts: list[TextPart | ToolCall] = []
        if calls_ready.text:
            parts.append(TextPart(text=calls_ready.text))
        parts.extend(calls_ready.tool_calls)
        return parts

    @staticmethod
    def _call_event(call: ToolCall) -> dict:
        '''Build the tool_start payload; arguments are inlined when valid.'''
        parsed = AgentLoop._parse_arguments(call.arguments_json)
        return {
            "call_id": call.call_id,
            "name": call.name,
            "arguments": parsed if isinstance(parsed, dict) else call.arguments_json,
        }

    @staticmethod
    def _truncate(content: str) -> str:
        '''Cap tool result length before it re-enters the model context.'''
        if len(content) > TOOL_RESULT_LIMIT:
            return (
                content[:TOOL_RESULT_LIMIT]
                + f"... [truncated, {len(content) - TOOL_RESULT_LIMIT} more chars]"
            )
        return content
