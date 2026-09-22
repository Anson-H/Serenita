from contextlib import contextmanager
from collections import defaultdict
import math

from backend.app.core.pagination import seek_cursor, seek_position
from backend.app.domain.knowledge import search_terms
from backend.app.storage.knowledge_database import KNOWLEDGE_DATABASE_SCHEMA
from backend.app.storage.sqlite import connect
from backend.app.core.business_operation import current_business_operation
from backend.app.repositories.business_change_repository import record_change
from backend.app.repositories.business_operation_repository import begin_operation, finish_operation


DOCUMENT_COLUMNS = "document_id, original_filename, mime_type, size_bytes, sha256, segment_count, created_at"


class KnowledgeRepository:
    def __init__(self, account_id, paths):
        self.account_id, self.paths = account_id, paths
        self.path = paths.knowledge_db(account_id)

    @contextmanager
    def transaction(self, *, write=False):
        self.paths.require_account_tree(self.account_id)
        if not KNOWLEDGE_DATABASE_SCHEMA.validate_existing(self.path):
            with connect(self.path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                KNOWLEDGE_DATABASE_SCHEMA.create(connection)
        with connect(self.path) as connection:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection

    def _document(self, connection, document_id, *, original=False):
        columns = "*" if original else DOCUMENT_COLUMNS
        row = connection.execute(f"SELECT {columns} FROM knowledge_documents WHERE document_id = ?", (document_id,)).fetchone()
        if row is None:
            raise LookupError("知识库文件已删除或不属于当前账号。")
        return dict(row)

    def get(self, document_id, *, original=False):
        with self.transaction() as connection:
            return self._document(connection, document_id, original=original)

    def create(self, document, segments):
        operation = current_business_operation()
        # Original bytes remain in the source store. The hash identifies the
        # exact upload command without retaining a second file in the journal.
        command = {"domain": "knowledge", "action": "create", "values": self._business_values(document)}
        with self.transaction(write=True) as connection:
            replay = begin_operation(connection, self.account_id, operation.operation_id, command)
            if replay is not None:
                self._document(connection, replay["document_id"])
                return replay
            connection.execute("INSERT INTO knowledge_documents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                               tuple(document[key] for key in ("document_id", "original_filename", "mime_type", "size_bytes", "sha256", "content_bytes", "segment_count", "created_at")))
            for segment in segments:
                terms = search_terms(segment["content"])
                terms.update({term: frequency * 3 for term, frequency in search_terms(document["original_filename"]).items()})
                connection.execute("INSERT INTO knowledge_segments VALUES (?, ?, ?, ?, ?)",
                                   (document["document_id"], segment["segment_index"], segment["page_number"], segment["content"], sum(terms.values())))
                connection.executemany("INSERT INTO knowledge_terms VALUES (?, ?, ?, ?)",
                                       ((document["document_id"], segment["segment_index"], term, frequency) for term, frequency in terms.items()))
            result = self._document(connection, document["document_id"])
            record_change(connection, actor_account_id=self.account_id, operation_id=operation.operation_id,
                          scope_kind="account", member_id=None, resource_type="knowledge_document",
                          resource_id=document["document_id"], before=None, after=self._business_values(result),
                          context={"original_filename": result["original_filename"], "content_role": "reference_material"},
                          origin_kind=operation.origin_kind)
            return finish_operation(connection, self.account_id, operation.operation_id, result)

    @staticmethod
    def _business_values(document):
        return {f"/{key}": document[key] for key in ("original_filename", "mime_type", "size_bytes", "sha256", "segment_count")}

    def catalog(self, *, cursor=None, limit=30):
        scope = ["knowledge", self.account_id]
        position = seek_position(cursor, scope=scope, size=2)
        with self.transaction() as connection:
            total = connection.execute("SELECT count(*) FROM knowledge_documents").fetchone()[0]
            condition = " WHERE (created_at, document_id) < (?, ?)" if position else ""
            rows = connection.execute(f"SELECT {DOCUMENT_COLUMNS} FROM knowledge_documents" + condition
                                      + " ORDER BY created_at DESC, document_id DESC LIMIT ?", [*(position or []), limit + 1]).fetchall()
        documents = [dict(row) for row in rows[:limit]]
        following = seek_cursor(scope, [documents[-1][key] for key in ("created_at", "document_id")]) if len(rows) > limit else None
        return {"documents": documents, "total": total, "next_cursor": following}

    def read(self, document_id, *, segment_start, segment_count):
        with self.transaction() as connection:
            document = self._document(connection, document_id)
            segments = [dict(row) for row in connection.execute(
                "SELECT segment_index, page_number, content FROM knowledge_segments WHERE document_id = ? AND segment_index >= ? ORDER BY segment_index LIMIT ?",
                (document_id, segment_start, segment_count),
            )]
        return document, segments

    def search(self, query, *, limit=8):
        terms = list(search_terms(query))
        if not terms:
            return {"results": [], "matching_documents": 0, "has_more": False}
        scores = defaultdict(float)
        with self.transaction() as connection:
            total, average = connection.execute("SELECT count(*), avg(token_count) FROM knowledge_segments").fetchone()
            if not total:
                return {"results": [], "matching_documents": 0, "has_more": False}
            placeholders = ",".join("?" for _ in terms)
            frequencies = dict(connection.execute(f"SELECT term, count(*) FROM knowledge_terms WHERE term IN ({placeholders}) GROUP BY term", terms))
            rows = connection.execute(
                f"SELECT t.document_id, t.segment_index, t.term, t.frequency, s.token_count FROM knowledge_terms t JOIN knowledge_segments s USING (document_id, segment_index) WHERE t.term IN ({placeholders})", terms)
            for row in rows:
                inverse = math.log1p((total - frequencies[row["term"]] + 0.5) / (frequencies[row["term"]] + 0.5))
                frequency = row["frequency"]
                scores[(row["document_id"], row["segment_index"])] += inverse * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * row["token_count"] / max(average, 1)))
            best = {}
            for key in sorted(scores, key=lambda key: (-scores[key], key)):
                best.setdefault(key[0], key)
            results = []
            for document_id, key in list(best.items())[:limit]:
                document = self._document(connection, document_id)
                segment = dict(connection.execute("SELECT segment_index, page_number, content FROM knowledge_segments WHERE document_id = ? AND segment_index = ?", key).fetchone())
                content = segment.pop("content")
                normalized = content.casefold()
                offsets = [normalized.find(term) for term in terms if term in normalized]
                start = max(0, min(offsets, default=0) - 80)
                results.append({**document, **segment, "excerpt": content[start:start + 400], "score": round(scores[key], 4)})
        return {"results": results, "matching_documents": len(best), "has_more": len(best) > limit}

    def delete(self, document_id):
        operation = current_business_operation()
        with self.transaction(write=True) as connection:
            replay = begin_operation(connection, self.account_id, operation.operation_id,
                                     {"domain": "knowledge", "action": "delete", "document_id": document_id})
            if replay is not None:
                return replay
            document = self._document(connection, document_id)
            connection.execute("DELETE FROM knowledge_documents WHERE document_id = ?", (document_id,))
            record_change(connection, actor_account_id=self.account_id, operation_id=operation.operation_id,
                          scope_kind="account", member_id=None, resource_type="knowledge_document", resource_id=document_id,
                          before=self._business_values(document), after=None,
                          context={"original_filename": document["original_filename"], "content_role": "reference_material"},
                          origin_kind=operation.origin_kind)
            return finish_operation(connection, self.account_id, operation.operation_id,
                                    {"document_id": document_id, "deleted": True})
