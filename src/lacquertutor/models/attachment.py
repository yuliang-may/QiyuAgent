"""Attachment metadata stored with session state."""

from __future__ import annotations

from pydantic import BaseModel


class AttachmentMeta(BaseModel):
    attachment_id: str
    filename: str
    stored_name: str
    relative_path: str
    mime_type: str
    size_bytes: int
    created_at: str
    linked_step_number: int | None = None
    linked_checkpoint_id: str = ""
    note: str = ""
