"""Conversation domain model — Sprint 5e (multi-turn support).

A request is now a list of messages instead of a single query string.
The role/content shape mirrors the OpenAI / Anthropic chat message
convention so the generator can hand it to the LLM with minimal
massaging.

Scope rules:
  - Only ``user`` and ``assistant`` roles cross the wire. The system
    prompt is owned by the generator and chosen by task_type.
  - Empty content strings are not allowed for ``user`` messages — that
    would mean a turn with nothing to retrieve against. Validators
    enforce this on the API boundary.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

Role = Literal["user", "assistant"]


class ConvMessage(BaseModel):
    role: Role
    content: str

    @field_validator("content")
    @classmethod
    def _trim(cls, v: str) -> str:
        return v.strip()


def latest_user_message(messages: list[ConvMessage]) -> str:
    """Return the most recent user-authored content. Empty string if
    there is no user message — caller should treat that as an empty
    request and skip retrieval."""
    for m in reversed(messages):
        if m.role == "user" and m.content:
            return m.content
    return ""


def conversation_summary(messages: list[ConvMessage], *, max_chars: int = 1200) -> str:
    """Render the conversation as a compact transcript for prompts that
    need to "see" the conversation but not as actual chat messages —
    e.g. the context-aware rewriter."""
    lines: list[str] = []
    used = 0
    for m in reversed(messages):
        line = f"{m.role.upper()}: {m.content}"
        if used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line)
    return "\n".join(reversed(lines))
