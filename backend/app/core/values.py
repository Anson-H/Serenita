"""Canonical JSON identity and UTC audit timestamps."""

import hashlib
import json
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(dump(value).encode()).hexdigest()
