"""
News app models package.

This package contains all models for the news application, organized into
separate files for better maintainability.
"""

# Import all models to make them available when importing from news.models
from .article import Article
from .article import ArticleManager
from .bookmarks import BookmarkedArticle
from .bookmarks import LikedArticle
from .bookmarks import ReadArticle
from .category import Category
from .category import CategoryChoices
from .category import CategoryManager
from .news_source import NewsSource
from .news_source import NewsSourceManager
from .search_analytics import SearchAnalytics
from .search_analytics import SearchAnalyticsManager
from .user_interaction import UserInteraction
from .user_interaction import UserInteractionManager
from .user_preference import UserPreference

# Export all models for easy import
__all__ = [
    # NewsSource
    "NewsSource",
    "NewsSourceManager",
    # Category
    "Category",
    "CategoryManager",
    "CategoryChoices",
    # Article
    "Article",
    "ArticleManager",
    # User Interactions
    "UserInteraction",
    "UserInteractionManager",
    # User Preferences
    "UserPreference",
    # Bookmarks and Reading
    "BookmarkedArticle",
    "LikedArticle",
    "ReadArticle",
    # Search Analytics
    "SearchAnalytics",
    "SearchAnalyticsManager",
]
