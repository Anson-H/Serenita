"""Extraction exceptions copied from SAG-Benchmark."""

class PipelineError(Exception):
    """pipeline 基础异常类"""

    def __init__(self, message: str, *args: object) -> None:
        self.message = message
        super().__init__(message, *args)


class ExtractError(PipelineError):
    """事项提取异常"""

    pass
