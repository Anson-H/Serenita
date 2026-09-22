"""Message classes copied from SAG-Benchmark."""
from enum import Enum
from pydantic import BaseModel, Field

class LLMRole(str, Enum):
    """消息角色"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LLMMessage(BaseModel):
    """LLM消息模型"""

    role: LLMRole = Field(..., description="角色")
    content: str = Field(..., description="消息内容")
