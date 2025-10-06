"""
Views package for news app.
Imports all views for backward compatibility.
"""

from .admin import AdminAnalyticsView
from .admin import AdminContentView
from .admin import AdminDashboardView
from .admin import AdminSearchAnalyticsView
from .admin import AdminUsersView
from .api import autocomplete_suggestions
from .api import bookmark_article
from .api import like_article
from .api import load_more_articles
from .api import save_user_preferences
from .api import track_article_click
from .api import track_share
from .bookmarks import BookmarksView
from .category import CategoryNewsView
from .dashboard import UserDashboardView
from .for_you import ForYouView
from .home import NewsHomeView
from .preferences import PreferencesView
from .preferences import update_preferences
from .search import SearchResultsView
from .trending import TrendingView

__all__ = [
    "AdminAnalyticsView",
    "AdminContentView",
    "AdminDashboardView",
    "AdminSearchAnalyticsView",
    "AdminUsersView",
    "BookmarksView",
    "CategoryNewsView",
    "ForYouView",
    "NewsHomeView",
    "PreferencesView",
    "SearchResultsView",
    "TrendingView",
    "UserDashboardView",
    "autocomplete_suggestions",
    "bookmark_article",
    "like_article",
    "load_more_articles",
    "save_user_preferences",
    "track_article_click",
    "track_share",
    "update_preferences",
]
