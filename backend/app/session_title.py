from __future__ import annotations

import json
from typing import Any


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

SESSION_TITLE_SYSTEM_PROMPT = "\n".join(
    (
        "仅根据当前轮次的用户输入和附件内容生成简洁的会话标题。",
        "只输出标题本身的一行纯文本，不要引号、前缀、解释、Markdown、XML 或代码。",
        (
            "使用输入的语言，优先保留能表达"
            + "和".join(SESSION_TITLE_FOCUS_KEYWORDS)
            + "的关键词。"
        ),
        (
            f"中文标题以约 {SESSION_TITLE_TARGET_CJK_CHARACTERS} 个汉字为目标，"
            f"最多 {SESSION_TITLE_MAX_CHARS} 个字符；非中文标题以约 "
            f"{SESSION_TITLE_TARGET_WORDS} 个词为目标。"
        ),
    )
)


def session_title_messages(
    title_seed: str,
) -> list[dict[str, Any]]:
    """Build the isolated, JSON-framed auxiliary title request."""
    payload = {
        "title_seed": str(title_seed or ""),
    }
    return [
        {"role": "system", "content": SESSION_TITLE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "请从以下 JSON 生成会话标题：\n"
                + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            ),
        },
    ]

UNTITLED_CONVERSATION = "新聊天"
