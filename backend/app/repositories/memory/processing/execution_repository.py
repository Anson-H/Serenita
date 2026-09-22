"""Read exact execution coordinates and durable model responses within member scope."""
import json


class MemoryExecutionRepository:
    def __init__(self, repository):
        self.repository = repository

    def positions(self, actor, member, attempt_id):
        with self.repository._transaction(actor, member) as (access, db):
            self.repository._require(db, access, 'processing_attempt', attempt_id)
            row = db.execute("SELECT COALESCE(MAX(entry_sequence),0), "
                "COALESCE(MAX(json_extract(payload_json,'$.call_number')),0) FROM execution_entries "
                "WHERE account_id=? AND member_id=? AND attempt_id=?",
                (access.account_id, member, attempt_id)).fetchone()
            return tuple(row)

    def checkpoint_result(self, actor, member, attempt_id, key):
        with self.repository._transaction(actor, member) as (access, db):
            self.repository._require(db, access, 'processing_attempt', attempt_id)
            row = db.execute("SELECT entry_id,payload_json FROM execution_entries WHERE account_id=? "
                "AND member_id=? AND attempt_id=? AND entry_kind='model_result' "
                "AND json_extract(payload_json,'$.checkpoint_key')=? "
                "AND json_extract(payload_json,'$.checkpoint_output') IS NOT NULL "
                "ORDER BY entry_sequence DESC LIMIT 1", (access.account_id, member, attempt_id, key)).fetchone()
            if row is None:
                return None
            return {'reference': {'object_type': 'memory_execution_entry', 'object_id': attempt_id,
                'item_id': row['entry_id']}, 'payload': json.loads(row['payload_json'])}
