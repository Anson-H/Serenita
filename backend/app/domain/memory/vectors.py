"""Validate float32 vector content and report memory-index contract errors."""
import math,struct,hashlib
from backend.app.core.errors import SerenitaError

def fail(code, message, *, kind="invalid_structure"):
    raise SerenitaError(kind, code, message)


def canonical_vector(values, dimensions):
    if len(values) != dimensions or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in values):
        fail("MEMORY_VECTOR_INVALID", "向量维度或数值不符合绑定空间。")
    try:
        packed = struct.pack(f"<{dimensions}f", *values)
        vector = list(struct.unpack(f"<{dimensions}f", packed))
    except (OverflowError, struct.error):
        fail("MEMORY_VECTOR_INVALID", "向量无法精确保存为有限 float32 数值。")
    if not all(math.isfinite(x) for x in vector) or not any(x != 0 for x in vector):
        fail("MEMORY_VECTOR_INVALID", "余弦检索需要非零有限向量。")
    return vector, hashlib.sha256(packed).hexdigest()

