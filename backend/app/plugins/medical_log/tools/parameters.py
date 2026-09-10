LOG_ID = {"type": "string", "minLength": 1, "description": "当前成员健康日记的稳定标识，取自当前成员已有工具结果；不能使用医疗报告标识或其它成员的标识。"}
FIELDS = {
    "recorded_on": {"type": "string", "minLength": 10, "maxLength": 10, "description": "记录日期，合法 YYYY-MM-DD，精确到日；创建必填，更新省略保持原值，提交时替换原值；不接受 null、空字符串或无效日期。"},
    "title": {"type": "string", "minLength": 1, "description": "日记标题，创建必填，更新省略保持原值；去除首尾空白后必须非空，不接受 null。"},
    "content": {"type": "string", "minLength": 1, "description": "完整日记内容，创建必填，更新提交时替换全文、省略保持原值；去除首尾空白后必须非空，不接受 null。"},
}
