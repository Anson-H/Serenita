"""Episode invariants and revision projection within the memory transaction."""
from copy import deepcopy

from backend.app.core.errors import SerenitaError


def fail(code, message):
    raise SerenitaError("conflict", code, message)


def ref(kind, identity, *, version=None, item_id=None):
    return {"object_type": kind, "object_id": identity, "version": version, "item_id": item_id}


def key(value):
    return (value["object_type"], value["object_id"], value.get("version"), value.get("item_id"))


def _require(repo, connection, access, reference, *, cutoff=None):
    if hasattr(reference, "model_dump"):
        reference = reference.model_dump(mode="json")
    return repo._require(connection, access, reference["object_type"], reference["object_id"],
        cutoff=cutoff, version=reference.get("version"), item_id=reference.get("item_id"))




def validate_membership_uniqueness(connection, access, batch):
    """Each Event receives one permanent membership; retries reuse the commit."""
    seen = set()
    for item in batch.episode_memberships:
        if item.event_id in seen:
            fail("MEMORY_MEMBERSHIP_BATCH", "同次提交每个事件只能保存一条固定归属。")
        seen.add(item.event_id)
        if connection.execute("SELECT 1 FROM event_episode WHERE event_id=? AND account_id=? AND member_id=?",
                (item.event_id, access.account_id, access.member_id)).fetchone():
            fail("MEMORY_MEMBERSHIP_ALREADY_EXISTS", "该事件已有固定事项归属，不能再次追加或重新分配事项。")


def validate_episode_append(repo, connection, access, batch, before_cutoff):
    """Run after inserting all new rows, before the shared append commits."""
    revisions = {(item.episode_id, item.version) for item in batch.episode_revisions}
    origins = {(item.episode_id, item.version) for item in batch.episode_revision_inputs}
    if revisions != origins or len(origins) != len(batch.episode_revision_inputs):
        fail('MEMORY_REVISION_INPUT_INVALID', '每份事项版本必须共同保存且仅保存一份实际生成输入关联。')
    created = {item.episode_id for item in batch.episodes}
    for item in batch.episodes:
        if not any(row.episode_id == item.episode_id for row in batch.episode_memberships):
            fail("MEMORY_EPISODE_INITIAL_MEMBERSHIP", "新事项必须同时保存起始事件归属。")
    for item in batch.episode_memberships:
        _require(repo, connection, access, ref("episode", item.episode_id),
            cutoff=None if item.episode_id in created else before_cutoff)
        _require(repo, connection, access, ref("event", item.event_id), cutoff=before_cutoff)
    for item in batch.episode_memberships:
        edges = [edge for edge in batch.event_relations if item.event_id in (edge.from_event_id, edge.to_event_id)]
        if item.episode_id in created:
            if edges:
                fail('MEMORY_EPISODE_INITIAL_RELATION', '独立事项的起始事件不创建关系。')
            continue
        if len(edges) != 1:
            fail('MEMORY_EPISODE_RELATION_REQUIRED', '加入已有事项必须在同一事务保存一条事件关系。')
        edge = edges[0]
        target = edge.to_event_id if edge.from_event_id == item.event_id else edge.from_event_id
        membership = _require(repo, connection, access, ref('episode_membership', target), cutoff=before_cutoff)
        if membership['episode_id'] != item.episode_id:
            fail('MEMORY_EPISODE_SCOPE', '连接对象必须已归入同一事项。')
        if edge.reason != item.reason:
            fail('MEMORY_EPISODE_REASON_MISMATCH', '事项归属和事件关系必须使用同一条最终判断理由。')
    seen = set()
    for item in batch.episode_revisions:
        if item.episode_id in seen:
            fail("MEMORY_EPISODE_REVISION_BATCH", "同次提交每个事项只追加一份完整版本。")
        seen.add(item.episode_id)
        previous = connection.execute("SELECT max(v.version) FROM episode_revisions v JOIN commits c USING(commit_id) "
            "WHERE v.account_id=? AND v.member_id=? AND v.episode_id=? AND c.sequence<=?",
            (access.account_id, access.member_id, item.episode_id, before_cutoff)).fetchone()[0] or 0
        if item.version != previous + 1:
            fail("MEMORY_EPISODE_REVISION_CONFLICT", "事项已有新版本，请读取后重新生成。")
        from backend.app.repositories.memory.reading.revision_input import revision_input, revision_sources
        row = repo._record(connection, access, 'episode_revision', item.episode_id, version=item.version)
        data = revision_input(repo, connection, access, row)
        cutoff = data['record_cutoff']
        membership = _require(repo, connection, access, ref('episode_membership', item.trigger_event_id), cutoff=cutoff)
        if membership['episode_id'] != item.episode_id:
            fail('MEMORY_EPISODE_REVISION_TRIGGER', '触发事件必须属于当前事项。')
        if previous:
            _require(repo, connection, access, ref('episode_revision', item.episode_id, version=previous), cutoff=cutoff)
        objects = data.get('objects', [])
        required = {('episode', item.episode_id, None), ('event', item.trigger_event_id, None),
                    ('episode_membership', item.trigger_event_id, None)}
        if previous:
            required.add(('episode_revision', item.episode_id, previous))
        from backend.app.domain.memory.references import object_reference
        actual = {(r['object_type'], r['object_id'], r.get('version')) for r in map(object_reference, objects)}
        if not required <= actual:
            fail('MEMORY_EPISODE_REVISION_INPUT', '实际模型输入缺少事项、触发事件、归属或上一版本。')
        for value in objects:
            _require(repo, connection, access, object_reference(value), cutoff=cutoff)
        from backend.app.repositories.memory.sources.evidence import read_change
        for source in revision_sources(data):
            read_change(repo, access, source, connection)


def project_episode(repo, connection, access, row, cutoff):
    result = deepcopy(row)
    if row["object_type"] == "episode":
        versions = connection.execute("SELECT v.version FROM episode_revisions v JOIN commits c USING(commit_id) "
            "WHERE v.account_id=? AND v.member_id=? AND v.episode_id=? AND c.sequence<=? ORDER BY v.version",
            (access.account_id, access.member_id, row["episode_id"], cutoff)).fetchall()
        result["revisions"] = [ref("episode_revision", row["episode_id"], version=value[0]) for value in versions
            if repo._visible(connection, access, repo._record(connection, access, "episode_revision", row["episode_id"], version=value[0], cutoff=cutoff))]
        # A hidden latest result must never silently expose an older result as current.
        result["current_revision"] = None
        if versions:
            current = repo._record(connection, access, "episode_revision", row["episode_id"], version=versions[-1][0], cutoff=cutoff)
            if repo._visible(connection, access, current):
                result["current_revision"] = deepcopy(current)
    return result
