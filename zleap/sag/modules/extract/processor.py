"""SAG-Benchmark extraction adapted to host models and medical template.

Request assembly, model invocation and native validation are adapted
from the fixed paper repository. Requests contain only instructions and actual inputs. Persistence remains in Serenita.
"""
import copy
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from zleap.sag.core.ai.models import LLMMessage, LLMRole
from zleap.sag.exceptions import ExtractError
from zleap.sag.common import get_logger

logger = get_logger("extract.processor")


class EventProcessor:
    def __init__(self, llm_client, prompt_manager, config, *, entity_types):
        self.llm_client = llm_client
        self.prompt_manager = prompt_manager
        self.config = config
        self.entity_types = entity_types

    async def process(
        self,
        items: list,
        metadata: dict,
        source_type: str,
    ) -> dict:
        """
        处理提取（调用LLM）

        流程：
        2. 构建系统提示词
        3. 构建输入 JSON
        4. 调用 LLM
        5. 校验输出

        Args:
            items: ArticleSection 或 ChatMessage 列表
            metadata: 元数据 {document_title, chunk_title, previous_context}
            source_type: "ARTICLE" 或 "CHAT"

        Returns:
            LLM返回的原始结果Dict
        """
        if not items:
            logger.info("items 为空，跳过提取")
            return {"type": "response", "data": {"items": [], "meta": {}}}

        try:
            # 2. 构建系统提示词
            system_prompt = self._build_system_prompt()
            logger.info(f"系统提示词长度: {len(system_prompt)} 字符")

            # 3. 构建输入 JSON
            user_input = self._build_input(items, metadata, source_type)
            logger.info(
                f"输入: {len(items)} items, type={source_type}"
            )

            # 4. 构建消息（system + 实际 user）
            messages = self._build_messages(system_prompt, user_input)

            # 5. 调用 LLM
            schema = self._build_schema()
            result = await self._call_llm_with_retry(messages, schema)

            # 6. 校验输出
            self._validate_output(result)

            # 记录结果
            self._log_extract_result(result)

            return result

        except Exception as e:
            logger.error(f"提取失败: {e}", exc_info=True)
            raise ExtractError(f"提取失败: {e}") from e

    def _get_extract_prompt_config(self) -> tuple[str, dict]:
        """Read the host's single medical extraction template."""
        return "extract", self.prompt_manager.get_template_config("extract", test_mode=self.config.test_mode)

    def _build_system_prompt(self) -> str:
        """构建系统提示词（从 YAML 读取，不含示例）"""
        template_name, config = self._get_extract_prompt_config()
        template = config.get("template", "")

        tz = ZoneInfo(self.config.timezone)
        time_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
        strict_requirements_template = config.get("strict_requirements", "")

        custom_background = self._format_custom(self.config.custom_background)

        # 如果启用严格过滤，从 YAML 读取规则并追加
        custom_requirements = self.config.custom_requirements
        if self.config.enable_strict_filtering and strict_requirements_template:
            formatted_strict = self._format_custom(strict_requirements_template)
            if custom_requirements:
                custom_requirements = custom_requirements + "\n" + formatted_strict
            else:
                custom_requirements = formatted_strict

        custom_requirements = self._format_custom(custom_requirements)

        try:
            return template.format(
                time=time_str,
                timezone=self.config.timezone,
                custom_background=custom_background,
                custom_requirements=custom_requirements,
            )
        except KeyError:
            return self.prompt_manager.render(
                template_name,
                time=time_str,
                timezone=self.config.timezone,
                custom_background=custom_background,
                custom_requirements=custom_requirements,
            )

    def _format_custom(self, text: str) -> str:
        """格式化自定义文本"""
        if not text:
            return ""
        lines = text.strip().split("\n")
        return "\n" + "\n".join(f"    {line}" for line in lines)

    def _build_messages(self, system_prompt: str, user_input: dict) -> list[LLMMessage]:
        """构建系统提示词与当前实际输入。"""
        return [
            LLMMessage(role=LLMRole.SYSTEM, content=system_prompt),
            LLMMessage(role=LLMRole.USER, content=json.dumps(user_input, ensure_ascii=False)),
        ]

    def _build_input(
        self,
        items: list,
        metadata: dict,
        source_type: str,
    ) -> dict:
        """
        构建输入 JSON（新结构：data 只含 items，meta 含所有元数据）

        结构：
        - type: "request"
        - data: { items: [...] }
        - meta: { source_type, source_title, source_summary, previous_context, entity_types }
        """
        is_article = source_type == "ARTICLE"

        # 构建 items 数组
        items_data = []
        for i, item in enumerate(items, 1):
            item_data = {"id": i, "content": item.content}
            items_data.append(item_data)

        # 构建 entity_types 对象数组（包含 type 和 description）
        entity_types_data = []
        for et in self.entity_types:
            entity_types_data.append(
                {"type": et.type, "description": et.description or f"{et.name}实体"}
            )

        # 构建输入结构（meta 在 data 内部）
        input_meta = {
            "source_type": "article" if is_article else "chat",
            "source_title": metadata.get("document_title", ""),
            "source_summary": metadata.get("document_summary", ""),
            "entity_types": entity_types_data,
        }

        # 可选字段：previous_context
        previous_context = metadata.get("previous_context", "")
        if previous_context:
            input_meta["previous_context"] = previous_context

        return {
            "type": "request",
            "data": {
                "items": items_data,
                "meta": input_meta,
            },
        }

    def _build_schema(self) -> dict:
        """构建输出 Schema"""
        _template_name, config = self._get_extract_prompt_config()
        output_schema = config.get("output_schema", {})
        definitions = config.get("definitions", {})

        schema = copy.deepcopy({**output_schema, "definitions": definitions})

        # 动态注入实体类型枚举
        valid_types = [et.type for et in self.entity_types]
        if valid_types:
            try:
                if "definitions" in schema and "entity" in schema["definitions"]:
                    entity_def = schema["definitions"]["entity"]
                    if "properties" in entity_def and "type" in entity_def["properties"]:
                        entity_def["properties"]["type"]["enum"] = valid_types
                        logger.info(f"注入实体类型枚举: {len(valid_types)} 个类型")
            except Exception as e:
                logger.info(f"注入实体类型枚举失败: {e}，继续使用默认 schema")

        return schema

    async def _call_llm_with_retry(self, messages: list[LLMMessage], schema: dict) -> dict:
        """调用 LLM（带重试）"""
        try:
            logger.info("调用 LLM（带重试机制）")

            result = await self.llm_client.chat_with_schema(messages, response_schema=schema)

            logger.info("LLM 调用成功")
            return result

        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            raise ExtractError(f"LLM 调用失败: {e}") from e

    def _validate_output(self, result: dict):
        """
        校验输出格式（增强验证）

        严格验证：结构错误会抛出异常
        宽松验证：内容质量问题只记录警告，不中断任务
        """
        # === 严格验证：结构错误 ===
        if result.get("type") != "response":
            raise ValueError(f"输出 type 必须为 'response'，实际: {result.get('type')}")

        if "data" not in result:
            raise ValueError("输出缺少 'data' 字段")

        if "items" not in result.get("data", {}):
            raise ValueError("输出 data 缺少 'items' 字段")

        if "meta" not in result.get("data", {}):
            raise ValueError("输出 data 缺少 'meta' 字段")

        # === 宽松验证：内容质量（记录警告，不中断） ===
        items = result.get("data", {}).get("items", [])
        valid_types = {et.type for et in self.entity_types}

        empty_refs_count = 0
        empty_title_count = 0
        empty_content_count = 0
        invalid_entity_types = set()

        def validate_item(item: dict, path: str = ""):
            """递归验证事项（包括 children）"""
            nonlocal empty_refs_count, empty_title_count, empty_content_count

            item_path = f"{path}.{item.get('title', '?')}" if path else item.get("title", "?")

            # 验证 references（只统计，不单独记录）
            refs = item.get("references", [])
            if not refs or len(refs) == 0:
                empty_refs_count += 1

            # 验证 title（只统计，不单独记录）
            if not item.get("title", "").strip():
                empty_title_count += 1

            # 验证 content（只统计，不单独记录）
            if not item.get("content", "").strip():
                empty_content_count += 1

            # 验证实体类型
            entities = item.get("entities", [])
            for entity in entities:
                entity_type = entity.get("type")
                if entity_type and entity_type not in valid_types:
                    invalid_entity_types.add(entity_type)

            # 递归验证 children
            children = item.get("children", [])
            for child in children:
                validate_item(child, item_path)

        # 验证所有事项
        for item in items:
            validate_item(item)

        # 汇总警告
        if empty_refs_count > 0:
            logger.warning(f"输出验证: {empty_refs_count} 个事项的 references 为空")
        if empty_title_count > 0:
            logger.warning(f"输出验证: {empty_title_count} 个事项的 title 为空")
        if empty_content_count > 0:
            logger.warning(f"输出验证: {empty_content_count} 个事项的 content 为空")
        if invalid_entity_types:
            logger.warning(
                f"输出验证: 发现无效实体类型 {invalid_entity_types}，"
                f"允许的类型: {sorted(valid_types)}"
            )


    def _log_extract_result(self, result: dict) -> None:
        """记录 LLM 提取结果（策略感知）"""
        meta = result.get("data", {}).get("meta", {})
        logger.info(
            "LLM返回: reason=%s, confidence=%s",
            meta.get("reason", ""),
            meta.get("confidence", 0),
        )
