from datetime import datetime
from datetime import timedelta
from unittest.mock import Mock
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from newsflow.news.models import Article
from newsflow.news.models import Category
from newsflow.news.models import NewsSource
from newsflow.scrapers.services import NewsScraperService


class NewsScraperServiceTestCase(TestCase):
    """Test cases for NewsScraperService."""

    def setUp(self):
        """Set up test data."""
        self.category = Category.objects.create(
            name="Technology",
            slug="technology",
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
        )

        self.scraper = NewsScraperService()

    def test_init(self):
        """Test NewsScraperService initialization."""
        self.assertIsNotNone(self.scraper.session)
        self.assertEqual(self.scraper.timeout, 30)
        self.assertEqual(self.scraper.retry_attempts, 3)
        self.assertEqual(self.scraper.rate_limit, 2)

    def test_extract_domain(self):
        """Test domain extraction from URLs."""
        test_cases = [
            ("https://www.example.com/article", "example.com"),
            ("http://subdomain.test.org/path", "test.org"),
            ("https://news.bbc.co.uk/article", "bbc.co.uk"),
        ]

        for url, expected_domain in test_cases:
            with self.subTest(url=url):
                domain = self.scraper._extract_domain(url)
                self.assertEqual(domain, expected_domain)

    def test_clean_content(self):
        """Test content cleaning functionality."""
        dirty_content = """
        This is a test article with extra    spaces.

        Follow us on Twitter!
        Subscribe to our newsletter.
        © 2023 Example Corp.
        """

        cleaned = self.scraper._clean_content(dirty_content)

        self.assertNotIn("Follow us on", cleaned)
        self.assertNotIn("Subscribe to", cleaned)
        self.assertNotIn("© 2023", cleaned)
        self.assertNotIn("  ", cleaned)  # No double spaces

    def test_calculate_read_time(self):
        """Test reading time calculation."""
        # Test with 400 words (should be 2 minutes at 200 wpm)
        content = " ".join(["word"] * 400)
        read_time = self.scraper._calculate_read_time(content)
        self.assertEqual(read_time, 2)

        # Test with very short content (should be minimum 1 minute)
        short_content = "Short article"
        read_time = self.scraper._calculate_read_time(short_content)
        self.assertEqual(read_time, 1)

    def test_extract_keywords(self):
        """Test keyword extraction."""
        content = """
        Artificial intelligence and machine learning are transforming technology.
        Deep learning algorithms and neural networks are becoming more sophisticated.
        """

        keywords = self.scraper._extract_keywords(content, max_keywords=5)

        self.assertIsInstance(keywords, list)
        self.assertLessEqual(len(keywords), 5)
        self.assertIn("artificial", keywords)
        self.assertIn("intelligence", keywords)

    def test_is_duplicate_article(self):
        """Test duplicate article detection."""
        # Create an existing article
        existing_url = "https://example.com/existing-article"
        Article.objects.create(
            title="Existing Article",
            url=existing_url,
            content="Some content",
            source=self.news_source,
            published_at=timezone.now(),
        )

        # Test exact URL match
        is_duplicate = self.scraper._is_duplicate_article(
            existing_url,
            "Different Title",
            self.news_source,
        )
        self.assertTrue(is_duplicate)

        # Test new URL
        is_duplicate = self.scraper._is_duplicate_article(
            "https://example.com/new-article",
            "New Title",
            self.news_source,
        )
        self.assertFalse(is_duplicate)

    def test_validate_article_quality_valid(self):
        """Test article quality validation with valid article."""
        valid_article = {
            "title": "Test Article Title",
            "content": "This is a test article with enough content. "
            * 20,  # 20 * 10 = 200+ chars
            "published_at": timezone.now(),
        }

        is_valid, reason = self.scraper.validate_article_quality(valid_article)
        self.assertTrue(is_valid)
        self.assertEqual(reason, "Valid article")

    def test_validate_article_quality_invalid_title(self):
        """Test article quality validation with invalid title."""
        invalid_article = {
            "title": "Short",  # Too short
            "content": "This is a test article with enough content. " * 20,
            "published_at": timezone.now(),
        }

        is_valid, reason = self.scraper.validate_article_quality(invalid_article)
        self.assertFalse(is_valid)
        self.assertEqual(reason, "Title too short or missing")

    def test_validate_article_quality_invalid_content(self):
        """Test article quality validation with invalid content."""
        invalid_article = {
            "title": "Valid Article Title",
            "content": "Too short",  # Not enough words
            "published_at": timezone.now(),
        }

        is_valid, reason = self.scraper.validate_article_quality(invalid_article)
        self.assertFalse(is_valid)
        self.assertIn("Content too short", reason)

    def test_validate_article_quality_future_date(self):
        """Test article quality validation with future publish date."""
        future_article = {
            "title": "Valid Article Title",
            "content": "This is a test article with enough content. " * 20,
            "published_at": timezone.now() + timedelta(days=1),  # Future date
        }

        is_valid, reason = self.scraper.validate_article_quality(future_article)
        self.assertFalse(is_valid)
        self.assertEqual(reason, "Publish date in future")

    @patch("newsflow.scrapers.services.NewspaperArticle")
    def test_scrape_article_success(self, mock_newspaper):
        """Test successful article scraping."""
        # Mock newspaper article
        mock_article = Mock()
        mock_article.download = Mock()
        mock_article.parse = Mock()
        mock_article.nlp = Mock()
        mock_article.title = "Test Article Title"
        mock_article.text = "This is test article content. " * 20
        mock_article.summary = "Test summary"
        mock_article.authors = ["John Doe"]
        mock_article.publish_date = datetime.now()
        mock_article.top_image = "https://example.com/image.jpg"
        mock_article.keywords = ["test", "article"]

        mock_newspaper.return_value = mock_article

        # Test scraping
        result = self.scraper.scrape_article("https://example.com/test-article")

        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "Test Article Title")
        self.assertIn("This is test article content", result["content"])
        self.assertEqual(result["author"], "John Doe")

    @patch("newsflow.scrapers.services.NewspaperArticle")
    def test_scrape_article_failure(self, mock_newspaper):
        """Test article scraping failure."""
        # Mock newspaper article that throws exception
        mock_article = Mock()
        mock_article.download.side_effect = Exception("Download failed")
        mock_newspaper.return_value = mock_article

        # Test scraping
        result = self.scraper.scrape_article("https://example.com/failing-article")

        self.assertIsNone(result)

    @patch("newsflow.scrapers.services.feedparser")
    def test_scrape_rss_feed_success(self, mock_feedparser):
        """Test successful RSS feed scraping."""
        # Mock feedparser response
        mock_feed = Mock()
        mock_feed.bozo = False
        mock_feed.entries = [
            Mock(
                link="https://example.com/article1",
                title="RSS Article 1",
                summary="Article summary",
                published_parsed=(2023, 10, 1, 12, 0, 0, 0, 0, 0),
            ),
        ]
        mock_feedparser.parse.return_value = mock_feed

        # Mock the scrape_article method to return valid data
        with patch.object(self.scraper, "scrape_article") as mock_scrape:
            mock_scrape.return_value = {
                "title": "RSS Article 1",
                "content": "Article content " * 30,  # Enough content
                "summary": "Article summary",
                "author": "Author",
                "published_at": timezone.now(),
                "top_image": "",
                "keywords": ["test"],
                "read_time": 2,
            }

            # Mock article quality validation
            with patch.object(
                self.scraper,
                "validate_article_quality",
            ) as mock_validate:
                mock_validate.return_value = (True, "Valid article")

                # Mock saving article
                with patch.object(self.scraper, "_save_article") as mock_save:
                    mock_save.return_value = Mock()

                    stats = self.scraper.scrape_rss_feed(self.news_source.id)

        self.assertEqual(stats["success"], 1)
        self.assertEqual(stats["failed"], 0)
        self.assertEqual(stats["duplicates"], 0)

    def test_scrape_rss_feed_no_rss_url(self):
        """Test RSS feed scraping with no RSS URL configured."""
        # Remove RSS feed URL
        self.news_source.rss_feed = ""
        self.news_source.save()

        stats = self.scraper.scrape_rss_feed(self.news_source.id)

        self.assertEqual(stats["success"], 0)
        self.assertEqual(stats["failed"], 0)
        self.assertEqual(stats["duplicates"], 0)

    def test_scrape_source_invalid_id(self):
        """Test scraping with invalid source ID."""
        stats = self.scraper.scrape_source(99999)  # Non-existent ID

        self.assertEqual(stats["success"], 0)
        self.assertEqual(stats["failed"], 0)
        self.assertEqual(stats["duplicates"], 0)

    def test_get_scraping_statistics_global(self):
        """Test getting global scraping statistics."""
        stats = self.scraper.get_scraping_statistics()

        self.assertIn("total_sources", stats)
        self.assertIn("sources_due_for_scraping", stats)
        self.assertIn("total_articles_today", stats)
        self.assertIn("avg_success_rate", stats)

    def test_get_scraping_statistics_source_specific(self):
        """Test getting statistics for specific source."""
        stats = self.scraper.get_scraping_statistics(self.news_source.id)

        self.assertIn("source_name", stats)
        self.assertEqual(stats["source_name"], self.news_source.name)
        self.assertIn("total_articles", stats)
        self.assertIn("success_rate", stats)

    def test_save_article_success(self):
        """Test successful article saving."""
        article_data = {
            "title": "Test Article",
            "url": "https://example.com/test",
            "content": "Test content",
            "summary": "Test summary",
            "author": "Test Author",
            "published_at": timezone.now(),
            "top_image": "https://example.com/image.jpg",
            "keywords": ["test", "article"],
            "read_time": 2,
        }

        article = self.scraper._save_article(article_data, self.news_source)

        self.assertIsNotNone(article)
        self.assertEqual(article.title, "Test Article")
        self.assertEqual(article.source, self.news_source)

    def test_save_article_with_category(self):
        """Test article saving with automatic categorization."""
        article_data = {
            "title": "Tech Article",
            "url": "https://example.com/tech",
            "content": "Tech content",
            "summary": "Tech summary",
            "author": "Tech Author",
            "published_at": timezone.now(),
            "top_image": "",
            "keywords": ["tech"],
            "read_time": 1,
        }

        article = self.scraper._save_article(article_data, self.news_source)

        self.assertIsNotNone(article)
        # Check if article was added to the technology category
        self.assertTrue(article.categories.filter(name=self.category.name).exists())

    @patch("newsflow.scrapers.services.time.sleep")
    def test_rate_limiting(self, mock_sleep):
        """Test that rate limiting is applied."""
        self.scraper._rate_limit_delay()
        mock_sleep.assert_called_once_with(self.scraper.rate_limit)


class NewsScraperServiceIntegrationTestCase(TestCase):
    """Integration tests for NewsScraperService with real data structures."""

    def setUp(self):
        """Set up test data."""
        self.news_source = NewsSource.objects.create(
            name="Integration Test Source",
            base_url="https://httpbin.org",  # Test service
            source_type="website",
            primary_category="general",
            country="US",
            language="en",
            is_active=True,
        )

        self.scraper = NewsScraperService()

    def test_end_to_end_article_processing(self):
        """Test complete article processing workflow."""
        # Create a complete article data structure
        article_data = {
            "title": "Integration Test Article",
            "url": "https://example.com/integration-test",
            "content": "This is an integration test article with sufficient content. "
            * 20,
            "summary": "Integration test summary",
            "author": "Integration Tester",
            "published_at": timezone.now(),
            "top_image": "https://example.com/test-image.jpg",
            "keywords": ["integration", "test", "article"],
            "read_time": 2,
        }

        # Validate quality
        is_valid, reason = self.scraper.validate_article_quality(article_data)
        self.assertTrue(is_valid)

        # Check for duplicates (should be False for new article)
        is_duplicate = self.scraper._is_duplicate_article(
            article_data["url"],
            article_data["title"],
            self.news_source,
        )
        self.assertFalse(is_duplicate)

        # Save article
        article = self.scraper._save_article(article_data, self.news_source)
        self.assertIsNotNone(article)

        # Check that duplicate detection works after saving
        is_duplicate_after = self.scraper._is_duplicate_article(
            article_data["url"],
            article_data["title"],
            self.news_source,
        )
        self.assertTrue(is_duplicate_after)
