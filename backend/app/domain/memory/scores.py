"""Score conversion shared by SAG adapters and persisted evidence checks."""
import math
from backend.app.core.errors import SerenitaError

def sag_score(cosine):
    """Match upstream Elasticsearch cosine kNN _score, retaining raw evidence.

    https://www.elastic.co/guide/en/elasticsearch/reference/8.19/dense-vector.html
    """
    if not math.isfinite(cosine) or not -1.000001 <= cosine <= 1.000001:
        raise SerenitaError('invalid_input', 'MEMORY_VECTOR_SCORE_INVALID', '向量相似度不是有效余弦分数。')
    return (1.0 + min(1.0, max(-1.0, cosine))) / 2.0

