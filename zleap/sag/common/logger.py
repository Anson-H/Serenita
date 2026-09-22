"""Use application logging without upstream global configuration."""
import logging

def get_logger(name: str) -> logging.Logger:
    """
    获取日志器

    Args:
        name: 日志器名称

    Returns:
        日志器实例
    """
    return logging.getLogger(f"zleap.sag.{name}")
