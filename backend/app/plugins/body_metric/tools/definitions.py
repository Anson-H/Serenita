"""Construct the body metric tool collection."""

from .parameters import build_parameters
from .record_tools import BodyTool


def create_tools(*, runtime_context):
    if not runtime_context.member_id:
        return []
    return [
        BodyTool(runtime_context, name, shape)
        for name, shape in build_parameters().items()
    ]
