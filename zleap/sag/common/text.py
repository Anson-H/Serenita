"""Required text helpers copied from SAG-Benchmark."""
import re

def normalize_heading_text(
    text: str | None,
    max_length: int = 500,
    suffix: str = "...",
) -> str:
    """
    规范化标题文本，并在超长时截断。

    Args:
        text: 原始标题文本
        max_length: 最大长度
        suffix: 截断后缀

    Returns:
        规范化后的标题文本
    """
    if not text:
        return ""

    normalized = text.strip()
    normalized = re.sub(r"^#{1,6}\s*", "", normalized)
    normalized = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", normalized)
    normalized = " ".join(normalized.split())

    if max_length <= 0 or len(normalized) <= max_length:
        return normalized

    if max_length <= len(suffix):
        return normalized[:max_length]

    return normalized[: max_length - len(suffix)].rstrip() + suffix


def count_chinese_characters(text: str) -> int:
    """
    统计中文字符数量

    Args:
        text: 文本内容

    Returns:
        中文字符数量
    """
    return len([c for c in text if "\u4e00" <= c <= "\u9fff"])


def estimate_tokens(text: str, method: str = "simple") -> int:
    """
    估算文本token数量

    Args:
        text: 文本内容
        method: 估算方法（simple | tiktoken）

    Returns:
        估算的token数量
    """
    if method == "tiktoken":
        try:
            import tiktoken

            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except ImportError:
            pass

    # 简单估算：中文1.5字符/token, 英文4字符/token
    chinese_count = count_chinese_characters(text)
    english_count = len(text) - chinese_count

    return int(chinese_count / 1.5 + english_count / 4)
