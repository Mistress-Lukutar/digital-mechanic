'''
File:   chat_api.py
Brief:  Chat endpoint with SSE streaming, conversation reset, and language selection.
Author: Mistress-Lukutar
Date:   2026-11-27
Version: v0.2.0

Provides the ``/api/chat`` router with a streaming chat endpoint that wraps
the :class:`~mechanic.agent.loop.AgentLoop` and yields SSE-formatted events,
plus a reset endpoint to clear a vehicle's conversation history. Supports an
optional ``language`` field on ``ChatRequest`` for non-Russian responses.

Multimodal support: ``ChatRequest`` accepts an optional ``image`` data-URL
that is forwarded into the agent turn as a multimodal content part.
'''

from __future__ import annotations

import json
import logging
import re
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from mechanic.agent.conversations import ConversationStore
from mechanic.agent.loop import AgentLoop
from mechanic.agent.prompt import build_system_prompt
from mechanic.api.deps import (
    get_app_settings,
    get_conversations,
    get_hub,
)
from mechanic.errors import FleetError
from mechanic.llm import AiProtocol, Endpoint, get_llm_client
from mechanic.services.app_settings import LlmConfig, effective_llm_config

logger = logging.getLogger(__name__)


def _extract_citations(text: str) -> list[dict]:
    """Extract document citations from markdown text.

    Matches the pattern ``[doc_id, стр. N]`` used by the frontend and
    returns deduplicated entries capped at 20.

    Args:
        text: The full response text to scan for citations.

    Returns:
        A list of ``{"doc": ..., "page": ...}`` dicts in first-occurrence order.
    """
    pattern = r"\[([^<>,\[\]]+), стр\. (\d+)\]"
    seen: set[tuple[str, int]] = set()
    citations: list[dict] = []
    for match in re.finditer(pattern, text):
        doc_id = match.group(1).strip("«»").strip()
        page = int(match.group(2))
        pair = (doc_id, page)
        if pair not in seen:
            seen.add(pair)
            citations.append({"doc": doc_id, "page": page})
            if len(citations) >= 20:
                break
    return citations


router = APIRouter(prefix="/api", tags=["chat"])

# Maximum length for a data-URL image (~1.5 MB JPEG base64-encoded).
_MAX_IMAGE_URL_LEN = 2_100_000


class ChatRequest(BaseModel):
    """Chat message request body.

    Attributes:
        message: User message text.
        session_id: Optional session identifier for the vehicle check.
        language: Target response language (ru, kk, uz, hi); defaults to ru.
        image: Optional data-URL image (``data:image/...``). Must be ≤ 2 100 000 chars.
    """

    message: str
    session_id: str | None = None
    language: Literal["ru", "kk", "uz", "hi"] | None = None
    image: str | None = None

    @field_validator("image")
    @classmethod
    def _validate_image(cls, value: str | None) -> str | None:
        """Validate an optional data-URL image field.

        Args:
            value: The raw string from the request body.

        Returns:
            *value* unchanged if valid.

        Raises:
            ValueError: When the image is not a ``data:image/`` URL or exceeds
                the length limit.
        """
        if value is None:
            return None
        if not value.startswith("data:image/"):
            raise ValueError(
                "Изображение: поддерживаются data-URL до 1.5 МБ"
            )
        if len(value) > _MAX_IMAGE_URL_LEN:
            raise ValueError(
                "Изображение: поддерживаются data-URL до 1.5 МБ"
            )
        return value


async def _auth_user(request: Request) -> object:  # TokenUser
    """Resolve bearer token to :class:`TokenUser`."""
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="требуется авторизация",
        )
    token = auth_header[7:]
    user = get_hub().auth.resolve_token(token)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="требуется авторизация",
        )
    return user


def _build_registry(hub: object) -> object:  # ToolRegistry
    """Build the tool registry from the hub.

    Args:
        hub: ServiceHub instance.

    Returns:
        A :class:`~mechanic.agent.tools_base.ToolRegistry`.
    """
    from mechanic.agent.tools_impl import build_registry

    return build_registry(hub)


async def _chat_events(
    vehicle_id: str,
    message: str,
    session_id: str | None,
    username: str,
    hub: object,  # ServiceHub
    conversations: ConversationStore,
    llm_cfg: LlmConfig,
    language: Literal["ru", "kk", "uz", "hi"] | None = None,
    image: str | None = None,
) -> object:  # AsyncIterator[tuple[str, dict]]
    """Generate SSE events from the agent loop.

    Args:
        vehicle_id: Selected vehicle.
        message: User message text.
        session_id: Optional session identifier.
        username: Authenticated user.
        hub: ServiceHub instance.
        conversations: Conversation store.
        llm_cfg: Effective LLM configuration.
        language: Target response language (ru/kk/uz/hi).
        image: Optional data-URL image for multimodal input.

    Yields:
        (event_name, payload) tuples from the agent loop.
    """
    protocol = AiProtocol(llm_cfg.protocol)
    client = get_llm_client(protocol)
    endpoint = Endpoint(
        base_url=llm_cfg.base_url,
        api_key=llm_cfg.api_key,
        model_id=llm_cfg.model,
        protocol=protocol,
    )
    registry = _build_registry(hub)
    system_prompt = build_system_prompt(hub, vehicle_id, language=language)

    loop = AgentLoop(
        client=client,
        endpoint=endpoint,
        registry=registry,
        store=conversations,
        system_prompt=system_prompt,
        temperature=llm_cfg.temperature,
        max_output_tokens=llm_cfg.max_output_tokens,
        tool_services=hub,
    )

    async for name, payload in loop.run(
        vehicle_id, message, session_id, username, image=image
    ):
        yield (name, payload)


@router.post("/chat/{vehicle_id}")
async def chat(
    vehicle_id: str,
    body: ChatRequest,
    user=Depends(_auth_user),
) -> StreamingResponse:
    """Stream a chat response for *vehicle_id* via SSE."""
    hub = get_hub()
    conversations = get_conversations()

    # Check vehicle exists BEFORE streaming.
    try:
        hub.fleet.get_vehicle(vehicle_id)
    except FleetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    llm_cfg = effective_llm_config(hub.settings, get_app_settings())

    async def event_stream() -> object:  # AsyncIterator[str]
        """SSE event stream."""
        t0 = time.perf_counter()
        answer_parts: list[str] = []
        tools_used: list[str] = []
        ticket_draft_info: dict | None = None
        async for name, payload in _chat_events(
            vehicle_id,
            body.message,
            body.session_id,
            user.username,
            hub,
            conversations,
            llm_cfg,
            language=body.language or "ru",
            image=body.image,
        ):
            yield f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

            if name == "token":
                answer_parts.append(payload.get("text", ""))
            elif name == "tool_start":
                tool_name = payload.get("name")
                if tool_name is not None and tool_name not in tools_used:
                    tools_used.append(tool_name)
            elif name == "ticket_draft":
                ticket_draft_info = {
                    "anomaly_type": payload.get("payload", {}).get("anomaly_type"),
                    "urgency": payload.get("payload", {}).get("urgency"),
                }
            elif name == "turn_done":
                usage = payload.get("usage", {}) or {}
                detail = {
                    "question": body.message[:4000],
                    "answer": "".join(answer_parts)[:4000],
                    "tools": tools_used,
                    "citations": _extract_citations("".join(answer_parts)),
                    "ticket_draft": ticket_draft_info,
                    "has_image": body.image is not None,
                    "language": body.language,
                }
                hub.usage.record(
                    username=user.username,
                    kind="chat",
                    vehicle_id=vehicle_id,
                    model=llm_cfg.model,
                    input_tokens=usage.get("input_tokens") or 0,
                    output_tokens=usage.get("output_tokens") or 0,
                    duration_ms=int((time.perf_counter() - t0) * 1000),
                    status="ok",
                    detail=detail,
                )
            elif name == "error":
                hub.usage.record(
                    username=user.username,
                    kind="chat",
                    vehicle_id=vehicle_id,
                    model=llm_cfg.model,
                    input_tokens=0,
                    output_tokens=0,
                    duration_ms=int((time.perf_counter() - t0) * 1000),
                    status="error",
                    error=payload.get("message", "")[:300],
                )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/{vehicle_id}/reset")
async def reset_chat(
    vehicle_id: str,
    user=Depends(_auth_user),
) -> dict:
    """Reset the conversation for *vehicle_id*."""
    conversations = get_conversations()
    conversations.reset(vehicle_id)
    return {"status": "reset"}
