from backend.app.plugins.medical_log.tools.base import MedicalLogTool
from backend.app.plugins.medical_log.tools.parameters import LOG_ID


class ReadMedicalLogTool(MedicalLogTool):
    name = "read_log"
    description = "读取当前成员中匹配的健康日记，返回日记内容。"
    input_schema = {"type": "object", "properties": {
        "medical_log_ids": {"type": "array", "minItems": 1, "maxItems": 100, "uniqueItems": True, "items": LOG_ID, "description": "可选的一条或多条日记标识，取自当前成员已有工具结果；省略表示不按标识限定，提供时与日期、关键词共同筛选。接受 1 至 100 个非空、不重复的标识，不接受空数组或 null；任一标识已失效或不属于当前成员时整次失败。"},
        "after_date": {"type": "string", "minLength": 10, "maxLength": 10, "description": "可选记录日期下界，含当天，合法 YYYY-MM-DD；省略无下界，不接受空字符串或 null。不能晚于 before_date，与标识、关键词共同生效。"},
        "before_date": {"type": "string", "minLength": 10, "maxLength": 10, "description": "可选记录日期上界，含当天，合法 YYYY-MM-DD；省略无上界，不接受空字符串或 null。不能早于 after_date，与标识、关键词共同生效。"},
        "query": {"type": "string", "description": "标题或正文的字面关键词，与标识、日期条件共同生效；省略、空字符串或纯空白表示不限定关键词，不接受 null。"},
    }, "additionalProperties": False}
