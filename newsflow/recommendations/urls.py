"""
URL patterns for the recommendations app.
"""

from django.urls import path

from . import views

app_name = "recommendations"

urlpatterns = [
    # Personalized feed
    path("feed/", views.PersonalizedFeedView.as_view(), name="personalized-feed"),
    # Similar articles
    path(
        "similar/<int:article_id>/",
        views.SimilarArticlesView.as_view(),
        name="similar-articles",
    ),
    # Trending articles
    path("trending/", views.TrendingView.as_view(), name="trending"),
    # Exploration feed
    path("explore/", views.ExploreFeedView.as_view(), name="explore-feed"),
    # User analytics
    path("analytics/", views.UserAnalyticsView.as_view(), name="user-analytics"),
    # Record interaction
    path("interaction/", views.record_interaction, name="record-interaction"),
]
