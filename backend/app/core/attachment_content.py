"""Verified attachment content shared by capability boundaries."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AttachmentContent:
    resource_id: str
    original_filename: str
    mime_type: str
    content_bytes: bytes
