import logging

logger = logging.getLogger(__name__)


class TimeTrackerManager:
    """Stub — time tracking persistence not used in rag_core MVP."""

    def save_tracking_data(self, *args, **kwargs):
        pass

    def get_average_times(self, *args, **kwargs):
        return {}

    def get_tracking_data(self, *args, **kwargs):
        return []
