"""Lossless columnar encoding for arrays of same-shape JSON objects.

Tool Observations frequently repeat one identical key set across many rows
(lab dictionary items, catalog entries, evidence tables). Each such array is
encoded as ``{"$keys": [...keys in logical output order...], "$rows": [[...values...]]}`` at the
tool-result boundary, so the persisted timeline and the model request share
one compact form. The transform is purely mechanical, deterministic and
reversible; ``$``-prefixed keys never collide with business evidence keys.
Deterministic consumers that need structural access decode before use.
"""

from __future__ import annotations

from typing import Any


def encode_tabular_json(value: Any) -> Any:
    """Encode arrays of two or more same-shape dicts as ``$keys``/``$rows``.

    Any list of two or more dicts sharing an identical key set becomes
    ``{"$keys": [...first-row key order...], "$rows": [[...values in $keys order...]]}``;
    every other shape is preserved. Preserving the first logical object's key
    order keeps the persisted output aligned with the Tool's output contract.
    The transform is recursive, so tables nested inside row values or enclosing
    objects are encoded as well.
    """

    if isinstance(value, list):
        items = [encode_tabular_json(item) for item in value]
        if len(items) >= 2 and all(isinstance(item, dict) for item in items):
            keys = list(items[0])
            key_set = set(keys)
            if all(set(item) == key_set for item in items[1:]):
                return {
                    "$keys": keys,
                    "$rows": [[item[key] for key in keys] for item in items],
                }
        return items
    if isinstance(value, dict):
        return {key: encode_tabular_json(item) for key, item in value.items()}
    return value


def decode_tabular_json(value: Any) -> Any:
    """Inverse of :func:`encode_tabular_json`; restores the original shape.

    Any dict holding exactly ``$keys``/``$rows`` expands back to a list of
    dicts; every other shape is preserved. Deterministic consumers that need
    structural access to a persisted Observation must decode before use.
    """

    if isinstance(value, dict):
        if set(value) == {"$keys", "$rows"}:
            keys = value["$keys"]
            rows = value["$rows"]
            well_formed = (
                isinstance(keys, list)
                and all(isinstance(key, str) for key in keys)
                and isinstance(rows, list)
                and all(
                    isinstance(row, list) and len(row) == len(keys) for row in rows
                )
            )
            if well_formed:
                return [
                    {
                        key: decode_tabular_json(item)
                        for key, item in zip(keys, row)
                    }
                    for row in rows
                ]
        return {key: decode_tabular_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode_tabular_json(item) for item in value]
    return value
