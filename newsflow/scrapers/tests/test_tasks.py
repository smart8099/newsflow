from datetime import timedelta
from unittest.mock import Mock
from unittest.mock import patch

from django.test import TestCase
from django.test import TransactionTestCase
from django.utils import timezone

from newsflow.news.models import Article
from newsflow.news.models import NewsSource
from newsflow.scrapers import tasks


class ScrapingTasksTestCase(TestCase):
    """Test cases for scraping Celery tasks."""

    def setUp(self):
        """Set up test data."""
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
            last_scraped=timezone.now() - timedelta(hours=2),  # Due for scraping
        )

        self.inactive_source = NewsSource.objects.create(
            name="Inactive Source",
            base_url="https://inactive.com",
            source_type="rss",
            primary_category="general",
            country="US",
            language="en",
            is_active=False,
        )

    @patch("newsflow.scrapers.tasks.NewsScraperService")
    def test_scrape_single_source_success(self, mock_scraper_class):
        """Test successful single source scraping."""
        # Mock the scraper service
        mock_scraper = Mock()
        mock_scraper.scrape_rss_feed.return_value = {
            "success": 5,
            "failed": 1,
            "duplicates": 2,
        }
        mock_scraper_class.return_value = mock_scraper

        # Execute task
        result = tasks.scrape_single_source(self.news_source.id)

        # Verify results
        self.assertEqual(result["success"], 5)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["duplicates"], 2)

        # Verify scraper was called correctly
        mock_scraper.scrape_rss_feed.assert_called_once_with(self.news_source.id)

    def test_scrape_single_source_not_found(self):
        """Test scraping with non-existent source ID."""
        result = tasks.scrape_single_source(99999)

        self.assertEqual(result["success"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["duplicates"], 0)
        self.assertIn("error", result)

    def test_scrape_single_source_inactive(self):
        """Test scraping with inactive source."""
        result = tasks.scrape_single_source(self.inactive_source.id)

        self.assertEqual(result["success"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["duplicates"], 0)
        self.assertIn("error", result)

    def test_scrape_single_source_not_due(self):
        """Test scraping source that's not due for scraping."""
        # Set last_scraped to recent time
        self.news_source.last_scraped = timezone.now()
        self.news_source.save()

        result = tasks.scrape_single_source(self.news_source.id)

        self.assertEqual(result["success"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["duplicates"], 0)
        self.assertTrue(result.get("skipped", False))

    @patch("newsflow.scrapers.tasks.scrape_single_source")
    def test_scrape_all_active_sources(self, mock_single_scrape):
        """Test bulk scraping of all active sources."""
        # Create additional sources due for scraping
        source2 = NewsSource.objects.create(
            name="Source 2",
            base_url="https://source2.com",
            source_type="website",
            primary_category="business",
            country="US",
            language="en",
            is_active=True,
            last_scraped=timezone.now() - timedelta(hours=3),
        )

        # Mock the individual scraping tasks
        mock_single_scrape.s.return_value = Mock()
        mock_group = Mock()
        mock_group.apply_async.return_value.get.return_value = [
            {"success": 3, "failed": 0, "duplicates": 1},
            {"success": 2, "failed": 1, "duplicates": 0},
        ]

        with patch("newsflow.scrapers.tasks.group", return_value=mock_group):
            result = tasks.scrape_all_active_sources()

        self.assertEqual(result["success"], 5)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(result["sources_processed"], 2)

    def test_scrape_all_active_sources_no_sources_due(self):
        """Test bulk scraping when no sources are due."""
        # Make all sources not due for scraping
        self.news_source.last_scraped = timezone.now()
        self.news_source.save()

        result = tasks.scrape_all_active_sources()

        self.assertEqual(result["success"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["duplicates"], 0)
        self.assertEqual(result["sources_processed"], 0)

    def test_scheduled_scraper(self):
        """Test the scheduled scraper task."""
        with patch("newsflow.scrapers.tasks.scrape_single_source") as mock_scrape:
            mock_scrape.delay.return_value = Mock()

            result = tasks.scheduled_scraper()

            # Should queue scraping for our due source
            self.assertEqual(result["sources_scraped"], 1)
            self.assertEqual(result["sources_checked"], 2)  # 1 active + 1 inactive
            mock_scrape.delay.assert_called_once_with(self.news_source.id)

    def test_cleanup_old_articles(self):
        """Test cleanup of old articles."""
        # Create old and new articles
        old_date = timezone.now() - timedelta(days=35)
        new_date = timezone.now() - timedelta(days=1)

        old_article = Article.objects.create(
            title="Old Article",
            url="https://example.com/old",
            content="Old content",
            source=self.news_source,
            published_at=old_date,
            scraped_at=old_date,
            is_published=True,
        )

        new_article = Article.objects.create(
            title="New Article",
            url="https://example.com/new",
            content="New content",
            source=self.news_source,
            published_at=new_date,
            scraped_at=new_date,
            is_published=True,
        )

        # Run cleanup
        result = tasks.cleanup_old_articles(days_old=30)

        # Check results
        self.assertEqual(result["archived"], 1)

        # Verify articles state
        old_article.refresh_from_db()
        new_article.refresh_from_db()

        self.assertFalse(old_article.is_published)  # Should be archived
        self.assertTrue(new_article.is_published)  # Should remain published

    def test_cleanup_old_articles_no_old_articles(self):
        """Test cleanup when no old articles exist."""
        # Create only recent articles
        Article.objects.create(
            title="Recent Article",
            url="https://example.com/recent",
            content="Recent content",
            source=self.news_source,
            published_at=timezone.now() - timedelta(days=1),
            scraped_at=timezone.now() - timedelta(days=1),
            is_published=True,
        )

        result = tasks.cleanup_old_articles(days_old=30)

        self.assertEqual(result["archived"], 0)
        self.assertEqual(result["deleted"], 0)

    def test_update_source_statistics(self):
        """Test updating source statistics."""
        # Create some test articles
        for i in range(3):
            Article.objects.create(
                title=f"Article {i}",
                url=f"https://example.com/article-{i}",
                content="Test content",
                source=self.news_source,
                published_at=timezone.now() - timedelta(hours=i),
                scraped_at=timezone.now() - timedelta(hours=i),
            )

        result = tasks.update_source_statistics(self.news_source.id)

        self.assertEqual(result["source_name"], self.news_source.name)
        self.assertEqual(result["articles_last_24h"], 3)
        self.assertIn("avg_articles_per_day", result)
        self.assertIn("total_articles", result)

    def test_update_source_statistics_not_found(self):
        """Test updating statistics for non-existent source."""
        result = tasks.update_source_statistics(99999)

        self.assertIn("error", result)
        self.assertEqual(result["error"], "Source not found")

    @patch("newsflow.scrapers.tasks.NewsScraperService")
    def test_scrape_single_article_success(self, mock_scraper_class):
        """Test successful single article scraping."""
        mock_scraper = Mock()
        mock_scraper.scrape_article.return_value = {
            "title": "Test Article",
            "content": "Test content " * 30,
            "summary": "Test summary",
            "author": "Test Author",
            "published_at": timezone.now(),
            "top_image": "",
            "keywords": ["test"],
            "read_time": 2,
        }
        mock_scraper.validate_article_quality.return_value = (True, "Valid article")
        mock_scraper._is_duplicate_article.return_value = False
        mock_scraper._save_article.return_value = Mock(
            id=1,
            title="Test Article",
            url="https://test.com",
        )
        mock_scraper_class.return_value = mock_scraper

        result = tasks.scrape_single_article(
            "https://test.com/article",
            self.news_source.id,
        )

        self.assertTrue(result["success"])
        self.assertIn("article_id", result)

    @patch("newsflow.scrapers.tasks.NewsScraperService")
    def test_scrape_single_article_failure(self, mock_scraper_class):
        """Test single article scraping failure."""
        mock_scraper = Mock()
        mock_scraper.scrape_article.return_value = None
        mock_scraper_class.return_value = mock_scraper

        result = tasks.scrape_single_article("https://test.com/failing-article")

        self.assertFalse(result["success"])
        self.assertIn("error", result)

    @patch("requests.head")
    def test_health_check_sources(self, mock_requests):
        """Test health check for all sources."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_requests.return_value = mock_response

        result = tasks.health_check_sources()

        self.assertEqual(result["total_sources"], 2)  # 1 active + 1 inactive
        self.assertEqual(result["healthy_sources"], 2)
        self.assertEqual(result["unhealthy_sources"], 0)

    @patch("requests.head")
    def test_health_check_sources_with_failures(self, mock_requests):
        """Test health check with some source failures."""
        # Mock failing response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_requests.return_value = mock_response

        result = tasks.health_check_sources()

        self.assertEqual(result["total_sources"], 2)
        self.assertEqual(result["healthy_sources"], 0)
        self.assertEqual(result["unhealthy_sources"], 2)

    @patch("requests.head")
    def test_health_check_sources_with_exceptions(self, mock_requests):
        """Test health check with connection exceptions."""
        # Mock connection error
        mock_requests.side_effect = Exception("Connection failed")

        result = tasks.health_check_sources()

        self.assertEqual(result["total_sources"], 2)
        self.assertEqual(result["healthy_sources"], 0)
        self.assertEqual(result["unhealthy_sources"], 2)


class TaskRetryTestCase(TransactionTestCase):
    """Test task retry mechanisms."""

    def setUp(self):
        """Set up test data."""
        self.news_source = NewsSource.objects.create(
            name="Retry Test Source",
            base_url="https://example.com",
            source_type="rss",
            primary_category="technology",
            country="US",
            language="en",
            is_active=True,
            last_scraped=timezone.now() - timedelta(hours=2),
        )

    @patch("newsflow.scrapers.tasks.NewsScraperService")
    def test_scrape_single_source_retry_mechanism(self, mock_scraper_class):
        """Test that task retries on failure."""
        # Mock scraper to raise exception
        mock_scraper = Mock()
        mock_scraper.scrape_rss_feed.side_effect = Exception("Network error")
        mock_scraper_class.return_value = mock_scraper

        # The task should raise an exception to trigger retry
        with self.assertRaises(Exception):
            tasks.scrape_single_source(self.news_source.id)

    @patch("newsflow.scrapers.tasks.NewsScraperService")
    def test_scrape_single_source_success_rate_update(self, mock_scraper_class):
        """Test that success rate is updated correctly."""
        mock_scraper = Mock()
        mock_scraper.scrape_rss_feed.return_value = {
            "success": 8,
            "failed": 2,
            "duplicates": 0,
        }
        mock_scraper_class.return_value = mock_scraper

        # Execute task
        tasks.scrape_single_source(self.news_source.id)

        # Refresh source from database
        self.news_source.refresh_from_db()

        # Verify success rate was updated (8/10 = 80%)
        self.assertEqual(self.news_source.success_rate, 80.0)

    @patch("newsflow.scrapers.tasks.NewsScraperService")
    def test_scrape_single_source_performance_tracking(self, mock_scraper_class):
        """Test that performance metrics are tracked."""
        mock_scraper = Mock()
        mock_scraper.scrape_rss_feed.return_value = {
            "success": 5,
            "failed": 0,
            "duplicates": 1,
        }
        mock_scraper_class.return_value = mock_scraper

        # Record initial response time
        initial_response_time = self.news_source.average_response_time

        # Execute task
        tasks.scrape_single_source(self.news_source.id)

        # Refresh source from database
        self.news_source.refresh_from_db()

        # Verify response time was updated
        self.assertIsNotNone(self.news_source.average_response_time)
        self.assertNotEqual(
            self.news_source.average_response_time,
            initial_response_time,
        )
