from __future__ import annotations

import unicodedata


def normalize_entity_name(value: str) -> str:
    """Return a stable comparison key for entity names and aliases.

    Entity identity remains scoped by user and entity type.  This deliberately
    only removes presentation differences (case, width, whitespace and
    punctuation); it does not try to infer that two different words are the
    same real-world entity.
    """

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def normalize_entity_type(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()
