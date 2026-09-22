"""Immutable Event edge validation and reads at a record cutoff."""
from __future__ import annotations

from collections import defaultdict

from backend.app.core.errors import SerenitaError
from backend.app.schemas.memory.values import canonical_uuid


def fail(code, message, kind="invalid_input"):
    raise SerenitaError(kind, code, message)






def validate_relation_pairs(repo, connection, access, batch):
    """A saved Event pair can never receive another edge, even with a new ID."""
    pairs = set()
    for row in batch.event_relations:
        pair = tuple(sorted((row.from_event_id, row.to_event_id)))
        if pair in pairs:
            fail("MEMORY_RELATION_PAIR_REPEATED", "同次提交不能对同一对事件重复创建边。")
        pairs.add(pair)
        existing = connection.execute(
            "SELECT 1 FROM event_relations WHERE account_id=? AND member_id=? "
            "AND min(from_event_id, to_event_id)=? AND max(from_event_id, to_event_id)=?",
            (access.account_id, access.member_id, *pair)).fetchone()
        if existing:
            fail("MEMORY_RELATION_ALREADY_EXISTS", "这对事件已有固定关系，不能重新判断、替代或停止采用。", "conflict")


def validate_relation_append(repo, connection, access, batch):
    for relation in batch.event_relations:
        for event_id in (relation.from_event_id, relation.to_event_id):
            repo._require(connection, access, "event", event_id)


def project_relation_object(repo, connection, access, row, cutoff):
    return {**row, "symmetric": row["relation_type"] == "ConflictsWith"}


def event_relations_at(repo, connection, access, record_cutoff, event_ids=None, limit=500, *, after_position=None):
    """Read all saved edges in scope; later edges never hide earlier edges."""
    if connection is None or event_ids == []:
        return {"pairs": [], "unread": [], "complete": True, "next_position": None}
    args = [access.account_id, access.member_id, record_cutoff]
    where = ""
    if event_ids:
        placeholders = ",".join("?" for _ in event_ids)
        where = f" AND (r.from_event_id IN ({placeholders}) OR r.to_event_id IN ({placeholders}))"
        args += [*event_ids, *event_ids]
    if after_position:
        where += ' AND (c.sequence<? OR (c.sequence=? AND r.relation_id>?))'
        args += [int(after_position[0]), int(after_position[0]), after_position[1]]
    rows = connection.execute(
        "SELECT r.relation_id,c.sequence FROM event_relations r JOIN commits c USING(commit_id) "
        "WHERE r.account_id=? AND r.member_id=? AND c.sequence<=?" + where +
        " ORDER BY c.sequence DESC,r.relation_id LIMIT ?", [*args, limit + 1]).fetchall()
    unread = [{"reason": "relation_pair_budget", "limit": limit}] if len(rows) > limit else []
    pairs = []
    for found in rows[:limit]:
        row = repo._record(connection, access, "event_relation", found["relation_id"], cutoff=record_cutoff)
        if not repo._visible(connection, access, row):
            if not any(item['reason']=='relation_evidence_unavailable' for item in unread):
                unread.append({"reason": "relation_evidence_unavailable"})
            continue
        relation = project_relation_object(repo, connection, access, row, record_cutoff)
        pairs.append({"relation": relation})
    next_position = [str(rows[limit-1]['sequence']), rows[limit-1]['relation_id']] if len(rows)>limit else None
    return {"pairs": pairs, "unread": unread, "complete": not unread, "next_position": next_position}


def experience_counts(events, pairs, *, complete=True, judgments=None):
    """Event records and coarse edges cannot establish distinct experience counts."""
    eligible, excluded, unresolved = [], [], []
    judgments = judgments or {}
    for event in events:
        judgment = judgments.get(event['event_id'], {})
        if judgment.get('decision') == 'eligible':
            eligible.append(event['event_id'])
        elif judgment.get('decision') == 'excluded':
            excluded.append({'event_id': event['event_id'], 'reason': judgment['reason']})
        else:
            unresolved.append({'event_id': event['event_id'], 'reason': judgment.get('reason', 'experience_eligibility_not_established'),
                **{key: judgment[key] for key in ('failure_code', 'failure_detail') if key in judgment}})
    if eligible:
        unresolved.append({'reason': 'experience_count_not_established',
            'message': '事件条数与粗粒度关系不能确定实际经历次数；需读取事件原文判断。'})
    determined_empty = complete and not eligible and not unresolved
    return {'event_count': len(events), 'eligible_event_count': len(eligible),
        'experience_count': 0 if determined_empty else None,
        'minimum': 0 if determined_empty else None, 'maximum': 0 if determined_empty else None,
        'groups': [[identity] for identity in eligible], 'excluded': excluded,
        'unresolved': unresolved, 'complete': determined_empty,
        'scope': 'specified_event_expressions_at_record_cutoff'}


class MemoryRelationRepository:
    def __init__(self, repository):
        self.repository = repository

    def read(self, actor, member, event_ids, *, record_cutoff=None, limit=100, judgments=None):
        repo = self.repository
        with repo._transaction(actor, member) as (access, connection):
            cutoff = repo._cutoff(connection, access, record_cutoff)
            events = [repo._require(connection, access, "event", canonical_uuid(event_id), cutoff=cutoff) for event_id in event_ids]
            projected = event_relations_at(repo, connection, access, cutoff, event_ids, limit)
            counts = experience_counts(events, projected["pairs"], complete=not projected["unread"], judgments=judgments)
            return {"member_id": member, "record_cutoff": cutoff, "pairs": projected["pairs"],
                    "objects": [pair["relation"] for pair in projected["pairs"]],
                    "unread": projected["unread"], "complete": projected["complete"], "experience_counts": counts}

    def event_groups(self, actor, member, cutoff, ranked_event_ids):
        repo = self.repository
        with repo._transaction(actor, member) as (access, connection):
            cutoff = repo._cutoff(connection, access, cutoff)
            by_event = defaultdict(list)
            for event_id in ranked_event_ids:
                row = repo._record(connection, access, "event", canonical_uuid(event_id), cutoff=cutoff)
                if repo._visible(connection, access, row):
                    by_event[row["event_id"]].append(event_id)
            projected = event_relations_at(repo, connection, access, cutoff, list(by_event), limit=500)
            linked_events = {identifier for pair in projected["pairs"] if pair["relation"]
                             for identifier in (pair["relation"]["from_event_id"], pair["relation"]["to_event_id"])}
            if linked_events:
                placeholders = ",".join("?" for _ in linked_events)
                rows = connection.execute(
                    "SELECT d.event_id FROM events d JOIN commits c USING(commit_id) "
                    f"WHERE d.account_id=? AND d.member_id=? AND d.event_id IN ({placeholders}) AND c.sequence<=? "
                    "ORDER BY c.sequence DESC,d.event_id LIMIT 501", (access.account_id, member, *sorted(linked_events), cutoff)).fetchall()
                if len(rows) > 500:
                    projected["unread"].append({"reason": "relation_event_budget", "limit": 500})
                    projected["complete"] = False
                for found in rows[:500]:
                    # Group membership is index metadata for the relation's
                    # authorized endpoints, not an extra fact-reading route.
                    if found["event_id"] not in by_event[found["event_id"]]:
                        by_event[found["event_id"]].append(found["event_id"])
                if linked_events.difference(by_event):
                    projected["unread"].append({"reason": "related_event_unavailable"})
                    projected["complete"] = False
            parents = {event: event for event in by_event}
            def find(value):
                while parents[value] != value:
                    parents[value] = parents[parents[value]]
                    value = parents[value]
                return value
            for pair in projected["pairs"]:
                left, right = pair["relation"]["from_event_id"], pair["relation"]["to_event_id"]
                if pair["relation"] and left in parents and right in parents:
                    parents[find(right)] = find(left)
            groups = defaultdict(list)
            for event, descriptions in by_event.items():
                groups[find(event)].extend(descriptions)
            paths = [{"relation_id": pair["relation"]["relation_id"],
                      "relation_type": pair["relation"]["relation_type"],
                      "from_event_id": pair["relation"]["from_event_id"], "to_event_id": pair["relation"]["to_event_id"]}
                     for pair in projected["pairs"] if pair["relation"]]
            return {"groups": list(groups.values()), "unread": projected["unread"], "complete": projected["complete"], "record_cutoff": cutoff,
                    "source_paths": paths}
