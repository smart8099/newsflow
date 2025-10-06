from django.urls import path

from . import api

app_name = "scrapers"

urlpatterns = [
    # Dashboard
    path("dashboard/", api.ScrapingDashboardView.as_view(), name="dashboard"),
    # API endpoints
    path(
        "api/scrape/source/<int:source_id>/",
        api.ScrapeSourceAPIView.as_view(),
        name="api_scrape_source",
    ),
    path(
        "api/scrape/all-sources/",
        api.ScrapeAllSourcesAPIView.as_view(),
        name="api_scrape_all_sources",
    ),
    path(
        "api/scrape/article/",
        api.ScrapeArticleAPIView.as_view(),
        name="api_scrape_article",
    ),
    path(
        "api/health-check/",
        api.HealthCheckAPIView.as_view(),
        name="api_health_check",
    ),
    path(
        "api/status/",
        api.ScrapingStatusAPIView.as_view(),
        name="api_scraping_status",
    ),
    path(
        "api/source/<int:source_id>/stats/",
        api.SourceStatsAPIView.as_view(),
        name="api_source_stats",
    ),
    path("api/sources/", api.list_sources_api, name="api_list_sources"),
    path(
        "api/source/<int:source_id>/toggle/",
        api.toggle_source_status_api,
        name="api_toggle_source",
    ),
]
