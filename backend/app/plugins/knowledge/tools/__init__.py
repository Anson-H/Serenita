from backend.app.agent_runtime.tools.base import Tool, ToolResult
from backend.app.application.knowledge_service import KnowledgeService


class KnowledgeTool(Tool):
    def __init__(self, context):
        self.account_id = context.account_id
        self.service = context.service("knowledge", KnowledgeService)

    def bind_runtime_arguments(self, arguments, *, context, observations):
        if context.account_id != self.account_id:
            raise PermissionError("知识库工具与当前任务的账号不一致。")
        return dict(arguments)


class SearchKnowledgeTool(KnowledgeTool):
    name = "search_knowledge"
    description = "搜索当前账号的知识库，返回相关文件、匹配片段和内容位置。"
    input_schema = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 500, "description": "根据当前问题提炼的文件名或正文关键词，去除首尾空白后为 1 至 500 个字符；按中文相邻字和其他语言词语进行全文搜索，不接受空白或 null。"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 30, "description": "最多返回的相关文件数，默认 8，允许 1 至 30；每份文件返回相关度最高的一段，不接受 null。has_more 表示还有匹配文件。"},
        },
        "required": ["query"],
    }

    def run(self, arguments):
        return ToolResult(name=self.name, output=self.service.search(self.account_id, **arguments))


class ReadKnowledgeFileTool(KnowledgeTool):
    name = "read_knowledge_file"
    description = "读取知识库文件的原文，将所选内容交给模型并返回读取范围和引用位置。"
    input_schema = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "document_id": {"type": "string", "format": "uuid", "description": "目标文件的规范 UUID，取自当前账号知识库搜索结果或文件目录，不接受文件名、路径、空字符串或 null。"},
            "segment_start": {"type": "integer", "minimum": 1, "description": "起始内容段的一基索引，默认 1；取自搜索结果的 segment_index 或上次读取的 next_segment，不得超过文件 segment_count，不接受 null。"},
            "segment_count": {"type": "integer", "minimum": 1, "maximum": 8, "description": "连续读取的内容段数量，默认 4，允许 1 至 8，文件末尾返回实际剩余范围；每段最多 2000 字符，不接受 null。"},
            "include_pdf_pages": {"type": "boolean", "description": "是否同时读取这些内容段所在的 PDF 原页，默认 false；核对图表或版式时可设 true，最多涉及 8 页，仅 PDF 可用，其他格式设 true 时失败，不接受 null。"},
        },
        "required": ["document_id"],
    }

    def run(self, arguments):
        values = dict(arguments)
        include_pages = values.pop("include_pdf_pages", False)
        result = self.service.read(self.account_id, **values)
        if include_pages and result["document"]["mime_type"] != "application/pdf":
            from backend.app.core.errors import raise_error
            raise_error("invalid_input", "KNOWLEDGE_RESOURCE_INVALID", "只有 PDF 支持原页读取。")
        reference = {"resource_id": result["document"]["document_id"], "segment_start": result["segment_start"],
                     "segment_count": len(result["segments"])}
        refs = [{"resource_type": "knowledge_text", **reference}]
        if include_pages:
            refs.append({"resource_type": "knowledge_pdf", **reference})
        output = {**result, "segments": [{key: value for key, value in segment.items() if key != "content"} for segment in result["segments"]]}
        return ToolResult(name=self.name, output=output, effects={"model_resource_refs": refs})
