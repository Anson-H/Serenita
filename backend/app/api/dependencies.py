from backend.app.application.conversation_service import ConversationService


def get_conversation_service() -> ConversationService:
    return ConversationService()
