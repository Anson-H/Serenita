"""Read, verify and append physical LanceDB vectors with scoped write receipts."""
from contextlib import contextmanager
from collections import defaultdict
import fcntl,math,time
from backend.app.core.errors import SerenitaError
from backend.app.schemas.memory.append import canonical_uuid
from backend.app.domain.memory.vectors import fail,canonical_vector

class LanceVectors:
    index_name = 'event_vectors'
    vector_field = 'content_vector'
    integer_fields = ()
    identity_fields = (('vector_id', False), ('account_id', False), ('member_id', False))
    reference_fields = (('binding_id', False), ('event_id', False), ('space_id', False))
    metadata_fields = tuple((key, False) for key in (
        'model_id', 'provider_id', 'remote_model_id', 'model_signature', 'text_hash', 'vector_hash'))
    string_fields = identity_fields + reference_fields + metadata_fields
    def __init__(self, paths):
        self.paths = paths

    def path(self, account_id):
        return self.paths.memory_vectors_dir(account_id)

    @classmethod
    def table_name(cls, space_id):
        canonical_uuid(space_id)
        return cls.index_name

    def space_path(self, account_id, space_id):
        return self.path(account_id) / canonical_uuid(space_id)

    @contextmanager
    def binding_guard(self, account_id, binding_id, *, check_running=None):
        canonical_uuid(binding_id)
        directory = self.path(account_id) / ".locks"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (directory / binding_id).open("a") as handle:
            while True:
                if check_running:
                    check_running()
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    time.sleep(.02)
            try:
                from backend.app.repositories.memory.indexing.vector_receipts import vector_receipt_scope
                with vector_receipt_scope(self.path(account_id), account_id, binding_id):
                    yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _table(self, account_id, space, *, create=False):
        import lancedb
        import pyarrow as pa
        path = self.space_path(account_id, space['space_id'])
        name = self.table_name(space["space_id"])
        if not create and not (path / (name + ".lance")).exists():
            return None
        if create:
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = lancedb.connect(str(path))
        try:
            return db.open_table(name)
        except (ValueError, FileNotFoundError):
            if not create:
                return None
        fields = [pa.field(key, pa.string(), nullable=nullable) for key, nullable in self.string_fields]
        fields.extend(pa.field(key, pa.int64(), nullable=False) for key in self.integer_fields)
        schema = pa.schema([*fields, pa.field("dimensions", pa.int32(), nullable=False), pa.field(self.vector_field, pa.list_(pa.float32(), space["dimensions"]), nullable=False)])
        try:
            return db.create_table(name, schema=schema)
        except ValueError:
            # A different binding may create the same immutable space table.
            return db.open_table(name)

    def rows(self, account_id, space, vector_id):
        canonical_uuid(vector_id)
        from backend.app.repositories.memory.indexing.vector_receipts import remembered_vector
        receipt = remembered_vector(self, account_id, space, vector_id)
        if receipt is not None:
            return [receipt]
        from backend.app.repositories.memory.indexing.vector_cache import cached_row
        draft = cached_row(self, account_id, space, vector_id)
        if draft is not None:
            return [draft]
        table = self._table(account_id, space)
        return [] if table is None else table.search().where(f"vector_id = '{vector_id}'").limit(2).to_list()

    @staticmethod
    def expected(account_id, member_id, binding, space):
        return {"account_id": account_id, "member_id": member_id,
                **{key: binding[key] for key in ("vector_id", "binding_id", "event_id", "space_id", "text_hash")},
                **{key: space[key] for key in ("model_id", "provider_id", "remote_model_id", "model_signature", "dimensions")}}

    def confirm(self, account_id, member_id, binding, space, vector_hash):
        """Use the successful storage result held by this delivery lock."""
        from backend.app.repositories.memory.indexing.vector_receipts import remembered_vector
        row = remembered_vector(self, account_id, space, binding['vector_id'])
        if row is None or row.get('vector_hash') != vector_hash or any(
                row.get(key) != value for key, value in self.expected(account_id, member_id, binding, space).items()):
            fail('MEMORY_VECTOR_UNCONFIRMED', '当前交付尚未取得向量保存成功的结果。')
        return row

    def verify(self, account_id, member_id, binding, space, vector_hash):
        rows = self.rows(account_id, space, binding["vector_id"])
        if len(rows) != 1:
            fail("MEMORY_VECTOR_UNCONFIRMED", "绑定必须对应唯一且完整的实际向量行。")
        return self.verify_row(account_id, member_id, binding, space, vector_hash, rows[0])

    def verify_row(self, account_id, member_id, binding, space, vector_hash, row):
        from backend.app.repositories.memory.indexing.vector_receipts import remembered_vector
        verified = self._verified_row(account_id, member_id, binding, space, vector_hash, row)
        remembered_vector(self, account_id, space, binding['vector_id'], verified)
        return verified

    def _verified_row(self, account_id, member_id, binding, space, vector_hash, row):
        if any(row.get(key) != value for key, value in self.expected(account_id, member_id, binding, space).items()):
            fail("MEMORY_VECTOR_IDENTITY_MISMATCH", "实际向量身份或模型空间与绑定不一致。")
        _, actual_hash = canonical_vector(row[self.vector_field], space["dimensions"])
        if row.get("vector_hash") != actual_hash or vector_hash != actual_hash:
            fail("MEMORY_VECTOR_HASH_MISMATCH", "实际向量内容与确认校验值不一致。")
        return row

    @staticmethod
    def _binding_rows(table, bindings):
        """Read bounded groups from one table snapshot, retaining duplicates.

        Never persist a verification cache: every search reads the actual rows.
        A corrupt group that exceeds the row bound is rejected in full, so a
        duplicate cannot hide another binding beyond a truncated result.
        """
        for start in range(0, len(bindings), 1024):
            group = bindings[start:start + 1024]
            ids = ",".join("'" + canonical_uuid(row["vector_id"]) + "'" for row in group)
            rows = table.search().where(f"vector_id IN ({ids})").limit(2 * len(group) + 1).to_list()
            by_id = defaultdict(list)
            if len(rows) <= 2 * len(group):
                for row in rows:
                    by_id[row["vector_id"]].append(row)
            for binding in group:
                yield binding, by_id[binding["vector_id"]]

    def add(self, account_id, member_id, binding, space, values):
        """Append a target selected by the service while holding its delivery lock."""
        vector, digest = canonical_vector(values, space["dimensions"])
        row = {**self.expected(account_id, member_id, binding, space), "vector_hash": digest, self.vector_field: vector}
        from backend.app.repositories.memory.indexing.vector_cache import cache_vector
        if not cache_vector(self, account_id, space, row):
            self._table(account_id, space, create=True).add([row])
        # The storage call has completed successfully. Reuse its exact written
        # row for this delivery's confirmation; do not read the vector back.
        from backend.app.repositories.memory.indexing.vector_receipts import remembered_vector
        remembered_vector(self, account_id, space, binding['vector_id'], row)
        return digest

    def verify_many(self, account_id, member_id, bindings, space):
        """Freshly verify the exact requested bindings in one physical snapshot.

        The returned mapping is keyed by binding identity, so another binding
        for the same description cannot stand in for a missing original hit.
        No validation result survives this call and no table is created.
        """
        if not bindings:
            return {}, []
        if len({row['binding_id'] for row in bindings}) != len(bindings):
            raise ValueError('Exact binding verification requires unique binding identities')
        from backend.app.repositories.memory.processing.staging_scope import staging
        if staging() is not None:
            verified, failures = {}, []
            for binding in bindings:
                try:
                    self.verify(account_id, member_id, binding, space, binding['vector_hash'])
                    verified[binding['binding_id']] = binding
                except SerenitaError as error:
                    failures.append({'binding_id': binding['binding_id'], 'code': error.code})
            return verified, failures
        return self._verify_bindings(self._table(account_id, space), account_id, member_id, bindings, space)

    def _verify_bindings(self, table, account_id, member_id, bindings, space):
        if table is None:
            return {}, [{'binding_id': row['binding_id'], 'code': 'MEMORY_VECTOR_UNCONFIRMED'} for row in bindings]
        verified, failures = {}, []
        for binding, rows in self._binding_rows(table, bindings):
            try:
                if len(rows) != 1:
                    fail('MEMORY_VECTOR_UNCONFIRMED', '绑定必须对应唯一且完整的实际向量行。')
                self._verified_row(account_id, member_id, binding, space, binding['vector_hash'], rows[0])
                verified[binding['binding_id']] = binding
            except SerenitaError as exc:
                failures.append({'binding_id': binding['binding_id'], 'code': exc.code})
        return verified, failures

    def search(self, account_id, member_id, space, vector, confirmed):
        """Verify every allowed row before exact cosine search; reject orphans."""
        from backend.app.repositories.memory.processing.staging_scope import staging
        if staging() is not None:
            verified, failures = self.verify_many(account_id, member_id, confirmed, space)
            norm = math.sqrt(sum(value * value for value in vector))
            results = []
            for binding in verified.values():
                values = self.rows(account_id, space, binding['vector_id'])[0][self.vector_field]
                score = sum(a*b for a,b in zip(vector, values)) / (norm * math.sqrt(sum(value*value for value in values)))
                results.append({**binding, 'score': score})
            return sorted(results, key=lambda row: row['score'], reverse=True), failures
        table = self._table(account_id, space)
        if not confirmed:
            return [], []
        verified, failures = self._verify_bindings(table, account_id, member_id, confirmed, space)
        permitted = {binding['vector_id']: binding for binding in verified.values()}
        if not permitted:
            return [], failures
        # UUIDs are validated by the schema and row verification; this predicate
        # prevents orphan/pending rows from consuming the recall limit.
        ids = ",".join("'" + canonical_uuid(value) + "'" for value in permitted)
        rows = table.search(vector, vector_column_name=self.vector_field).distance_type("cosine").bypass_vector_index().where(f"vector_id IN ({ids})", prefilter=True).limit(len(permitted)).to_list()
        results = []
        for row in rows:
            binding = permitted.get(row["vector_id"])
            if binding is not None:
                results.append({**binding, "score": 1.0 - float(row["_distance"])})
        return results, failures

