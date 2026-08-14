class RecommendationNotFound(Exception):
    """Raised when a recommendation scenario cannot be found."""


class RecommendationNotReady(Exception):
    """Raised when recommendation prerequisites are not satisfied."""
