"""Notification reception switches and their effective start times."""

from datetime import datetime


NOTIFICATION_TYPES = ("medication_due", "medication_expired", "answer_completed")
PREFERENCE_NAMES = ("notifications", *NOTIFICATION_TYPES)


def reception_since(preferences, notification_type):
    if not preferences["notifications_enabled"] or not preferences[f"{notification_type}_enabled"]:
        return None
    return max(
        datetime.fromisoformat(value)
        for value in (
            preferences["notifications_enabled_since"],
            preferences[f"{notification_type}_enabled_since"],
        )
        if value is not None
    )
