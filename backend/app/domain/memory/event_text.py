"""Compose retrieval input from the Event's stored text fields."""


def event_text(event):
    return "\n".join(dict.fromkeys(
        part for part in (event["title"], event["summary"], event["content"]) if part
    ))
