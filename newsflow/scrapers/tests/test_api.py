from unittest.mock import Mock
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from newsflow.news.models import Article
from newsflow.news.models import NewsSource

User = get_user_model()


class ScrapingAPITestCase(TestCase):
    """Test cases for scraping API endpoints."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email="test@example.com",
            name="Test User",
        )

        self.news_source = NewsSource.objects.create(
            name="Test News Source",
            base_url="https://example.com",
            rss_feed="https://example.com/rss",
            source_type="rss",
            primary_category="technology",
            country="US",
            language="en",
            is_active=True,
            scrape_frequency=60,
            max_articles_per_scrape=10,
            success_rate=85.0,
            total_articles_scraped=100,
        )

        self.inactive_source = NewsSource.objects.create(
            name="Inactive Source",
            base_url="https://inactive.com",
            source_type="website",
            primary_category="general",
            country="US",
            language="en",
            is_active=False,
        )

        self.client = Client()
        self.client.force_login(self.user)

    def test_scrape_source_api_success(self):
        """Test successful source scraping via API."""
        with patch("newsflow.scrapers.api.scrape_single_source") as mock_task:
            mock_task.delay.return_value = Mock(id="task-123")

            # Make source due for scraping
            self.news_source.last_scraped = timezone.now() - timezone.timedelta(hours=2)
            self.news_source.save()

            url = reverse("scrapers:api_scrape_source", args=[self.news_source.id])
            response = self.client.post(url)

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["task_id"], "task-123")
            self.assertEqual(data["source_name"], self.news_source.name)
            mock_task.delay.assert_called_once_with(self.news_source.id)

    def test_scrape_source_api_not_due(self):
        """Test scraping source that's not due for scraping."""
        # Make source not due for scraping
        self.news_source.last_scraped = timezone.now()
        self.news_source.save()

        url = reverse("scrapers:api_scrape_source", args=[self.news_source.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("not due for scraping", data["error"])

    def test_scrape_source_api_force(self):
        """Test force scraping source via API."""
        with patch("newsflow.scrapers.api.scrape_single_source") as mock_task:
            mock_task.delay.return_value = Mock(id="task-456")

            # Make source not due for scraping
            self.news_source.last_scraped = timezone.now()
            self.news_source.save()

            url = reverse("scrapers:api_scrape_source", args=[self.news_source.id])
            response = self.client.post(url, {"force": "true"})

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["success"])
            mock_task.delay.assert_called_once_with(self.news_source.id)

    def test_scrape_source_api_not_found(self):
        """Test scraping non-existent source."""
        url = reverse("scrapers:api_scrape_source", args=[99999])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("not found", data["error"])

    def test_scrape_source_api_inactive(self):
        """Test scraping inactive source."""
        url = reverse("scrapers:api_scrape_source", args=[self.inactive_source.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data["success"])

    def test_scrape_all_sources_api_success(self):
        """Test bulk scraping via API."""
        with patch("newsflow.scrapers.api.scrape_all_active_sources") as mock_task:
            mock_task.delay.return_value = Mock(id="bulk-task-789")

            # Make source due for scraping
            self.news_source.last_scraped = timezone.now() - timezone.timedelta(hours=2)
            self.news_source.save()

            url = reverse("scrapers:api_scrape_all_sources")
            response = self.client.post(url)

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["task_id"], "bulk-task-789")
            self.assertEqual(data["sources_due"], 1)
            self.assertIn(self.news_source.name, data["source_names"])

    def test_scrape_all_sources_api_no_sources_due(self):
        """Test bulk scraping when no sources are due."""
        # Make sure no sources are due for scraping
        self.news_source.last_scraped = timezone.now()
        self.news_source.save()

        url = reverse("scrapers:api_scrape_all_sources")
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["sources_due"], 0)
        self.assertIn("No sources are due", data["message"])

    @patch("newsflow.scrapers.api.NewsScraperService")
    def test_scrape_article_api_test_mode(self, mock_scraper_class):
        """Test scraping single article in test mode."""
        mock_scraper = Mock()
        mock_scraper.scrape_article.return_value = {
            "title": "Test Article",
            "content": "Test content " * 30,
            "summary": "Test summary",
            "author": "Test Author",
            "published_at": timezone.now(),
            "top_image": "",
            "keywords": ["test", "article"],
            "read_time": 2,
        }
        mock_scraper.validate_article_quality.return_value = (True, "Valid article")
        mock_scraper_class.return_value = mock_scraper

        url = reverse("scrapers:api_scrape_article")
        response = self.client.post(
            url,
            {
                "url": "https://example.com/test-article",
                "test_mode": "true",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["test_mode"])
        self.assertEqual(data["article"]["title"], "Test Article")
        self.assertTrue(data["quality_check"]["is_valid"])

    def test_scrape_article_api_async_mode(self):
        """Test scraping single article in async mode."""
        with patch("newsflow.scrapers.api.scrape_single_article") as mock_task:
            mock_task.delay.return_value = Mock(id="article-task-123")

            url = reverse("scrapers:api_scrape_article")
            response = self.client.post(
                url,
                {
                    "url": "https://example.com/test-article",
                    "source_id": str(self.news_source.id),
                },
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["task_id"], "article-task-123")
            self.assertEqual(data["url"], "https://example.com/test-article")

    def test_scrape_article_api_missing_url(self):
        """Test scraping article without URL."""
        url = reverse("scrapers:api_scrape_article")
        response = self.client.post(url)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("URL parameter is required", data["error"])

    def test_health_check_api(self):
        """Test health check API."""
        with patch("newsflow.scrapers.api.health_check_sources") as mock_task:
            mock_task.delay.return_value = Mock(id="health-check-456")

            url = reverse("scrapers:api_health_check")
            response = self.client.post(url)

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["task_id"], "health-check-456")

    @patch("newsflow.scrapers.api.NewsScraperService")
    def test_scraping_status_api(self, mock_scraper_class):
        """Test scraping status API."""
        # Create test articles
        for i in range(3):
            Article.objects.create(
                title=f"Test Article {i}",
                url=f"https://example.com/article-{i}",
                content="Test content",
                source=self.news_source,
                published_at=timezone.now(),
                scraped_at=timezone.now(),
            )

        mock_scraper = Mock()
        mock_scraper.get_scraping_statistics.return_value = {
            "total_sources": 2,
            "sources_due_for_scraping": 1,
            "total_articles_today": 3,
            "avg_success_rate": 85.0,
        }
        mock_scraper_class.return_value = mock_scraper

        # Make source due for scraping
        self.news_source.last_scraped = timezone.now() - timezone.timedelta(hours=2)
        self.news_source.save()

        url = reverse("scrapers:api_scraping_status")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["global_stats"]["total_sources"], 2)
        self.assertEqual(data["sources_due_count"], 1)
        self.assertEqual(len(data["recent_articles"]), 3)
        self.assertGreater(len(data["source_stats"]), 0)

    @patch("newsflow.scrapers.api.NewsScraperService")
    def test_source_stats_api(self, mock_scraper_class):
        """Test source statistics API."""
        mock_scraper = Mock()
        mock_scraper.get_scraping_statistics.return_value = {
            "source_name": self.news_source.name,
            "total_articles": 100,
            "success_rate": 85.0,
            "last_scraped": self.news_source.last_scraped,
        }
        mock_scraper_class.return_value = mock_scraper

        url = reverse("scrapers:api_source_stats", args=[self.news_source.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["source_name"], self.news_source.name)
        self.assertIn("source_details", data)
        self.assertEqual(data["source_details"]["name"], self.news_source.name)

    def test_source_stats_api_not_found(self):
        """Test source statistics API with non-existent source."""
        url = reverse("scrapers:api_source_stats", args=[99999])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data["success"])

    def test_list_sources_api(self):
        """Test list sources API."""
        url = reverse("scrapers:api_list_sources")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["count"], 2)  # Active + inactive
        self.assertEqual(len(data["sources"]), 2)

        # Check source data structure
        source_data = next(s for s in data["sources"] if s["id"] == self.news_source.id)
        self.assertEqual(source_data["name"], self.news_source.name)
        self.assertEqual(source_data["source_type"], self.news_source.source_type)
        self.assertTrue(source_data["is_active"])

    def test_toggle_source_status_api(self):
        """Test toggling source active status."""
        initial_status = self.news_source.is_active

        url = reverse("scrapers:api_toggle_source", args=[self.news_source.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["source_id"], self.news_source.id)
        self.assertNotEqual(data["is_active"], initial_status)

        # Verify in database
        self.news_source.refresh_from_db()
        self.assertEqual(self.news_source.is_active, data["is_active"])

    def test_toggle_source_status_api_not_found(self):
        """Test toggling status of non-existent source."""
        url = reverse("scrapers:api_toggle_source", args=[99999])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data["success"])

    def test_api_requires_authentication(self):
        """Test that API endpoints require authentication."""
        # Logout user
        self.client.logout()

        # Test various endpoints
        endpoints = [
            reverse("scrapers:api_scrape_source", args=[self.news_source.id]),
            reverse("scrapers:api_scrape_all_sources"),
            reverse("scrapers:api_scrape_article"),
            reverse("scrapers:api_health_check"),
            reverse("scrapers:api_scraping_status"),
            reverse("scrapers:api_source_stats", args=[self.news_source.id]),
            reverse("scrapers:api_list_sources"),
            reverse("scrapers:api_toggle_source", args=[self.news_source.id]),
        ]

        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                if (
                    "list_sources" in endpoint
                    or "scraping_status" in endpoint
                    or "source_stats" in endpoint
                ):
                    # GET endpoints
                    response = self.client.get(endpoint)
                else:
                    # POST endpoints
                    response = self.client.post(endpoint)

                # Should redirect to login or return 403/401
                self.assertIn(response.status_code, [302, 401, 403])


class ScrapingDashboardTestCase(TestCase):
    """Test cases for scraping dashboard view."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email="test@example.com",
            name="Test User",
        )

        self.news_source = NewsSource.objects.create(
            name="Dashboard Test Source",
            base_url="https://example.com",
            source_type="rss",
            primary_category="technology",
            country="US",
            language="en",
            is_active=True,
        )

        self.client = Client()
        self.client.force_login(self.user)

    @patch("newsflow.scrapers.api.NewsScraperService")
    def test_dashboard_view(self, mock_scraper_class):
        """Test dashboard view loads correctly."""
        mock_scraper = Mock()
        mock_scraper.get_scraping_statistics.return_value = {
            "total_sources": 1,
            "sources_due_for_scraping": 0,
            "total_articles_today": 5,
            "avg_success_rate": 90.0,
        }
        mock_scraper_class.return_value = mock_scraper

        url = reverse("scrapers:dashboard")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("stats", response.context)
        self.assertIn("sources_due", response.context)
        self.assertIn("active_sources_count", response.context)

    def test_dashboard_requires_authentication(self):
        """Test that dashboard requires authentication."""
        self.client.logout()

        url = reverse("scrapers:dashboard")
        response = self.client.get(url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)

    @patch("newsflow.scrapers.api.NewsScraperService")
    def test_dashboard_with_error(self, mock_scraper_class):
        """Test dashboard view when error occurs."""
        mock_scraper = Mock()
        mock_scraper.get_scraping_statistics.side_effect = Exception("Service error")
        mock_scraper_class.return_value = mock_scraper

        url = reverse("scrapers:dashboard")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)


class APIErrorHandlingTestCase(TestCase):
    """Test cases for API error handling."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email="test@example.com",
            name="Test User",
        )

        self.client = Client()
        self.client.force_login(self.user)

    @patch("newsflow.scrapers.api.scrape_single_source")
    def test_api_task_exception_handling(self, mock_task):
        """Test API handles task exceptions gracefully."""
        mock_task.delay.side_effect = Exception("Celery error")

        news_source = NewsSource.objects.create(
            name="Error Test Source",
            base_url="https://example.com",
            source_type="rss",
            primary_category="technology",
            country="US",
            language="en",
            is_active=True,
            last_scraped=timezone.now() - timezone.timedelta(hours=2),
        )

        url = reverse("scrapers:api_scrape_source", args=[news_source.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("Failed to queue scraping task", data["error"])

    @patch("newsflow.scrapers.api.NewsScraperService")
    def test_api_service_exception_handling(self, mock_scraper_class):
        """Test API handles service exceptions gracefully."""
        mock_scraper = Mock()
        mock_scraper.scrape_article.side_effect = Exception("Service error")
        mock_scraper_class.return_value = mock_scraper

        url = reverse("scrapers:api_scrape_article")
        response = self.client.post(
            url,
            {
                "url": "https://example.com/test-article",
                "test_mode": "true",
            },
        )

        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("Failed to scrape article", data["error"])
