'''
File:   conversations.py
Brief:  In-memory per-vehicle conversation store feeding the LLM turns.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

One conversation per vehicle: the FSM keeps the chat attached to the
selected vehicle, so the vehicle id is the conversation key. Persistence
across backend restarts is out of hackathon scope; a refresh of the UI
does not reset the LLM context because the store lives server-side.
'''

from __future__ import annotations

from mechanic.llm import ImagePart, TextPart, ToolCall, ToolResult, Turn


class ConversationStore:
    '''Per-vehicle conversation histories as protocol-agnostic turns.'''

    def __init__(self) -> None:
        self._turns: dict[str, list[Turn]] = {}

    def history(self, vehicle_id: str) -> list[Turn]:
        '''Return a shallow copy of the conversation turns.'''
        return list(self._turns.get(vehicle_id, ()))

    def add_user_message(
        self, vehicle_id: str, text: str, image: str | None = None
    ) -> None:
        '''Append a user turn with one text part and an optional image.

        When *image* is provided the turn carries both a :class:`TextPart` and
        a :class:`ImagePart`; otherwise only the text part is stored.

        Args:
            vehicle_id: Vehicle key for the conversation.
            text: User message text.
            image: Optional data-URL image (``data:image/<type>;base64,...``).
        '''
        parts: list[TextPart | ImagePart] = [TextPart(text=text)]
        if image is not None and image.startswith("data:image/"):
            try:
                mime, b64 = image.split(",", 1)
                mime_type = mime[len("data:image/"):-len(";base64")]
                parts.append(ImagePart(mime_type=mime_type, data_b64=b64))
            except (ValueError, IndexError):
                pass  # malformed data-URL — store text only
        self._turns.setdefault(vehicle_id, []).append(
            Turn(role="user", parts=parts)
        )

    def add_assistant_parts(
        self, vehicle_id: str, parts: list[TextPart | ToolCall]
    ) -> None:
        '''Append an assistant turn (text and/or tool-call parts).'''
        if not parts:
            return
        self._turns.setdefault(vehicle_id, []).append(
            Turn(role="assistant", parts=list(parts))
        )

    def add_tool_results(
        self, vehicle_id: str, results: list[ToolResult]
    ) -> None:
        '''Append one tool turn with the given results.'''
        if not results:
            return
        self._turns.setdefault(vehicle_id, []).append(
            Turn(role="tool", parts=list(results))
        )

    def reset(self, vehicle_id: str) -> None:
        '''Drop the conversation for a vehicle (the "new check" action).'''
        self._turns.pop(vehicle_id, None)
