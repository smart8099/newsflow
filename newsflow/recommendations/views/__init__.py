"""
Views package for recommendations app.
Imports all views for backward compatibility.
"""

from .analytics import UserAnalyticsView
from .analytics import record_interaction
from .explore import ExploreFeedView
from .personalized import PersonalizedFeedView
from .similar import SimilarArticlesView
from .trending import TrendingView

__all__ = [
    "ExploreFeedView",
    "PersonalizedFeedView",
    "SimilarArticlesView",
    "TrendingView",
    "UserAnalyticsView",
    "record_interaction",
]
