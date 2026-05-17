import logging

logger = logging.getLogger(__name__)


class ConversationManager:
    """Stub — conversation persistence not used in rag_core MVP."""

    def save_conversation(self, *args, **kwargs):
        pass

    def get_conversation(self, *args, **kwargs):
        return None

    def list_conversations(self, *args, **kwargs):
        return []
