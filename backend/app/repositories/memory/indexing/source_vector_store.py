"""Physical source-fragment vectors retain exact business field coordinates."""
from backend.app.repositories.memory.indexing.vector_store import LanceVectors

class LanceSourceChunks(LanceVectors):
    index_name = 'source_chunks'
    string_fields = (LanceVectors.identity_fields + LanceVectors.reference_fields
        + tuple((key, False) for key in ('chunk_id', 'source_database', 'change_id', 'field_path'))
        + LanceVectors.metadata_fields + (('content', False),))
    integer_fields = ('character_start', 'character_end', 'rank')

    @staticmethod
    def expected(account, member, binding, space):
        return {**LanceVectors.expected(account, member, binding, space),
            **{key: binding[key] for key in ('chunk_id', 'source_database', 'change_id', 'field_path',
                'character_start', 'character_end', 'rank', 'content')}}

