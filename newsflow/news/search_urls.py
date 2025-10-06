"""
URL configuration for NewsFlow search API endpoints.
"""

from django.urls import path

from .search_views import ArticleSearchView
from .search_views import AutocompleteView
from .search_views import TrendingSearchView
from .search_views import clear_search_history
from .search_views import search_history

app_name = "search"

urlpatterns = [
    # Main search endpoints
    path("articles/", ArticleSearchView.as_view(), name="article-search"),
    path("autocomplete/", AutocompleteView.as_view(), name="autocomplete"),
    path("trending/", TrendingSearchView.as_view(), name="trending"),
    # User search history
    path("history/", search_history, name="history"),
    path("history/clear/", clear_search_history, name="clear-history"),
]
