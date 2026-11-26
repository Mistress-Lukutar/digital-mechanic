'''
File:   test_llm_openai_client.py
Brief:  Unit tests for the OpenAI-compatible LLM client.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations

import json

import httpx

from mechanic.llm.openai_client import OpenAiClient, _turns_to_messages
from mechanic.llm.types import (
    ChatRequest,
    Endpoint,
    ImagePart,
    ModelInfo,
    StopReason,
    StreamError,
    TextDelta,
    TextPart,
    ToolCall,
    ToolCallsReady,
    ToolResult,
    Turn,
    TurnComplete,
)


def _sse_frame(event_name: str | None, data: str) -> str:
    '''Build a raw SSE frame string.'''
    lines = []
    if event_name is not None:
        lines.append(f"event: {event_name}")
    lines.append(f"data: {data}")
    lines.append("")  # blank line = dispatch
    return "\n".join(lines) + "\n"


def _sse_body(frames: list[str]) -> str:
    '''Concatenate raw SSE frames into a full response body.'''
    return "".join(frames)


# ------------------------------------------------------------------
# Helpers for MockTransport
# ------------------------------------------------------------------

def make_handler(sse_body_str: str, content_type: str = "text/event-stream"):
    '''Return an httpx.MockTransport handler that returns the given SSE body.'''
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=sse_body_str.encode("utf-8"),
            headers={"content-type": content_type},
        )
    return handler


# ------------------------------------------------------------------
# test_stream_text_and_turn_complete
# ------------------------------------------------------------------

async def test_stream_text_and_turn_complete():
    '''Two content deltas then finish_reason=stop, then a usage chunk.'''
    body = (
        _sse_frame(None, json.dumps({"choices": [{"delta": {"content": "Hello"}}]}))
        + _sse_frame(None, json.dumps({"choices": [{"delta": {"content": " world"}}]}))
        + _sse_frame(
            None,
            json.dumps({"choices": [{"finish_reason": "stop"}]}),
        )
        + _sse_frame(
            None,
            json.dumps({"usage": {"prompt_tokens": 10, "completion_tokens": 5}}),
        )
    )

    collected = []
    async for event in OpenAiClient(
        httpx.AsyncClient(transport=httpx.MockTransport(make_handler(body)))
    ).stream_chat(
        ChatRequest(
            endpoint=Endpoint(
                base_url="http://llm.test/v1",
                api_key="k",
                model_id="m",
                protocol="openai_compatible",
            ),
            system_prompt=None,
            turns=[],
            tools=[],
            temperature=0.7,
        )
    ):
        collected.append(event)

    assert len(collected) == 3
    assert isinstance(collected[0], TextDelta) and collected[0].text == "Hello"
    assert isinstance(collected[1], TextDelta) and collected[1].text == " world"
    tc = collected[2]
    assert isinstance(tc, TurnComplete)
    assert tc.stop_reason == StopReason.END_TURN
    assert tc.input_tokens == 10
    assert tc.output_tokens == 5


# ------------------------------------------------------------------
# test_stream_tool_calls_assembly
# ------------------------------------------------------------------

async def test_stream_tool_calls_assembly():
    '''Tool-call fragments arriving split across chunks assemble into one ToolCall.'''
    body = (
        _sse_frame(
            None,
            json.dumps({"choices": [{"delta": {"content": "ok ", "tool_calls": []}}]}),
        )
        # First tool_call fragment: index 0 with id and name
        + _sse_frame(
            None,
            json.dumps({
                "choices": [{
                    "delta": {
                        "tool_calls": [{
                            "index": 0,
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "calc"},
                        }]
                    }
                }],
            }),
        )
        # Arguments piece 1
        + _sse_frame(
            None,
            json.dumps({
                "choices": [{
                    "delta": {
                        "tool_calls": [{
                            "index": 0,
                            "function": {"arguments": '{"x":'},
                        }]
                    }
                }],
            }),
        )
        # Arguments piece 2
        + _sse_frame(
            None,
            json.dumps({
                "choices": [{
                    "delta": {
                        "tool_calls": [{
                            "index": 0,
                            "function": {"arguments": '1}'},
                        }]
                    }
                }],
            }),
        )
        # Finish with tool_calls
        + _sse_frame(
            None,
            json.dumps({"choices": [{"finish_reason": "tool_calls"}]}),
        )
    )

    collected = []
    async for event in OpenAiClient(
        httpx.AsyncClient(transport=httpx.MockTransport(make_handler(body)))
    ).stream_chat(
        ChatRequest(
            endpoint=Endpoint(
                base_url="http://llm.test/v1",
                api_key="k",
                model_id="m",
                protocol="openai_compatible",
            ),
            system_prompt=None,
            turns=[],
            tools=[],
            temperature=0.7,
        )
    ):
        collected.append(event)

    assert len(collected) == 3
    assert isinstance(collected[0], TextDelta) and collected[0].text == "ok "
    tc = collected[1]
    assert isinstance(tc, ToolCallsReady)
    assert tc.text == "ok "
    assert len(tc.tool_calls) == 1
    call = tc.tool_calls[0]
    assert isinstance(call, ToolCall)
    assert call.call_id == "call_1"
    assert call.name == "calc"
    assert call.arguments_json == '{"x":1}'
    # TurnComplete follows ToolCallsReady
    assert isinstance(collected[2], TurnComplete)
    assert collected[2].stop_reason == StopReason.TOOL_USE


# ------------------------------------------------------------------
# test_stream_http_error
# ------------------------------------------------------------------

async def test_stream_http_error():
    '''HTTP 401 returns StreamError with the error message and no TurnComplete.'''
    body = '{"error": {"message": "bad key"}}'

    collected = []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=401,
            content=body.encode("utf-8"),
            headers={"content-type": "application/json"},
        )

    async for event in OpenAiClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ).stream_chat(
        ChatRequest(
            endpoint=Endpoint(
                base_url="http://llm.test/v1",
                api_key="k",
                model_id="m",
                protocol="openai_compatible",
            ),
            system_prompt=None,
            turns=[],
            tools=[],
            temperature=0.7,
        )
    ):
        collected.append(event)

    assert len(collected) == 1
    err = collected[0]
    assert isinstance(err, StreamError)
    assert err.message == "bad key"
    assert err.http_code == 401


# ------------------------------------------------------------------
# test_stream_midstream_error
# ------------------------------------------------------------------

async def test_stream_midstream_error():
    '''SSE body emitting an error chunk with no choices yields StreamError.'''
    body = (
        _sse_frame(
            None,
            json.dumps({"choices": [{"delta": {"content": "partial"}}]}),
        )
        + _sse_frame(
            None,
            json.dumps({
                "error": {
                    "message": "rate limit",
                    "code": 429,
                }
            }),
        )
        # A subsequent chunk that would normally be processed
        + _sse_frame(
            None,
            json.dumps({"choices": [{"finish_reason": "stop"}]}),
        )
    )

    collected = []
    async for event in OpenAiClient(
        httpx.AsyncClient(transport=httpx.MockTransport(make_handler(body)))
    ).stream_chat(
        ChatRequest(
            endpoint=Endpoint(
                base_url="http://llm.test/v1",
                api_key="k",
                model_id="m",
                protocol="openai_compatible",
            ),
            system_prompt=None,
            turns=[],
            tools=[],
            temperature=0.7,
        )
    ):
        collected.append(event)

    assert len(collected) == 2
    assert isinstance(collected[0], TextDelta) and collected[0].text == "partial"
    err = collected[1]
    assert isinstance(err, StreamError)
    assert err.message == "rate limit"
    assert err.http_code == 429


# ------------------------------------------------------------------
# test_request_turns_to_messages
# ------------------------------------------------------------------

def test_request_turns_to_messages():
    '''_turns_to_messages produces correct OpenAI wire shapes.'''
    user_turn = Turn(
        role="user",
        parts=[
            TextPart(text="Hello image"),
            ImagePart(mime_type="image/png", data_b64="aaa"),
        ],
    )
    assistant_turn = Turn(
        role="assistant",
        parts=[
            TextPart(text="Using tool"),
            ToolCall(call_id="call_0", name="fetch", arguments_json='{"url":"x"}'),
        ],
    )
    tool_turn = Turn(
        role="tool",
        parts=[
            ToolResult(
                call_id="call_0",
                name="fetch",
                content="result",
                images=[ImagePart(mime_type="image/jpeg", data_b64="bbb")],
            ),
        ],
    )

    messages = _turns_to_messages([user_turn, assistant_turn, tool_turn])

    # 1. User message with text + image_url
    assert len(messages) >= 3
    user_msg = messages[0]
    assert user_msg["role"] == "user"
    content = user_msg["content"]
    assert isinstance(content, list)
    text_parts_found = [c for c in content if c.get("type") == "text"]
    assert any(p.get("text") == "Hello image" for p in text_parts_found)
    assert any(
        c.get("type") == "image_url"
        for c in content
        if isinstance(c.get("image_url"), dict)
    )

    # 2. Assistant message with tool_calls
    assistant_msg = messages[1]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["content"] == "Using tool"
    assert "tool_calls" in assistant_msg
    tc = assistant_msg["tool_calls"][0]
    assert tc["id"] == "call_0"
    assert tc["type"] == "function"
    assert tc["function"]["name"] == "fetch"
    assert tc["function"]["arguments"] == '{"url":"x"}'

    # 3. Tool message with tool_call_id
    tool_msg = messages[2]
    assert tool_msg["role"] == "tool"
    assert tool_msg["tool_call_id"] == "call_0"
    assert tool_msg["content"] == "result"

    # 4. Follow-up user message for images from tool result
    image_msg = messages[3]
    assert image_msg["role"] == "user"
    assert any(c.get("type") == "image_url" for c in image_msg["content"])


# ------------------------------------------------------------------
# test_fetch_models_parses
# ------------------------------------------------------------------

async def test_fetch_models_parses():
    '''Handler returns 200 with model data; fetch_models parses correctly.'''

    def handler(request: httpx.Request) -> httpx.Response:
        resp_body = json.dumps({
            "data": [
                {"id": "m1", "context_length": 4096},
            ]
        })
        return httpx.Response(
            200,
            content=resp_body.encode(),
            headers={"content-type": "application/json"},
        )

    client = OpenAiClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    models = await client.fetch_models("http://llm.test/v1", "k")

    assert len(models) == 1
    m = models[0]
    assert isinstance(m, ModelInfo)
    assert m.model_id == "m1"
    assert m.display_name == "m1"
    assert m.context_tokens == 4096
    # Heuristic: m1 has no vision keywords (supports_vision=False);
    # not a non-chat keyword (supports_tools=True)
    assert m.supports_tools is True
    assert m.supports_vision is False
