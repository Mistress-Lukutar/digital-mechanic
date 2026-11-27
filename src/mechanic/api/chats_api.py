'''
File:   chats_api.py
Brief:  Chat conversation listing, retrieval, deletion, and branch-switch
        endpoints.
Author: Mistress-Lukutar
Date:   2026-11-27
Version: v0.2.0

Provides the ``/api/chats`` router with endpoints for listing conversations,
fetching individual chat threads with messages, deleting conversations, and
switching the active branch of a conversation.
'''

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from mechanic.api.deps import current_user, get_conversations, get_hub
from mechanic.services.auth import TokenUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chats", tags=["chats"])


@router.get("")
async def list_chats(
    vehicle_id: str = Query(...),
    user: TokenUser = Depends(current_user),
) -> list[dict]:
    """List conversations for the authenticated user on a given vehicle."""
    return get_hub().chats.list_conversations(user.username, vehicle_id)


@router.get("/{conversation_id}")
async def get_chat(
    conversation_id: str,
    user: TokenUser = Depends(current_user),
) -> dict:
    """Retrieve a single conversation with its messages."""
    conv = get_hub().chats.get_conversation(conversation_id)
    if conv is None or conv["username"] != user.username:
        raise HTTPException(status_code=404, detail="чат не найден")
    return {
        "conversation": conv,
        "messages": get_hub().chats.get_messages(conversation_id),
    }


class BranchRequest(BaseModel):
    """Branch-switch request body.

    Attributes:
        message_id: Message whose branch should become active.
    """

    message_id: int


@router.post("/{conversation_id}/branch")
async def switch_branch(
    conversation_id: str,
    body: BranchRequest,
    user: TokenUser = Depends(current_user),
) -> dict:
    """Activate the branch containing *message_id* and return the dialog."""
    hub = get_hub()
    conv = hub.chats.get_conversation(conversation_id)
    if conv is None or conv["username"] != user.username:
        raise HTTPException(status_code=404, detail="чат не найден")
    if not hub.chats.switch_branch(conversation_id, body.message_id):
        raise HTTPException(status_code=404, detail="сообщение не найдено")
    # Force re-hydration of the in-memory LLM store from the new path.
    get_conversations().forget(conversation_id)
    return {
        "conversation": conv,
        "messages": hub.chats.get_messages(conversation_id),
    }


@router.delete("/{conversation_id}")
async def delete_chat(
    conversation_id: str,
    user: TokenUser = Depends(current_user),
) -> dict:
    """Delete a conversation and its in-memory LLM turns."""
    conv = get_hub().chats.get_conversation(conversation_id)
    if conv is None or conv["username"] != user.username:
        raise HTTPException(status_code=404, detail="чат не найден")
    get_hub().chats.delete_conversation(conversation_id)
    get_conversations().forget(conversation_id)
    return {"status": "deleted"}
