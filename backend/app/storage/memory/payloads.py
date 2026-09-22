"""Immutable, member-scoped, lossless storage for large execution payload values."""
import hashlib
import json
import os
import re
import tempfile
import zlib

from backend.app.core.errors import SerenitaError
from backend.app.storage.paths import ensure_private_directory

_VALUE_KEYS = ('input', 'output', 'operations', 'value', 'prepared_messages', 'content', 'reasoning', 'vectors')


def payload_has_references(value, *, request=False):
    """Inline fragments need no filesystem access; reserved markers still decode."""
    def packed(item):
        return isinstance(item, dict) and '$memory_blob' in item
    return any(packed(value.get(key)) for key in _VALUE_KEYS) or (
        request and isinstance(value.get('request'), dict) and any(packed(item) for item in value['request'].values()))


class MemoryPayloadStore:
    def __init__(self, paths, account, member):
        from backend.app.schemas.memory.values import canonical_uuid
        canonical_uuid(member)
        self.root = paths.account_root(account) / 'memory' / 'payloads' / member

    def pack(self, value):
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
        # Reserved markers are always wrapped, preserving arbitrary input JSON.
        if len(raw) < 2048 and not (isinstance(value, dict) and '$memory_blob' in value):
            return value
        digest = hashlib.sha256(raw).hexdigest()
        ensure_private_directory(self.root)
        path = self.root / (digest + '.json.zlib')
        if path.exists():
            self.unpack({'$memory_blob': digest, 'bytes': len(raw)})
        else:
            fd, pending = tempfile.mkstemp(prefix='.publishing-', dir=self.root)
            try:
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(zlib.compress(raw))
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.link(pending, path)
                except FileExistsError:
                    self.unpack({'$memory_blob': digest, 'bytes': len(raw)})
                directory = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                os.unlink(pending)
        return {'$memory_blob': digest, 'bytes': len(raw)}

    def unpack(self, value):
        if not isinstance(value, dict) or '$memory_blob' not in value:
            return value
        digest = value.get('$memory_blob')
        try:
            if set(value) != {'$memory_blob', 'bytes'} or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
                raise ValueError('invalid payload reference')
            fd = os.open(self.root / (digest + '.json.zlib'), os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as handle:
                raw = zlib.decompress(handle.read())
            if len(raw) != value['bytes'] or hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('payload integrity mismatch')
            return json.loads(raw)
        except (OSError, ValueError, zlib.error) as exc:
            raise SerenitaError('invalid_structure', 'MEMORY_PAYLOAD_UNAVAILABLE', '执行内容缺失或完整性校验失败。') from exc

    def encode(self, value, *, request=False):
        # Root metadata remains queryable in SQLite. Every packed value is exact JSON.
        result = dict(value)
        for key in _VALUE_KEYS:
            if key in result:
                result[key] = self.pack(result[key])
        if request and isinstance(result.get('request'), dict):
            result['request'] = {key: self.pack(item) for key, item in result['request'].items()}
        return result

    def decode(self, value, *, request=False):
        result = dict(value)
        for key in _VALUE_KEYS:
            if key in result:
                result[key] = self.unpack(result[key])
        if request and isinstance(result.get('request'), dict):
            result['request'] = {key: self.unpack(item) for key, item in result['request'].items()}
        return result
