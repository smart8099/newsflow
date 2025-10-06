"""
URL configuration for NewsFlow news application.

Provides Google News-style routing with clean URLs for categories,
search, trending, and API endpoints.
"""

from django.urls import include
from django.urls import path

from . import views
from .search_views import AutocompleteView

app_name = "news"

urlpatterns = [
    # Main news pages
    path("", views.NewsHomeView.as_view(), name="home"),
    path("category/<str:category>/", views.CategoryNewsView.as_view(), name="category"),
    path("search/", views.SearchResultsView.as_view(), name="search"),
    path("trending/", views.TrendingView.as_view(), name="trending"),
    path("for-you/", views.ForYouView.as_view(), name="for-you"),
    path("bookmarks/", views.BookmarksView.as_view(), name="bookmarks"),
    path("dashboard/", views.UserDashboardView.as_view(), name="dashboard"),
    path("preferences/", views.PreferencesView.as_view(), name="preferences"),
    # Admin dashboard (staff only)
    path(
        "admin-dashboard/",
        views.AdminDashboardView.as_view(),
        name="admin-dashboard",
    ),
    path(
        "admin-dashboard/analytics/",
        views.AdminAnalyticsView.as_view(),
        name="admin-analytics",
    ),
    path("admin-dashboard/users/", views.AdminUsersView.as_view(), name="admin-users"),
    path(
        "admin-dashboard/content/",
        views.AdminContentView.as_view(),
        name="admin-content",
    ),
    path(
        "admin-dashboard/search-analytics/",
        views.AdminSearchAnalyticsView.as_view(),
        name="admin-search-analytics",
    ),
    # AJAX/API endpoints
    path("api/track-click/", views.track_article_click, name="track-click"),
    path("api/bookmark/", views.bookmark_article, name="bookmark"),
    path("api/like/", views.like_article, name="like"),
    path("api/track-share/", views.track_share, name="track-share"),
    path("api/load-more/", views.load_more_articles, name="load-more"),
    path("api/save-preferences/", views.save_user_preferences, name="save-preferences"),
    path(
        "api/update-preferences/",
        views.update_preferences,
        name="update-preferences",
    ),
    # Search API endpoints (include from search_urls)
    path("api/search/", include("newsflow.news.search_urls")),
    # Direct autocomplete endpoint for HTMX
    path("api/autocomplete/", AutocompleteView.as_view(), name="autocomplete"),
    path("autocomplete/", views.autocomplete_suggestions, name="autocomplete-html"),
    # User-specific pages
    # path("history/", views.ReadingHistoryView.as_view(), name="history"),
]
