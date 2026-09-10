"""Scope-bound cursors for already computed, deterministic result collections."""

import base64
import hashlib
import json


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def collection_page(items, *, scope, cursor=None, limit=24, maximum=100):
    if type(limit) is not int or not 1 <= limit <= maximum:
        raise ValueError(f"每页数量须为 1 至 {maximum}。")
    signature = fingerprint([scope, items])
    offset = 0
    if cursor:
        try:
            token = json.loads(base64.urlsafe_b64decode(cursor))
            offset = token["offset"]
            if (
                token["signature"] != signature
                or type(offset) is not int
                or not 0 <= offset <= len(items)
            ):
                raise ValueError()
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise ValueError("分页范围或数据已改变，请从第一页重新读取。") from exc
    next_offset = offset + limit
    next_cursor = (
        base64.urlsafe_b64encode(
            json.dumps({"signature": signature, "offset": next_offset}).encode()
        ).decode()
        if next_offset < len(items)
        else None
    )
    return {
        "items": items[offset:next_offset],
        "total": len(items),
        "next_cursor": next_cursor,
    }


def seek_cursor(scope, position):
    return base64.urlsafe_b64encode(
        json.dumps(
            {"scope": fingerprint(scope), "position": position}, separators=(",", ":")
        ).encode()
    ).decode()


def seek_position(cursor, *, scope, size):
    if cursor is None:
        return None
    try:
        if not isinstance(cursor, str) or not 1 <= len(cursor) <= 4096:
            raise ValueError()
        token = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
        position = token["position"]
        if (
            token["scope"] != fingerprint(scope)
            or not isinstance(position, list)
            or len(position) != size
            or any(not isinstance(value, str) for value in position)
        ):
            raise ValueError()
        return position
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise ValueError("分页游标与当前范围不一致，请重新读取目录。") from exc
