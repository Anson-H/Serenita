"""Event traversal, entity association and description merging from SAG-Benchmark.

Host callbacks supply verified identities; output values share Serenita IDs.
The original cache, grouping, deduplication and merge order are retained.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from zleap.sag.common import get_logger

logger = get_logger("extract.parser")
ParseContext = Any
SourceEvent = SimpleNamespace


class ResultParser:
    def __init__(self, *, resolve_entity=None, cache_key=None, create_event=None):
        self.resolve_entity = resolve_entity
        self.cache_key = cache_key
        self.create_event = create_event

    def parse_events(
        self,
        raw_items: list[dict],
        items: list,
        context: ParseContext,
    ) -> list[SourceEvent]:
        """
        解析事项（LLM结果 -> SourceEvent列表）

        Args:
            raw_items: LLM返回的事项数据列表
            items: 原始输入 items（用于引用解析）
            context: 解析上下文

        Returns:
            SourceEvent 列表（扁平化，包含所有层级）
        """
        # 构建 index -> item 映射（1-based）
        index_map = {i + 1: item for i, item in enumerate(items)}
        all_item_ids = [item.id for item in items]

        # 递归解析（扁平化存储）
        all_events = []
        for item_data in raw_items:
            events = self._parse_item_recursive(
                item_data,
                index_map,
                all_item_ids,
                context,
                parent_id=None,
                level=0,
            )
            all_events.extend(events)

        return all_events

    def _parse_item_recursive(
        self,
        item_data: dict,
        index_map: dict,
        all_item_ids: list[str],
        context: ParseContext,
        parent_id: str | None,
        level: int = 0,
    ) -> list[SourceEvent]:
        """
        递归解析单个事项（返回扁平列表）

        Args:
            item_data: 事项数据
            index_map: {序号: item} 映射
            all_item_ids: 所有 item 的 UUID 列表
            context: 解析上下文
            parent_id: 父事项ID
            level: 层级深度（0=L0顶层，1=L1，2=L2）

        Returns:
            [parent, child1, child2, ...] 扁平列表
        """
        # Host construction replaces upstream ORM fields, UUID and timestamp
        # defaults. Traversal below is copied unchanged; hierarchy stays temporary.
        event = self.create_event(item_data, index_map, all_item_ids, context)
        event_id = event.id

        result = [event]

        # 递归处理子事项
        children = item_data.get("children", [])
        if children:
            logger.info(f"事项 '{event.title}' 包含 {len(children)} 个子事项")
            for child_data in children:
                child_events = self._parse_item_recursive(
                    child_data,
                    index_map,
                    all_item_ids,
                    context,
                    parent_id=event_id,
                    level=level + 1,
                )
                result.extend(child_events)

        return result

    def process_entity_associations(
        self,
        events: list[SimpleNamespace],
        entity_types: list,
    ) -> list[SimpleNamespace]:
        """
        处理实体关联（完整流程）

        流程：
        1. 读取宿主确认的实体（使用缓存避免重复解析）
        2. 合并描述（同一实体的多个描述合并）
        3. 构造实体关联值

        Args:
            events: 事项列表（extra_data["raw_entities"]["entities"] 包含实体数据）
            entity_types: 实体类型列表

        Returns:
            处理后的事项列表（已设置 event_associations）
        """
        if not events:
            return events

        entity_cache = {}

        for event in events:
            raw_entities = event.extra_data.get("raw_entities", {}).get("entities", [])
            if not raw_entities:
                event.event_associations = []
                continue

            entity_map = {}

            # 收集宿主确认的实体
            for entity_data in raw_entities:
                cache_key = self.cache_key(entity_data)

                if cache_key in entity_cache:
                    entity = entity_cache[cache_key]
                else:
                    entity = self.resolve_entity(entity_data, entity_types)
                    if entity:
                        entity_cache[cache_key] = entity

                if entity is None:
                    continue

                # 收集描述（去重）
                if entity.id not in entity_map:
                    entity_map[entity.id] = {
                        "name": entity.name,
                        "descriptions": [],
                    }

                description = entity_data.get("description", "").strip()
                if description and description not in entity_map[entity.id]["descriptions"]:
                    entity_map[entity.id]["descriptions"].append(description)

            # 构造实体关联值
            event.event_associations = []
            for entity_id, info in entity_map.items():
                final_description = self._merge_descriptions(info["descriptions"])
                assoc = SimpleNamespace(
                    event_id=event.id,
                    entity_id=entity_id,
                    description=final_description,
                )
                event.event_associations.append(assoc)

        return events

    def _merge_descriptions(self, descriptions: list[str]) -> str:
        """合并描述列表"""
        return "、".join(descriptions) if descriptions else ""
