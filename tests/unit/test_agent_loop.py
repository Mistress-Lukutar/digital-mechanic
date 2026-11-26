'''
File:   test_agent_loop.py
Brief:  Unit tests for the AgentLoop — stream, tool-call round-trip, and error paths.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from mechanic.agent.conversations import ConversationStore
from mechanic.agent.loop import AgentLoop, PromptBuilder
from mechanic.agent.tools_base import ToolDef, ToolError, ToolOutcome, ToolRegistry
from mechanic.llm.types import (
    AiProtocol,
    ChatRequest,
    Endpoint,
    ImagePart,
    ReasoningDelta,
    StopReason,
    StreamError,
    TextDelta,
    TextPart,
    ToolCall,
    ToolCallsReady,
    TurnComplete,
)

# ======================================================================
# Helpers: FakeLLMClient, text_turn, make_loop, collect.
# ======================================================================


class FakeLLMClient:
    """Deterministic LLM client backed by a list of model turns.

    Each turn is a list of llm-event instances to yield in order.
    ``stream_chat`` pops the next turn; when exhausted it yields nothing.
    Every ``ChatRequest`` passed to ``stream_chat`` is recorded in
    ``self.requests``.
    """

    def __init__(self, turns_list: list[list] | None = None) -> None:
        self.turns_list: list[list] = turns_list if turns_list is not None else []
        self.requests: list[ChatRequest] = []
        self._index: int = 0

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[Any]:
        """Pop the next turn and yield its events."""
        self.requests.append(request)
        if self._index < len(self.turns_list):
            events = self.turns_list[self._index]
            self._index += 1
            for event in events:
                yield event
        # When turns are exhausted the async generator simply ends.

    @staticmethod
    def text_turn(
        text: str,
        stop: StopReason = StopReason.END_TURN,
        usage: tuple[int, int] | None = None,
    ) -> list[Any]:
        """Build a list of stream events for a plain-text model turn.

        The *text* is split into two chunks (first half / second half) to
        simulate realistic incremental streaming while keeping tests simple.

        Returns:
            A list containing TextDelta events (one per chunk), followed by
            one ``TurnComplete`` event carrying *stop* and optional *usage*.
        """
        events: list[Any] = []
        if text:
            mid = (len(text) + 1) // 2
            events.append(TextDelta(text[:mid]))
            events.append(TextDelta(text[mid:]))
        else:
            events.append(TextDelta(""))
        events.append(
            TurnComplete(
                stop_reason=stop,
                input_tokens=usage[0] if usage is not None else None,
                output_tokens=usage[1] if usage is not None else None,
            )
        )
        return events


def make_loop(
    client: FakeLLMClient,
    registry: ToolRegistry | None = None,
    prompt: str | PromptBuilder = "SYS",
    max_iterations: int = 8,
) -> AgentLoop:
    """Wire an ``AgentLoop`` with a fresh store and known endpoint."""
    endpoint = Endpoint(
        base_url="http://llm.test/v1",
        api_key="k",
        model_id="m",
        protocol=AiProtocol.OPENAI_COMPATIBLE,
    )
    store = ConversationStore()
    if registry is None:
        registry = ToolRegistry()
    return AgentLoop(
        client=client,
        endpoint=endpoint,
        registry=registry,
        store=store,
        system_prompt=prompt,
        temperature=0.3,
        max_iterations=max_iterations,
    )


async def collect(agen: Any) -> list[tuple[str, dict]]:
    """Drain an async iterator of (event_name, payload) tuples."""
    events: list[tuple[str, dict]] = []
    async for event in agen:
        events.append(event)
    return events


# ======================================================================
# Test 1 — plain_answer_events_and_history
# ======================================================================


async def test_plain_answer_events_and_history() -> None:
    """A single text-only turn produces token + turn_done events and history."""
    client = FakeLLMClient([
        FakeLLMClient.text_turn("hello", stop=StopReason.END_TURN, usage=(10, 5)),
    ])
    loop = make_loop(client)
    events = await collect(loop.run("V1", "What is the answer?"))

    expected_events = [
        ("token", {"text": "hel"}),
        ("token", {"text": "lo"}),
        (
            "turn_done",
            {
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        ),
    ]
    assert events == expected_events

    # Conversation history: user + assistant turns.
    store = loop._store
    history = store.history("V1")
    assert len(history) == 2
    roles = [t.role for t in history]
    assert roles == ["user", "assistant"]
    # Assistant turn text matches the model output.
    assistant_part = history[1].parts[0]
    assert assistant_part.text == "hello"

    # ChatRequest recorded by the loop.
    req = client.requests[0]
    assert req.system_prompt == "SYS"
    assert len(req.tools) == 0  # empty registry → no tools
    assert len(req.turns) == 1
    assert req.turns[0].role == "user"


# ======================================================================
# Test 2 — tool_call_roundtrip_sums_usage
# ======================================================================


async def test_tool_call_roundtrip_sums_usage() -> None:
    """A full tool-call round-trip: call, result, final text with summed usage."""

    def echo_executor(args: dict, *_a: Any) -> str:
        return f"echo:{args['q']}"

    registry = ToolRegistry()
    registry.register(ToolDef(
        name="echo",
        description="Echoes the query",
        parameters_json_schema={
            "type": "object",
            "properties": {"q": {"type": "string"}},
        },
        executor=echo_executor,
    ))

    client = FakeLLMClient([
        [  # Turn (a): tool call request
            ToolCallsReady(
                tool_calls=[ToolCall(
                    call_id="c1",
                    name="echo",
                    arguments_json='{"q": "hi"}',
                )],
                text="let me check",
            ),
            TurnComplete(
                stop_reason=StopReason.TOOL_USE,
                input_tokens=20,
                output_tokens=3,
            ),
        ],
        [  # Turn (b): final answer text
            *FakeLLMClient.text_turn("answer is echo:hi", usage=(5, 7)),
        ],
    ])

    loop = make_loop(client, registry)
    events = await collect(loop.run("V1", "What does echo say about hi?"))

    # --- event names in order ---
    # "let me check" was NOT streamed via TextDelta, so the loop emits it
    # as one remainder token before the tool events (no duplication).
    event_names = [e[0] for e in events]
    assert event_names == [
        "token",       # let me check (remainder)
        "tool_start",
        "tool_result",
        "token",       # answer i
        "token",       # s echo:hi
        "turn_done",
    ]

    # --- tool_start payload ---
    ts_payload = events[1][1]
    assert ts_payload == {"call_id": "c1", "name": "echo", "arguments": {"q": "hi"}}

    # --- tool_result payload ---
    tr_payload = events[2][1]
    assert tr_payload["is_error"] is False
    assert tr_payload["content"] == "echo:hi"
    assert tr_payload["summary"] == "echo:hi"

    # --- turn_done usage (sum of both model turns) ---
    td_payload = events[-1][1]
    assert td_payload["stop_reason"] == "end_turn"
    assert td_payload["usage"]["input_tokens"] == 25   # 20 + 5
    assert td_payload["usage"]["output_tokens"] == 10  # 3 + 7

    # --- history roles ---
    history = loop._store.history("V1")
    roles = [t.role for t in history]
    assert roles == ["user", "assistant", "tool", "assistant"]

    # The assistant turn (index 1) contains a ToolCall part.
    tool_call_part = None
    for p in history[1].parts:
        if isinstance(p, ToolCall):
            tool_call_part = p
            break
    assert tool_call_part is not None
    assert tool_call_part.call_id == "c1"

    # The tool turn (index 2) contains a ToolResult with call_id "c1".
    tool_result = None
    for p in history[2].parts:
        if isinstance(p, ToolCall):
            continue  # skip the assistant's ToolCall that might be there
        assert hasattr(p, 'call_id')
        tool_result = p
        break
    assert tool_result is not None
    assert tool_result.call_id == "c1"

    # --- second ChatRequest turns list (3 entries at request time) ---
    assert len(client.requests) == 2
    second_turns = client.requests[1].turns
    assert len(second_turns) == 3  # user, assistant+toolcall, tool


# ======================================================================
# Test 3 — tool_outcome_event_forwarded
# ======================================================================


async def test_tool_outcome_event_forwarded() -> None:
    """A ToolOutcome carrying an extra event is forwarded after tool_result."""

    def draft_executor(_args: dict, *_a: Any) -> ToolOutcome:
        return ToolOutcome(
            content="drafted",
            event=("ticket_draft", {"ticket": {"urgency": "high"}}),
        )

    registry = ToolRegistry()
    registry.register(ToolDef(
        name="draft",
        description="Draft a ticket",
        parameters_json_schema={"type": "object", "properties": {}},
        executor=draft_executor,
    ))

    client = FakeLLMClient([
        [
            ToolCallsReady(
                tool_calls=[ToolCall(
                    call_id="c1", name="draft", arguments_json='{}',
                )],
                text="",
            ),
            TurnComplete(
                stop_reason=StopReason.TOOL_USE,
                input_tokens=5,
                output_tokens=2,
            ),
        ],
        [
            *FakeLLMClient.text_turn("done"),
        ],
    ])

    loop = make_loop(client, registry)
    events = await collect(loop.run("V1", "Draft it"))

    # Find the tool_result index.
    tr_idx = next(i for i, e in enumerate(events) if e[0] == "tool_result")
    # The very next event should be the forwarded custom event.
    assert events[tr_idx + 1] == ("ticket_draft", {"ticket": {"urgency": "high"}})


# ======================================================================
# Test 4 — unknown_tool_is_error_result
# ======================================================================


async def test_unknown_tool_is_error_result() -> None:
    """Calling an unregistered tool yields an error result; the loop continues."""

    client = FakeLLMClient([
        [
            ToolCallsReady(
                tool_calls=[ToolCall(call_id="c1", name="nope", arguments_json='{}')],
                text="",
            ),
            TurnComplete(
                stop_reason=StopReason.TOOL_USE,
                input_tokens=5,
                output_tokens=2,
            ),
        ],
        [
            *FakeLLMClient.text_turn("all good"),
        ],
    ])

    loop = make_loop(client)  # empty registry
    events = await collect(loop.run("V1", "Call nope"))

    tr_payload = events[1][1]  # tool_result is the second event (after tool_start)
    assert tr_payload["is_error"] is True
    assert "unknown tool" in tr_payload["content"].lower()

    # The loop continued: we see turn_done at the end.
    assert events[-1][0] == "turn_done"


# ======================================================================
# Test 5 — tool_error_becomes_error_result
# ======================================================================


async def test_tool_error_becomes_error_result() -> None:
    """A tool executor raising ToolError produces an error result."""

    def boom_executor(_args: dict, *_a: Any) -> str:
        raise ToolError("boom")

    registry = ToolRegistry()
    registry.register(ToolDef(
        name="crash",
        description="Crashes",
        parameters_json_schema={"type": "object"},
        executor=boom_executor,
    ))

    client = FakeLLMClient([
        [
            ToolCallsReady(
                tool_calls=[ToolCall(call_id="c1", name="crash", arguments_json='{}')],
                text="",
            ),
            TurnComplete(
                stop_reason=StopReason.TOOL_USE,
                input_tokens=5,
                output_tokens=2,
            ),
        ],
        [
            *FakeLLMClient.text_turn("done"),
        ],
    ])

    loop = make_loop(client, registry)
    events = await collect(loop.run("V1", "Run crash"))

    tr_payload = events[1][1]
    assert tr_payload["is_error"] is True
    assert tr_payload["content"] == "boom"


# ======================================================================
# Test 6 — invalid_arguments_json
# ======================================================================


async def test_invalid_arguments_json() -> None:
    """Malformed arguments_json produces an error result with 'invalid arguments'."""

    registry = ToolRegistry()
    registry.register(ToolDef(
        name="parse",
        description="Parses JSON",
        parameters_json_schema={"type": "object"},
        executor=lambda args, *_: str(args),
    ))

    client = FakeLLMClient([
        [
            ToolCallsReady(
                tool_calls=[
                    ToolCall(
                        call_id="c1",
                        name="parse",
                        arguments_json='not-json{',
                    ),
                ],
                text="",
            ),
            TurnComplete(
                stop_reason=StopReason.TOOL_USE,
                input_tokens=5,
                output_tokens=2,
            ),
        ],
        [
            *FakeLLMClient.text_turn("done"),
        ],
    ])

    loop = make_loop(client, registry)
    events = await collect(loop.run("V1", "Parse this"))

    tr_payload = events[1][1]
    assert tr_payload["is_error"] is True
    assert "invalid arguments" in tr_payload["content"].lower()


# ======================================================================
# Test 7 — stream_error_persists_partial_text
# ======================================================================


async def test_stream_error_persists_partial_text() -> None:
    """A StreamError yields an error event; partial text is kept in history."""

    client = FakeLLMClient([
        [
            TextDelta("par"),
            StreamError("provider down"),
        ],
    ])

    loop = make_loop(client)
    events = await collect(loop.run("V1", "Stream me"))

    # Last event is the error; no turn_done.
    assert events[-1] == ("error", {"message": "provider down"})
    assert len(events) == 2  # token + error

    # History: assistant turn contains partial text.
    history = loop._store.history("V1")
    assert len(history) == 2
    assistant_text = history[1].parts[0].text
    assert assistant_text == "par"


# ======================================================================
# Test 8 — tool_use_without_calls_bails_out
# ======================================================================


async def test_tool_use_without_calls_bails_out() -> None:
    """ToolCallsReady with empty tool_calls and TOOL_USE stop yields bail-out error."""

    client = FakeLLMClient([
        [
            ToolCallsReady(tool_calls=[], text=""),
            TurnComplete(
                stop_reason=StopReason.TOOL_USE,
                input_tokens=5,
                output_tokens=2,
            ),
        ],
    ])

    loop = make_loop(client)
    events = await collect(loop.run("V1", "Tool me"))

    # The error event about no tool calls.
    assert len(events) == 1
    assert events[0][0] == "error"
    assert "provided no tool calls" in events[0][1]["message"].lower()
    # No turn_done event.


# ======================================================================
# Test 9 — iteration_limit
# ======================================================================


async def test_iteration_limit() -> None:
    """Exceeding max_iterations yields a limit-reached error with exact call count."""

    tool_turn = [
        ToolCallsReady(
            tool_calls=[ToolCall(call_id="c1", name="echo", arguments_json='{}')],
            text="",
        ),
        TurnComplete(stop_reason=StopReason.TOOL_USE, input_tokens=10, output_tokens=2),
    ]

    client = FakeLLMClient([tool_turn] * 4)

    def echo_exec(_args: dict, *_a: Any) -> str:
        return "ok"

    registry = ToolRegistry()
    registry.register(ToolDef(
        name="echo",
        description="Echoes",
        parameters_json_schema={"type": "object"},
        executor=echo_exec,
    ))

    loop = make_loop(client, registry, max_iterations=3)
    events = await collect(loop.run("V1", "Iterate"))

    assert events[-1] == ("error", {"message": "tool iteration limit reached"})
    # Exactly 3 stream_chat calls (one per iteration).
    assert len(client.requests) == 3


# ======================================================================
# Test 10 — system_prompt_builder_receives_context
# ======================================================================


async def test_system_prompt_builder_receives_context() -> None:
    """A callable prompt builder receives ToolContext and sets system_prompt."""
    captured_contexts: list[Any] = []

    def prompt_builder(context: Any) -> str:
        captured_contexts.append(context)
        return f"PROMPT:{context.vehicle_id}"

    client = FakeLLMClient([
        FakeLLMClient.text_turn("ok"),
    ])

    loop = make_loop(client, prompt=prompt_builder)
    await collect(loop.run("V1", "Build prompt"))

    assert captured_contexts[0].vehicle_id == "V1"
    assert client.requests[0].system_prompt == "PROMPT:V1"


# ======================================================================
# Test 11 — reasoning_event_passthrough
# ======================================================================


async def test_reasoning_event_passthrough() -> None:
    """ReasoningDelta events pass through before token events."""

    client = FakeLLMClient([
        [
            ReasoningDelta("hmm"),
            TextDelta("answer"),
            TurnComplete(
                stop_reason=StopReason.END_TURN,
                input_tokens=5,
                output_tokens=2,
            ),
        ],
    ])

    loop = make_loop(client)
    events = await collect(loop.run("V1", "Think"))

    # ("reasoning", ...) must appear before any ("token", ...).
    reasoning_idx = next(i for i, e in enumerate(events) if e[0] == "reasoning")
    token_idx = next(i for i, e in enumerate(events) if e[0] == "token")
    assert reasoning_idx < token_idx

    assert events[reasoning_idx] == ("reasoning", {"text": "hmm"})


# ======================================================================
# Test 12 — long_tool_result_truncated
# ======================================================================


async def test_long_tool_result_truncated() -> None:
    """A tool result exceeding the limit is truncated with a '[truncated' marker."""

    long_text = "x" * 5000

    def long_executor(_args: dict, *_a: Any) -> str:
        return long_text

    registry = ToolRegistry()
    registry.register(ToolDef(
        name="long",
        description="Returns a long string",
        parameters_json_schema={"type": "object"},
        executor=long_executor,
    ))

    client = FakeLLMClient([
        [
            ToolCallsReady(
                tool_calls=[ToolCall(call_id="c1", name="long", arguments_json='{}')],
                text="",
            ),
            TurnComplete(
                stop_reason=StopReason.TOOL_USE,
                input_tokens=5,
                output_tokens=2,
            ),
        ],
        [
            *FakeLLMClient.text_turn("done"),
        ],
    ])

    loop = make_loop(client, registry)
    events = await collect(loop.run("V1", "Get long"))

    tr_payload = events[1][1]
    assert len(tr_payload["content"]) <= 4100
    assert "[truncated" in tr_payload["content"]


# ======================================================================
# Test 13 — multimodal_user_turn_with_image
# ======================================================================


async def test_multimodal_user_turn_with_image() -> None:
    """A loop turn with an image builds a multimodal content list for the user
    message: first part is text, second part is an image_url dict."""
    client = FakeLLMClient([
        FakeLLMClient.text_turn("ok", stop=StopReason.END_TURN),
    ])

    data_url = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQE="

    loop = make_loop(client)
    events = await collect(loop.run("V1", "What is in this image?", image=data_url))

    assert events[-1][0] == "turn_done"

    # Conversation history: user turn must have multimodal parts.
    history = loop._store.history("V1")
    assert len(history) == 2  # user + assistant turns
    user_turn = history[0]
    assert user_turn.role == "user"
    parts = user_turn.parts
    assert len(parts) == 2

    # First part: text.
    first_part = parts[0]
    assert isinstance(first_part, TextPart)
    assert first_part.text == "What is in this image?"

    # Second part: image_url (ImagePart).
    second_part = parts[1]
    assert isinstance(second_part, ImagePart)
    assert second_part.mime_type == "jpeg"
    assert second_part.data_b64 == "/9j/4AAQSkZJRgABAQE="

    # ChatRequest recorded by the loop must carry the multimodal turn.
    req = client.requests[0]
    assert len(req.turns) == 1
    msg_turn = req.turns[0]
    assert msg_turn.role == "user"
    msg_parts = msg_turn.parts
    assert len(msg_parts) == 2
    assert isinstance(msg_parts[0], TextPart)
    assert isinstance(msg_parts[1], ImagePart)
