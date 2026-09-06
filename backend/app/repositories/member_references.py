"""Explicit participant registration; data ownership stays with each store."""

from backend.app.storage.conversation_database import conversation_member_references
from backend.app.storage.favorite_database import favorite_member_references


def member_reference_stores(paths):
    return (conversation_member_references(paths), favorite_member_references(paths))
