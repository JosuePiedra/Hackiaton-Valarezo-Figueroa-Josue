import logging

logger = logging.getLogger(__name__)


class RateLimitManager:
    """Stub — rate limiting not used in rag_core MVP."""

    def check_rate_limit(self, *args, **kwargs):
        return True

    def increment_usage(self, *args, **kwargs):
        pass
