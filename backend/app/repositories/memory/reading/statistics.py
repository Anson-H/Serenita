"""Complete authorized memory populations; pagination never selects the sample."""
from backend.app.core.errors import SerenitaError
from backend.app.core.pagination import seek_cursor, seek_position
from collections import defaultdict, deque

from backend.app.domain.memory.statistics import first_occurrences, effective_occurrence_times
from backend.app.core.values import digest as identity
from backend.app.repositories.memory.facts.relations import event_relations_at, experience_counts
from backend.app.schemas.memory.append import MemoryQuery
from backend.app.schemas.memory.statistics import MemoryStatisticsRequest

MAX_POPULATION_EVENTS = 20000
MAX_POPULATION_RELATIONS = 20000


def fail(code, message, kind="invalid_input"):
    raise SerenitaError(kind, code, message)




def selected_relations(pairs, event_ids):
    connected = set(event_ids)
    neighbors = defaultdict(set)
    for pair in pairs:
        if pair["relation"]:
            left, right = pair["relation"]["from_event_id"], pair["relation"]["to_event_id"]
            neighbors[left].add(right)
            neighbors[right].add(left)
    queue = deque(connected)
    while queue:
        unseen = neighbors[queue.popleft()] - connected
        connected.update(unseen)
        queue.extend(unseen)
    return [pair for pair in pairs if connected.intersection({pair["relation"]["from_event_id"], pair["relation"]["to_event_id"]})], connected


class MemoryStatisticsRepository:
    def __init__(self, repository):
        self.repository = repository

    def read(self, actor, member, request, *, judgments=None, include_population=False, population=None):
        request = request if isinstance(request, MemoryStatisticsRequest) else MemoryStatisticsRequest.model_validate(request)
        repo = self.repository
        scope = {"actor": actor, "member": member, "query": request.model_dump(mode="json", exclude={"cursor", "limit"})}
        try:
            position = seek_position(request.cursor, scope=scope, size=2)
        except ValueError:
            fail("MEMORY_STATISTICS_CURSOR_INVALID", "统计游标与当前成员或筛选范围不一致。")
        with repo._transaction(actor, member) as (access, connection):
            requested_cutoff = request.record_cutoff
            if position:
                if not position[0].isdigit():
                    fail("MEMORY_STATISTICS_CURSOR_INVALID", "统计游标无效。")
                if requested_cutoff is not None and requested_cutoff != int(position[0]):
                    fail("MEMORY_STATISTICS_CURSOR_INVALID", "统计游标的记录截点不一致。")
                requested_cutoff = int(position[0])
            cutoff = repo._cutoff(connection, access, population['record_cutoff'] if population is not None else requested_cutoff)
            if population is not None:
                if population['scope'] != scope or population['record_cutoff'] != cutoff:
                    fail('MEMORY_STATISTICS_CURSOR_INVALID', '统计输入与当前成员或记录截点不同。')
                all_events, events, pairs, graph, time_gaps = (population[key] for key in ('all_events', '_experience_events', 'pairs', 'graph', 'time_gaps'))
                for row in [*all_events, *(pair['relation'] for pair in graph['pairs'] if pair['relation'])]:
                    if not repo._visible(connection, access, row):
                        fail('MEMORY_STATISTICS_SCOPE_CHANGED', '统计期间依据权限发生变化，请重新查询。', 'forbidden')
                for kind, identities in (('event', request.event_ids), ('entity', request.entity_ids)):
                    for target_id in identities:
                        repo._require(connection, access, kind, target_id, cutoff=cutoff)
            else:
                for event_id in request.event_ids:
                    repo._require(connection, access, "event", event_id, cutoff=cutoff)
                entity_events = set()
                for entity_id in request.entity_ids:
                    repo._require(connection, access, "entity", entity_id, cutoff=cutoff)
                    entity_events.update(row[0] for row in connection.execute(
                        "SELECT x.event_id FROM event_entities x JOIN commits c USING(commit_id) "
                        "WHERE x.account_id=? AND x.member_id=? AND x.entity_id=? AND c.sequence<=?",
                        (access.account_id, member, entity_id, cutoff)))
                graph = event_relations_at(repo, connection, access, cutoff, limit=MAX_POPULATION_RELATIONS)
                scope_ids = selected_relations(graph["pairs"], request.event_ids)[1] if request.event_ids else set()
                narrowed = " AND e.event_id IN (" + ",".join("?" for _ in scope_ids) + ")" if scope_ids else ""
                rows = [] if connection is None else connection.execute(
                    "SELECT e.*,c.sequence AS record_sequence, c.submitted_at FROM events e JOIN commits c USING(commit_id) WHERE e.account_id=? AND e.member_id=? AND c.sequence<=? "
                    + narrowed + " ORDER BY e.event_id LIMIT ?", (access.account_id, member, cutoff, *sorted(scope_ids), MAX_POPULATION_EVENTS + 1)).fetchall()
                if len(rows) > MAX_POPULATION_EVENTS:
                    fail("MEMORY_STATISTICS_POPULATION_BUDGET", "完整记忆母体超过本次已支持规模，未返回部分统计。", "resource_limit")
                decoded = [repo._record_value(found, "event") for found in rows]
                all_events = []
                for event in decoded:
                    if repo._visible(connection, access, event):
                        all_events.append(event)
                query = MemoryQuery.model_validate({key: request.model_dump(mode="json")[key]
                    for key in ("target_time", "source_categories")})
                applicable = graph["pairs"]
                effective, time_gaps = effective_occurrence_times(all_events, applicable)
                events = [event for event in effective if
                    (not request.event_ids or event["event_id"] in request.event_ids) and
                    (not request.entity_ids or event["event_id"] in entity_events) and
                    (not request.query or request.query.casefold() in event["content"].casefold()) and
                    repo._matches(connection, access, event, query)]
                pairs, _ = selected_relations(applicable, [event["event_id"] for event in events])
            if include_population:
                return {'scope': scope, 'record_cutoff': cutoff, 'all_events': all_events,
                        '_experience_events': events, 'pairs': pairs, 'graph': graph, 'time_gaps': time_gaps}
            experience = experience_counts(events, pairs, complete=graph['complete'], judgments=judgments)
            start = position[1] if position else ""
            remaining = [event for event in events if event["event_id"] > start]
            page = remaining[:request.limit]
            next_cursor = seek_cursor(scope, [str(cutoff), page[-1]["event_id"]]) if len(remaining) > request.limit else None
            page_ids = {event["event_id"] for event in page}
            eligible_ids = {event_id for group in experience["groups"] for event_id in group}
            group_page = [{"group_id": identity(group), "event_ids": [event_id for event_id in group if event_id in page_ids],
                           "population_event_count": len(group)} for group in experience.pop("groups") if page_ids.intersection(group)]
            experience["groups"] = group_page
            experience["excluded_count"] = len(experience["excluded"])
            experience["excluded"] = [row for row in experience["excluded"] if row["event_id"] in page_ids]
            gaps = [*graph["unread"], *experience["unresolved"],
                *[gap for gap in time_gaps if gap["event_id"] in {event["event_id"] for event in events}]]
            first = first_occurrences([event for event in events if event["event_id"] in eligible_ids])
            if experience["unresolved"]:
                first.update(complete=False, definite=False, empty=None, reason="experience_population_unresolved")
            first["population"] = "eligible_actual_experience_expressions"
            first["possible_event_count"] = len(first["event_ids"])
            first["event_ids"] = [event_id for event_id in first["event_ids"] if event_id in page_ids]
            first["unknown_time_count"] = len(first["unknown_time_event_ids"])
            first["unknown_time_event_ids"] = [event_id for event_id in first["unknown_time_event_ids"] if event_id in page_ids]
            original_by_id = {event["event_id"]: event for event in all_events}
            return {"member_id": member, "record_cutoff": cutoff, "objects": [repo._project(connection, access, original_by_id[event["event_id"]], cutoff) for event in page], "event_count": len(events),
                "effective_occurrence_times": [{"event_id": event["event_id"], "occurrence_time": event["occurrence_time"], "basis": event["occurrence_time_basis"]} for event in page if event.get("occurrence_time_basis")],
                "experience": experience, "first_occurrence": first,
                "coverage": {"population": "authorized_memory_event_expressions", "complete_population": True,
                    "matching_events": len(events), "returned_events": len(page), "source_categories": request.source_categories,
                    "filters": request.model_dump(mode="json", exclude={"cursor", "limit"}), "time_membership": "possible_overlap",
                    "unknown_occurrence_time_count": sum(not (event["occurrence_time"] or {}).get("start") for event in events),
                    "relation_population_complete": graph["complete"],
                    "business_population_complete": False},
                "next_cursor": next_cursor, "gaps": gaps, "unread": ([{"reason": "statistics_detail_pages_remaining"}] if next_cursor else []),
                "read_query": request.model_dump(mode="json", exclude={"cursor"})}
