from backend.app.repositories.report_transaction import ReportTransaction
from backend.app.core.report_errors import (
    LabDictionaryRevisionConflictError,
    LabDictionaryNameConflictError,
    LabDictionaryPrimaryCategoryError,
)

import hashlib
import json
from copy import deepcopy
from typing import Any, Iterable


from backend.app.repositories.report_values import (
    _json_loads,
    _lab_name_key,
    _new_lab_item_id,
)


class LabCatalog:
    """Catalogue capabilities and their changes to facts share an explicit transaction."""

    def __init__(self, open_transaction, facts):
        self.open_transaction = open_transaction
        self.facts = facts

    def dictionary_revision(self, transaction: ReportTransaction) -> str:
        connection = transaction.connection
        items = [
            {
                "item_id": row["item_id"],
                "item_name_zh": row["item_name_zh"],
                "aliases": _json_loads(row["aliases"], []),
                "description": row["description"],
            }
            for row in connection.execute(
                "SELECT * FROM lab_items ORDER BY item_name_zh, item_id"
            ).fetchall()
        ]
        categories = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM lab_categories ORDER BY category_name"
            ).fetchall()
        ]
        relations = [
            dict(row)
            for row in connection.execute(
                """
                SELECT item_id, category_name, is_primary
                FROM lab_item_category_links
                ORDER BY item_id, is_primary DESC, category_name
                """
            ).fetchall()
        ]
        encoded = json.dumps(
            {"items": items, "categories": categories, "relations": relations},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def dictionary_data(
        self, transaction: ReportTransaction, member_id: str | None
    ) -> dict[str, Any]:
        connection = transaction.connection
        category_rows = connection.execute(
            "SELECT * FROM lab_categories ORDER BY category_name"
        ).fetchall()
        categories: list[dict[str, Any]] = []
        for row in category_rows:
            category_name = str(row["category_name"])
            usage = self.facts.category_usage(transaction, member_id, category_name)
            item_count = connection.execute(
                "SELECT COUNT(*) AS total FROM lab_item_category_links WHERE category_name = ?",
                (category_name,),
            ).fetchone()["total"]
            primary_item_count = connection.execute(
                """
                SELECT COUNT(*) AS total FROM lab_item_category_links
                WHERE category_name = ? AND is_primary = 1
                """,
                (category_name,),
            ).fetchone()["total"]
            categories.append(
                {
                    **dict(row),
                    "item_count": int(item_count),
                    "primary_item_count": int(primary_item_count),
                    "related_item_count": int(item_count) - int(primary_item_count),
                    "result_count": int(usage["result_count"]),
                    "report_count": int(usage["report_count"]),
                }
            )

        item_rows = connection.execute(
            "SELECT * FROM lab_items ORDER BY item_name_zh, item_id"
        ).fetchall()
        items: list[dict[str, Any]] = []
        for row in item_rows:
            item_id = str(row["item_id"])
            usages = self.facts.item_usage(transaction, member_id, item_id)
            usage_by_category = [dict(usage) for usage in usages]
            primary_category = next(
                (
                    str(usage["category_name"])
                    for usage in usages
                    if usage["is_primary"]
                ),
                "",
            )
            related_categories = [
                str(usage["category_name"])
                for usage in usages
                if not usage["is_primary"]
            ]
            items.append(
                {
                    **dict(row),
                    "aliases": _json_loads(row["aliases"], []),
                    "primary_category_name": primary_category,
                    "related_category_names": related_categories,
                    "usage_by_category": usage_by_category,
                    "result_count": sum(int(usage["result_count"]) for usage in usages),
                    "report_count": len(
                        self.facts.report_ids_for_item(transaction, item_id, member_id)
                    ),
                }
            )

        relations = [
            dict(row)
            for row in connection.execute(
                """
                SELECT item_id, category_name, is_primary
                FROM lab_item_category_links
                ORDER BY item_id, is_primary DESC, category_name
                """
            ).fetchall()
        ]
        return {
            "dictionary_revision": self.dictionary_revision(transaction),
            "summary": {
                "item_count": len(items),
                "category_count": len(categories),
                "relation_count": len(relations),
            },
            "items": items,
            "categories": categories,
            "relations": relations,
        }

    def lab_dictionary(self, member_id: str | None = None) -> dict[str, Any]:
        with self.open_transaction() as transaction:
            return self.dictionary_data(transaction, member_id)

    def require_dictionary_revision(
        self, transaction: ReportTransaction, expected_dictionary_revision: str
    ) -> None:
        if (
            not expected_dictionary_revision
            or self.dictionary_revision(transaction) != expected_dictionary_revision
        ):
            raise LabDictionaryRevisionConflictError(
                "检验指标分类目录已发生变化，请刷新后重试。"
            )

    @staticmethod
    def normalized_dictionary_aliases(
        item_name_zh: str, aliases: Iterable[str]
    ) -> list[str]:
        canonical_key = _lab_name_key(item_name_zh)
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in aliases:
            alias = str(raw or "").strip()
            key = _lab_name_key(alias)
            if not alias or not key or key == canonical_key or key in seen:
                continue
            seen.add(key)
            normalized.append(alias)
        return normalized

    def assert_dictionary_names_available(
        self,
        transaction: ReportTransaction,
        *,
        item_name_zh: str,
        aliases: list[str],
        primary_category_name: str,
        exclude_item_id: str | None = None,
        exclude_item_ids: Iterable[str] = (),
    ) -> None:
        connection = transaction.connection
        requested = {
            _lab_name_key(item_name_zh),
            *(_lab_name_key(alias) for alias in aliases),
        }
        excluded = {*exclude_item_ids, exclude_item_id}
        for row in connection.execute(
            """
            SELECT i.item_id, i.item_name_zh, i.aliases
            FROM lab_items i
            JOIN lab_item_category_links c
              ON c.item_id = i.item_id AND c.is_primary = 1
            WHERE c.category_name = ?
            """,
            (primary_category_name,),
        ).fetchall():
            if row["item_id"] in excluded:
                continue
            existing = {
                _lab_name_key(row["item_name_zh"]),
                *(_lab_name_key(alias) for alias in _json_loads(row["aliases"], [])),
            }
            if requested & existing:
                raise LabDictionaryNameConflictError(
                    f"指标名称或别名与“{row['item_name_zh']}”在主分类“{primary_category_name}”中重复。",
                    conflicting_item_id=str(row["item_id"]),
                    conflicting_item_name_zh=str(row["item_name_zh"]),
                )

    def require_categories(
        self, transaction: ReportTransaction, category_names: Iterable[str]
    ) -> list[str]:
        connection = transaction.connection
        requested = list(
            dict.fromkeys(
                str(value).strip() for value in category_names if str(value).strip()
            )
        )
        if not requested:
            return []
        placeholders = ",".join("?" for _ in requested)
        rows = connection.execute(
            f"SELECT category_name FROM lab_categories WHERE category_name IN ({placeholders})",
            requested,
        ).fetchall()
        found = {str(row["category_name"]) for row in rows}
        missing = [value for value in requested if value not in found]
        if missing:
            raise LookupError(f"检验分类不存在：{', '.join(missing)}")
        return requested

    def require_item_categories(
        self,
        transaction: ReportTransaction,
        primary_category_name: str,
        related_category_names: Iterable[str],
    ) -> tuple[str, list[str]]:
        primary = str(primary_category_name or "").strip()
        if not primary:
            raise ValueError("每个检验指标必须设置一个主分类。")
        related = [
            value
            for value in dict.fromkeys(
                str(value).strip()
                for value in related_category_names
                if str(value).strip()
            )
            if value != primary
        ]
        self.require_categories(transaction, [primary, *related])
        return primary, related

    @staticmethod
    def public_dictionary_impact(impact: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in impact.items() if not key.startswith("_")}

    def dictionary_mutation_result(
        self,
        transaction: ReportTransaction,
        *,
        effects: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "dictionary": self.dictionary_data(transaction, None),
            "effects": effects or {},
        }

    def create_lab_item(
        self,
        *,
        item_name_zh: str,
        aliases: Iterable[str],
        description: str | None,
        primary_category_name: str,
        related_category_names: Iterable[str],
        expected_dictionary_revision: str,
    ) -> dict[str, Any]:
        with self.open_transaction(write=True) as transaction:
            connection = transaction.connection
            self.require_dictionary_revision(transaction, expected_dictionary_revision)
            primary_category, related_categories = self.require_item_categories(
                transaction, primary_category_name, related_category_names
            )
            normalized_aliases = self.normalized_dictionary_aliases(
                item_name_zh, aliases
            )
            self.assert_dictionary_names_available(
                transaction,
                item_name_zh=item_name_zh,
                aliases=normalized_aliases,
                primary_category_name=primary_category,
            )
            item_id = _new_lab_item_id()
            connection.execute(
                """
                INSERT INTO lab_items(item_id, item_name_zh, aliases, description)
                VALUES (?, ?, ?, ?)
                """,
                (
                    item_id,
                    item_name_zh,
                    json.dumps(normalized_aliases, ensure_ascii=False),
                    description,
                ),
            )
            for category, is_primary in (
                (primary_category, 1),
                *((category, 0) for category in related_categories),
            ):
                connection.execute(
                    """
                    INSERT INTO lab_item_category_links(item_id, category_name, is_primary)
                    VALUES (?, ?, ?)
                    """,
                    (item_id, category, is_primary),
                )
            return self.dictionary_mutation_result(
                transaction, effects={"created_item_id": item_id}
            )

    def update_lab_item(
        self,
        item_id: str,
        *,
        item_name_zh: str,
        aliases: Iterable[str],
        description: str | None,
        primary_category_name: str,
        related_category_names: Iterable[str],
        expected_dictionary_revision: str,
    ) -> dict[str, Any]:
        with self.open_transaction(write=True) as transaction:
            connection = transaction.connection
            self.require_dictionary_revision(transaction, expected_dictionary_revision)
            current = connection.execute(
                "SELECT * FROM lab_items WHERE item_id = ?", (item_id,)
            ).fetchone()
            if current is None:
                raise LookupError("检验指标不存在。")
            primary_category, related_categories = self.require_item_categories(
                transaction, primary_category_name, related_category_names
            )
            normalized_aliases = self.normalized_dictionary_aliases(
                item_name_zh, aliases
            )
            self.assert_dictionary_names_available(
                transaction,
                item_name_zh=item_name_zh,
                aliases=normalized_aliases,
                primary_category_name=primary_category,
                exclude_item_id=item_id,
            )
            all_item_reports = self.facts.report_ids_for_item(transaction, item_id)
            connection.execute(
                """
                UPDATE lab_items
                SET item_name_zh = ?, aliases = ?, description = ?
                WHERE item_id = ?
                """,
                (
                    item_name_zh,
                    json.dumps(normalized_aliases, ensure_ascii=False),
                    description,
                    item_id,
                ),
            )
            self.facts.set_lab_item_name(transaction, item_id, item_name_zh)
            current_relations = {
                str(row["category_name"]): bool(row["is_primary"])
                for row in connection.execute(
                    """
                    SELECT category_name, is_primary FROM lab_item_category_links
                    WHERE item_id = ?
                    """,
                    (item_id,),
                ).fetchall()
            }
            current_primary = next(
                (
                    category
                    for category, is_primary in current_relations.items()
                    if is_primary
                ),
                None,
            )
            requested_categories = {primary_category, *related_categories}
            if primary_category not in current_relations:
                connection.execute(
                    """
                    INSERT INTO lab_item_category_links(item_id, category_name, is_primary)
                    VALUES (?, ?, 0)
                    """,
                    (item_id, primary_category),
                )
            connection.execute(
                "UPDATE lab_item_category_links SET is_primary = 0 WHERE item_id = ? AND is_primary = 1",
                (item_id,),
            )
            connection.execute(
                """
                UPDATE lab_item_category_links SET is_primary = 1
                WHERE item_id = ? AND category_name = ?
                """,
                (item_id, primary_category),
            )
            for category in (
                requested_categories - set(current_relations) - {primary_category}
            ):
                connection.execute(
                    """
                    INSERT INTO lab_item_category_links(item_id, category_name, is_primary)
                    VALUES (?, ?, 0)
                    """,
                    (item_id, category),
                )
            reclassification = (
                self.facts.reclassify_lab_item_results(
                    transaction,
                    item_id=item_id,
                    primary_category_name=primary_category,
                )
                if current_primary != primary_category
                else {
                    "affected_report_ids": set(),
                    "reclassified_result_count": 0,
                    "moved_to_existing_report_count": 0,
                    "created_report_count": 0,
                }
            )
            for category in set(current_relations) - requested_categories:
                connection.execute(
                    "DELETE FROM lab_item_category_links WHERE item_id = ? AND category_name = ?",
                    (item_id, category),
                )
            affected: set[str] = set()
            if str(current["item_name_zh"]) != item_name_zh:
                affected.update(all_item_reports)
            affected.update(reclassification["affected_report_ids"])
            effects = self.facts.reconcile_dictionary_report_changes(
                transaction, affected
            )
            effects.update(
                {
                    key: value
                    for key, value in reclassification.items()
                    if key != "affected_report_ids"
                }
            )
            return self.dictionary_mutation_result(transaction, effects=effects)

    def merge_lab_items(
        self,
        source_item_id: str,
        *,
        target_item_id: str,
        expected_dictionary_revision: str,
    ) -> dict[str, Any]:
        """Merge one canonical item into another without overwriting evidence."""

        with self.open_transaction(write=True) as transaction:
            connection = transaction.connection
            self.require_dictionary_revision(transaction, expected_dictionary_revision)
            if source_item_id == target_item_id:
                raise ValueError("不能将指标合并到自身。")
            source = connection.execute(
                "SELECT * FROM lab_items WHERE item_id = ?", (source_item_id,)
            ).fetchone()
            target = connection.execute(
                "SELECT * FROM lab_items WHERE item_id = ?", (target_item_id,)
            ).fetchone()
            if source is None or target is None:
                raise LookupError("待合并的检验指标不存在。")

            target_relations = {
                str(row["category_name"]): bool(row["is_primary"])
                for row in connection.execute(
                    """
                    SELECT category_name, is_primary FROM lab_item_category_links
                    WHERE item_id = ?
                    """,
                    (target_item_id,),
                ).fetchall()
            }
            target_primary = next(
                (
                    category_name
                    for category_name, is_primary in target_relations.items()
                    if is_primary
                ),
                None,
            )
            if target_primary is None:
                raise RuntimeError("目标检验指标缺少主分类。")
            source_relations = {
                str(row["category_name"])
                for row in connection.execute(
                    """
                    SELECT category_name FROM lab_item_category_links
                    WHERE item_id = ?
                    """,
                    (source_item_id,),
                ).fetchall()
            }
            source_report_ids, moved_result_count, deduplicated_result_count = (
                self.facts.merge_lab_item_results(
                    transaction,
                    source_item_id,
                    target_item_id,
                    str(target["item_name_zh"]),
                    target_primary,
                )
            )

            merged_aliases = self.normalized_dictionary_aliases(
                str(target["item_name_zh"]),
                [
                    *_json_loads(target["aliases"], []),
                    str(source["item_name_zh"]),
                    *_json_loads(source["aliases"], []),
                ],
            )
            self.assert_dictionary_names_available(
                transaction,
                item_name_zh=str(target["item_name_zh"]),
                aliases=merged_aliases,
                primary_category_name=target_primary,
                exclude_item_ids=(source_item_id, target_item_id),
            )
            connection.execute(
                "UPDATE lab_items SET aliases = ? WHERE item_id = ?",
                (json.dumps(merged_aliases, ensure_ascii=False), target_item_id),
            )
            for category_name in source_relations - {target_primary}:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO lab_item_category_links(
                        item_id, category_name, is_primary
                    ) VALUES (?, ?, 0)
                    """,
                    (target_item_id, category_name),
                )
            connection.execute(
                "DELETE FROM lab_items WHERE item_id = ?", (source_item_id,)
            )

            reclassification = self.facts.reclassify_lab_item_results(
                transaction,
                item_id=target_item_id,
                primary_category_name=target_primary,
            )
            affected_report_ids = {
                *source_report_ids,
                *reclassification["affected_report_ids"],
            }
            effects = self.facts.reconcile_dictionary_report_changes(
                transaction, affected_report_ids
            )
            effects.update(
                {
                    key: value
                    for key, value in reclassification.items()
                    if key != "affected_report_ids"
                }
            )
            effects.update(
                {
                    "affected_report_count": len(affected_report_ids),
                    "merged_result_count": len(source_report_ids),
                    "moved_result_count": moved_result_count,
                    "deduplicated_result_count": deduplicated_result_count,
                    "merged_source_item_id": source_item_id,
                    "merged_target_item_id": target_item_id,
                }
            )
            return self.dictionary_mutation_result(transaction, effects=effects)

    def delete_lab_item(
        self,
        item_id: str,
        *,
        expected_dictionary_revision: str,
    ) -> dict[str, Any]:
        with self.open_transaction(write=True) as transaction:
            connection = transaction.connection
            self.require_dictionary_revision(transaction, expected_dictionary_revision)
            if (
                connection.execute(
                    "SELECT 1 FROM lab_items WHERE item_id = ?", (item_id,)
                ).fetchone()
                is None
            ):
                raise LookupError("检验指标不存在。")
            impact = self.facts.dictionary_impact(
                transaction, operation="delete_item", item_id=item_id
            )
            connection.execute("DELETE FROM lab_items WHERE item_id = ?", (item_id,))
            effects = self.facts.reconcile_dictionary_report_changes(
                transaction, impact["_affected_report_ids"]
            )
            effects.update(self.public_dictionary_impact(impact))
            return self.dictionary_mutation_result(transaction, effects=effects)

    def create_lab_category(
        self,
        *,
        category_name: str,
        description: str | None,
        expected_dictionary_revision: str,
    ) -> dict[str, Any]:
        with self.open_transaction(write=True) as transaction:
            connection = transaction.connection
            self.require_dictionary_revision(transaction, expected_dictionary_revision)
            if (
                connection.execute(
                    "SELECT 1 FROM lab_categories WHERE category_name = ?",
                    (category_name,),
                ).fetchone()
                is not None
            ):
                raise LabDictionaryNameConflictError("检验分类名称已存在。")
            connection.execute(
                """
                INSERT INTO lab_categories(category_name, description)
                VALUES (?, ?)
                """,
                (category_name, description),
            )
            return self.dictionary_mutation_result(
                transaction, effects={"created_category_name": category_name}
            )

    def update_lab_category(
        self,
        current_category_name: str,
        *,
        category_name: str,
        description: str | None,
        expected_dictionary_revision: str,
    ) -> dict[str, Any]:
        with self.open_transaction(write=True) as transaction:
            connection = transaction.connection
            self.require_dictionary_revision(transaction, expected_dictionary_revision)
            current = connection.execute(
                "SELECT * FROM lab_categories WHERE category_name = ?",
                (current_category_name,),
            ).fetchone()
            if current is None:
                raise LookupError("检验分类不存在。")
            if (
                category_name != current_category_name
                and connection.execute(
                    "SELECT 1 FROM lab_categories WHERE category_name = ?",
                    (category_name,),
                ).fetchone()
                is not None
            ):
                raise LabDictionaryNameConflictError("检验分类名称已存在。")
            affected_reports = self.facts.report_ids_for_category(
                transaction, current_category_name
            )
            connection.execute(
                """
                UPDATE lab_categories
                SET category_name = ?, description = ?
                WHERE category_name = ?
                """,
                (category_name, description, current_category_name),
            )
            effects: dict[str, Any] = {}
            if category_name != current_category_name:
                self.facts.rename_report_titles(
                    transaction, affected_reports, category_name
                )
                effects = self.facts.reconcile_dictionary_report_changes(
                    transaction, affected_reports
                )
            return self.dictionary_mutation_result(transaction, effects=effects)

    def delete_lab_category(
        self,
        category_name: str,
        *,
        expected_dictionary_revision: str,
    ) -> dict[str, Any]:
        with self.open_transaction(write=True) as transaction:
            connection = transaction.connection
            self.require_dictionary_revision(transaction, expected_dictionary_revision)
            if (
                connection.execute(
                    "SELECT 1 FROM lab_categories WHERE category_name = ?",
                    (category_name,),
                ).fetchone()
                is None
            ):
                raise LookupError("检验分类不存在。")
            impact = self.facts.dictionary_impact(
                transaction,
                operation="delete_category",
                category_name=category_name,
            )
            if impact["primary_item_count"]:
                raise LabDictionaryPrimaryCategoryError(
                    f"该分类仍是 {impact['primary_item_count']} 个指标的主分类，"
                    "请先为这些指标更换主分类。"
                )
            connection.execute(
                "DELETE FROM lab_categories WHERE category_name = ?", (category_name,)
            )
            effects = self.public_dictionary_impact(impact)
            return self.dictionary_mutation_result(transaction, effects=effects)

    def normalize_lab_items(
        self, transaction: ReportTransaction, items: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        connection = transaction.connection
        safe: list[dict[str, Any]] = []
        alias_changes: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        for raw_item in items:
            item = deepcopy(raw_item)
            item_id = str(item.get("item_id") or "").strip()
            name = str(item.get("item_name_zh") or "").strip()
            category_name = str(item.get("category_name") or "").strip()
            if not item_id or not _lab_name_key(name) or not category_name:
                issues.append(
                    {
                        "kind": "invalid_lab_dictionary_entry",
                        "item_id": item_id,
                        "item_name_zh": name,
                        "category_name": category_name,
                    }
                )
                continue
            aliases = self.normalized_dictionary_aliases(name, item.get("aliases", []))
            row = connection.execute(
                "SELECT * FROM lab_items WHERE item_id = ?", (item_id,)
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO lab_categories(category_name, description)
                    VALUES (?, NULL)
                    """,
                    (category_name,),
                )
                try:
                    self.assert_dictionary_names_available(
                        transaction,
                        item_name_zh=name,
                        aliases=aliases,
                        primary_category_name=category_name,
                    )
                except LabDictionaryNameConflictError as exc:
                    issues.append(
                        {
                            "kind": "lab_dictionary_collision",
                            "item_id": item_id,
                            "item_name_zh": name,
                            **exc.detail,
                        }
                    )
                    continue
                connection.execute(
                    """
                    INSERT INTO lab_items(item_id, item_name_zh, aliases, description)
                    VALUES (?, ?, ?, NULL)
                    """,
                    (item_id, name, json.dumps(aliases, ensure_ascii=False)),
                )
                canonical_name = name
                connection.execute(
                    """
                    INSERT INTO lab_item_category_links(item_id, category_name, is_primary)
                    VALUES (?, ?, 1)
                    """,
                    (item_id, category_name),
                )
                canonical_category_name = category_name
            else:
                canonical_name = str(row["item_name_zh"])
                primary_row = connection.execute(
                    """
                    SELECT category_name FROM lab_item_category_links
                    WHERE item_id = ? AND is_primary = 1
                    """,
                    (item_id,),
                ).fetchone()
                if primary_row is None:
                    raise RuntimeError("检验指标缺少主分类。")
                canonical_category_name = str(primary_row["category_name"])
                if category_name != canonical_category_name:
                    issues.append(
                        {
                            "kind": "lab_dictionary_category_mismatch",
                            "item_id": item_id,
                            "item_name_zh": canonical_name,
                            "expected_category_name": canonical_category_name,
                            "provided_category_name": category_name,
                        }
                    )
                    continue
                stored_aliases = [
                    str(value).strip()
                    for value in _json_loads(row["aliases"], [])
                    if str(value).strip()
                ]
                requested_aliases = [
                    str(value).strip()
                    for value in [name, *(item.get("aliases", []) or [])]
                    if str(value).strip()
                    and _lab_name_key(value) != _lab_name_key(canonical_name)
                ]
                merged_aliases = list(
                    dict.fromkeys([*stored_aliases, *requested_aliases])
                )
                try:
                    self.assert_dictionary_names_available(
                        transaction,
                        item_name_zh=canonical_name,
                        aliases=self.normalized_dictionary_aliases(
                            canonical_name, merged_aliases
                        ),
                        primary_category_name=canonical_category_name,
                        exclude_item_id=item_id,
                    )
                except LabDictionaryNameConflictError:
                    issues.append(
                        {
                            "kind": "lab_dictionary_collision",
                            "item_id": item_id,
                            "item_name_zh": canonical_name,
                            "provided_item_name_zh": name,
                        }
                    )
                    continue
                added = [
                    value for value in merged_aliases if value not in stored_aliases
                ]
                if added:
                    connection.execute(
                        "UPDATE lab_items SET aliases = ? WHERE item_id = ?",
                        (json.dumps(merged_aliases, ensure_ascii=False), item_id),
                    )
                    alias_changes.append(
                        {
                            "item_id": item_id,
                            "item_name_zh": canonical_name,
                            "aliases": added,
                        }
                    )
            safe.append(
                {
                    key: value
                    for key, value in {
                        **item,
                        "item_id": item_id,
                        "item_name_zh": canonical_name,
                        "category_name": canonical_category_name,
                    }.items()
                    if not str(key).startswith("_")
                }
            )
        return safe, alias_changes, issues
