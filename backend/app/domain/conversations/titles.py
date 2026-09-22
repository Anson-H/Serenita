"""会话标题的长度、清理词表和默认值，供索引与标题任务共用。"""

SESSION_TITLE_MAX_CHARS = 14
SESSION_TITLE_INITIAL_CHARS = 10
SESSION_TITLE_TARGET_CJK_CHARACTERS = 8
SESSION_TITLE_TARGET_WORDS = 5

# Title-only vocabulary lives here instead of leaking into the main agent prompt.
SESSION_TITLE_FOCUS_KEYWORDS = ("健康主题", "处理方向")
TITLE_PREFIXES = (
    "你好",
    "您好",
    "请问",
    "麻烦你",
    "麻烦",
    "帮我看看",
    "可以帮我看看",
    "可以帮我",
    "我想问问",
    "我想问一下",
    "想问问",
    "想问一下",
    "我想了解",
    "我想",
    "我最近",
    "最近",
    "我",
)
TITLE_TAIL_REPLACEMENTS = (
    ("需要注意些什么", "注意事项"),
    ("需要注意什么", "注意事项"),
    ("要注意些什么", "注意事项"),
    ("要注意什么", "注意事项"),
    ("应该注意些什么", "注意事项"),
    ("应该注意什么", "注意事项"),
    ("该注意些什么", "注意事项"),
    ("该注意什么", "注意事项"),
    ("怎么办", "处理建议"),
    ("怎么处理", "处理建议"),
    ("怎么回事", "原因分析"),
    ("是什么原因", "原因分析"),
)
TITLE_LEADING_LABELS = (
    "模型真实回复",
    "核心结论",
    "下一步建议",
    "结论",
    "建议",
)

UNTITLED_CONVERSATION = "新聊天"
