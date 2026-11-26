'''
File:   __init__.py
Brief:  Provider-agnostic LLM client package (chat streaming, tools, models).
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0
'''

from mechanic.llm.anthropic_client import AnthropicClient
from mechanic.llm.factory import get_llm_client, get_shared_http_client
from mechanic.llm.gemini_client import GeminiClient
from mechanic.llm.openai_client import OpenAiClient
from mechanic.llm.sse import iter_sse_frames
from mechanic.llm.types import (
    PROTOCOL_DEFAULT_BASE_URLS,
    AiProtocol,
    ChatRequest,
    Endpoint,
    ImagePart,
    LLMClient,
    LLMError,
    ModelInfo,
    ReasoningDelta,
    StopReason,
    StreamError,
    TextDelta,
    TextPart,
    ToolCall,
    ToolCallsReady,
    ToolResult,
    ToolSpec,
    Turn,
    TurnComplete,
    guess_model_capabilities,
)

__all__ = [
    "AiProtocol",
    "PROTOCOL_DEFAULT_BASE_URLS",
    "LLMError",
    "LLMClient",
    "ImagePart",
    "TextPart",
    "ToolCall",
    "ToolResult",
    "Turn",
    "ToolSpec",
    "Endpoint",
    "ChatRequest",
    "StopReason",
    "ModelInfo",
    "TextDelta",
    "ReasoningDelta",
    "ToolCallsReady",
    "TurnComplete",
    "StreamError",
    "guess_model_capabilities",
    "get_llm_client",
    "get_shared_http_client",
    "OpenAiClient",
    "AnthropicClient",
    "GeminiClient",
    "iter_sse_frames",
]
