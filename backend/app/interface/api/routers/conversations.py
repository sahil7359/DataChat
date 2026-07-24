"""Conversation history (FR-15). 404 when unknown; empty repo => not configured."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.domain.ports.repositories import ConversationRepository
from app.domain.value_objects import ConversationId
from app.interface.api.schemas import ConversationResponse, TurnResponse
from app.interface.deps import get_conversation_repo

router = APIRouter(tags=["conversations"])


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    repo: ConversationRepository | None = Depends(get_conversation_repo),
) -> ConversationResponse:
    if repo is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    conversation = await repo.get(ConversationId(conversation_id))
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        turns=[TurnResponse(role=t.role.value, content=t.content) for t in conversation.turns],
    )
