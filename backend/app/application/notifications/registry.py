"""Compose registered notification resource adapters."""


def build_notification_types(paths):
    from backend.app.application.conversations.notifications import (
        build_types as conversation_types,
    )
    from backend.app.application.medications.notifications import (
        build_types as medication_types,
    )

    result = {}
    for builder in (conversation_types, medication_types):
        for item in builder(paths):
            if item.name in result:
                raise ValueError("重复的通知类型")
            result[item.name] = item
    return result
