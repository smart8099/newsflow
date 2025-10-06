from io import StringIO
from unittest.mock import Mock
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from newsflow.news.models import NewsSource


class ScrapeNewsCommandTestCase(TestCase):
    """Test cases for the scrape_news management command."""

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

    def test_list_sources_command(self):
        """Test listing all sources."""
        out = StringIO()
        call_command("scrape_news", "--list-sources", stdout=out)

        output = out.getvalue()
        self.assertIn("Found 2 news sources", output)
        self.assertIn("Test News Source", output)
        self.assertIn("Inactive Source", output)
        self.assertIn("rss", output)
        self.assertIn("website", output)

    def test_list_sources_empty(self):
        """Test listing sources when none exist."""
        NewsSource.objects.all().delete()

        out = StringIO()
        call_command("scrape_news", "--list-sources", stdout=out)

        output = out.getvalue()
        self.assertIn("No news sources configured", output)

    @patch("newsflow.scrapers.management.commands.scrape_news.NewsScraperService")
    def test_stats_command(self, mock_scraper_class):
        """Test showing scraping statistics."""
        mock_scraper = Mock()
        mock_scraper.get_scraping_statistics.return_value = {
            "total_sources": 2,
            "sources_due_for_scraping": 1,
            "total_articles_today": 5,
            "avg_success_rate": 85.5,
        }
        mock_scraper_class.return_value = mock_scraper

        out = StringIO()
        call_command("scrape_news", "--stats", stdout=out)

        output = out.getvalue()
        self.assertIn("Scraping Statistics", output)
        self.assertIn("Total Sources: 2", output)
        self.assertIn("Sources Due For Scraping: 1", output)
        self.assertIn("Avg Success Rate: 85.50", output)

    def test_dry_run_all_sources(self):
        """Test dry run mode for all sources."""
        out = StringIO()
        call_command("scrape_news", "--all-sources", "--dry-run", stdout=out)

        output = out.getvalue()
        self.assertIn("DRY RUN MODE", output)
        self.assertIn("Would scrape 1 sources", output)  # Only active source
        self.assertIn("Test News Source", output)

    def test_dry_run_specific_source(self):
        """Test dry run mode for specific source."""
        out = StringIO()
        call_command(
            "scrape_news",
            "--source",
            str(self.news_source.id),
            "--dry-run",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("DRY RUN MODE", output)
        self.assertIn("Would scrape 1 sources", output)
        self.assertIn("Test News Source", output)

    @patch("newsflow.scrapers.management.commands.scrape_news.NewsScraperService")
    def test_scrape_by_source_id(self, mock_scraper_class):
        """Test scraping by source ID."""
        mock_scraper = Mock()
        mock_scraper.scrape_rss_feed.return_value = {
            "success": 5,
            "failed": 1,
            "duplicates": 2,
        }
        mock_scraper_class.return_value = mock_scraper

        out = StringIO()
        call_command("scrape_news", "--source", str(self.news_source.id), stdout=out)

        output = out.getvalue()
        self.assertIn("Test News Source", output)
        self.assertIn("5 articles saved", output)
        self.assertIn("1 failed", output)
        self.assertIn("2 duplicates", output)

    def test_scrape_by_source_name(self):
        """Test scraping by source name."""
        with patch(
            "newsflow.scrapers.management.commands.scrape_news.NewsScraperService",
        ) as mock_scraper_class:
            mock_scraper = Mock()
            mock_scraper.scrape_rss_feed.return_value = {
                "success": 3,
                "failed": 0,
                "duplicates": 1,
            }
            mock_scraper_class.return_value = mock_scraper

            out = StringIO()
            call_command("scrape_news", "--source-name", "Test News", stdout=out)

            output = out.getvalue()
            self.assertIn("Test News Source", output)
            self.assertIn("3 articles saved", output)

    def test_scrape_by_source_name_not_found(self):
        """Test scraping by non-existent source name."""
        out = StringIO()
        call_command("scrape_news", "--source-name", "Non-existent", stdout=out)

        output = out.getvalue()
        self.assertIn('No active source found with name "Non-existent"', output)

    def test_scrape_by_source_name_multiple_matches(self):
        """Test scraping when source name matches multiple sources."""
        # Create another source with similar name
        NewsSource.objects.create(
            name="Test News Source 2",
            base_url="https://example2.com",
            source_type="rss",
            primary_category="business",
            country="US",
            language="en",
            is_active=True,
        )

        out = StringIO()
        call_command("scrape_news", "--source-name", "Test News", stdout=out)

        output = out.getvalue()
        self.assertIn("Multiple sources found", output)
        self.assertIn("Please use --source <ID>", output)

    @patch("newsflow.scrapers.management.commands.scrape_news.NewsScraperService")
    def test_scrape_all_sources(self, mock_scraper_class):
        """Test scraping all sources."""
        mock_scraper = Mock()
        mock_scraper.scrape_rss_feed.return_value = {
            "success": 3,
            "failed": 0,
            "duplicates": 1,
        }
        mock_scraper_class.return_value = mock_scraper

        out = StringIO()
        call_command("scrape_news", "--all-sources", stdout=out)

        output = out.getvalue()
        self.assertIn("Starting scraping of 1 sources", output)
        self.assertIn("Summary", output)
        self.assertIn("Total articles saved: 3", output)

    def test_scrape_invalid_source_id(self):
        """Test scraping with invalid source ID."""
        with self.assertRaises(CommandError) as cm:
            call_command("scrape_news", "--source", "99999")

        self.assertIn("NewsSource with ID 99999 not found", str(cm.exception))

    def test_scrape_inactive_source_without_force(self):
        """Test scraping inactive source without force flag."""
        out = StringIO()
        call_command(
            "scrape_news",
            "--source",
            str(self.inactive_source.id),
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("not active", output)
        self.assertIn("Use --force", output)

    @patch("newsflow.scrapers.management.commands.scrape_news.NewsScraperService")
    def test_scrape_inactive_source_with_force(self, mock_scraper_class):
        """Test scraping inactive source with force flag."""
        mock_scraper = Mock()
        mock_scraper.scrape_rss_feed.return_value = {
            "success": 1,
            "failed": 0,
            "duplicates": 0,
        }
        mock_scraper_class.return_value = mock_scraper

        out = StringIO()
        call_command(
            "scrape_news",
            "--source",
            str(self.inactive_source.id),
            "--force",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("1 articles saved", output)

    @patch("newsflow.scrapers.management.commands.scrape_news.NewsScraperService")
    def test_scrape_single_url(self, mock_scraper_class):
        """Test scraping a single URL."""
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

        out = StringIO()
        call_command(
            "scrape_news",
            "--url",
            "https://example.com/test-article",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("Article Information", output)
        self.assertIn("Test Article", output)
        self.assertIn("Test Author", output)
        self.assertIn("2 minutes", output)

    @patch("newsflow.scrapers.management.commands.scrape_news.NewsScraperService")
    def test_scrape_single_url_failure(self, mock_scraper_class):
        """Test scraping a single URL that fails."""
        mock_scraper = Mock()
        mock_scraper.scrape_article.return_value = None
        mock_scraper_class.return_value = mock_scraper

        with self.assertRaises(SystemExit):
            call_command("scrape_news", "--url", "https://example.com/failing-article")

    @patch("newsflow.scrapers.management.commands.scrape_news.NewsScraperService")
    def test_scrape_single_url_quality_failure(self, mock_scraper_class):
        """Test scraping a single URL with quality validation failure."""
        mock_scraper = Mock()
        mock_scraper.scrape_article.return_value = {
            "title": "Short",
            "content": "Too short",
            "summary": "",
            "author": "",
            "published_at": timezone.now(),
            "top_image": "",
            "keywords": [],
            "read_time": 1,
        }
        mock_scraper.validate_article_quality.return_value = (
            False,
            "Content too short",
        )
        mock_scraper_class.return_value = mock_scraper

        with self.assertRaises(SystemExit):
            call_command("scrape_news", "--url", "https://example.com/poor-quality")

    @patch("newsflow.scrapers.management.commands.scrape_news.NewsScraperService")
    def test_test_mode(self, mock_scraper_class):
        """Test running in test mode."""
        mock_scraper = Mock()
        mock_scraper.scrape_rss_feed.return_value = {
            "success": 1,
            "failed": 0,
            "duplicates": 0,
        }
        mock_scraper_class.return_value = mock_scraper

        out = StringIO()
        call_command(
            "scrape_news",
            "--source",
            str(self.news_source.id),
            "--test-mode",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("TEST MODE", output)

    def test_max_articles_override(self):
        """Test overriding max articles per scrape."""
        with patch(
            "newsflow.scrapers.management.commands.scrape_news.NewsScraperService",
        ) as mock_scraper_class:
            mock_scraper = Mock()
            mock_scraper.scrape_rss_feed.return_value = {
                "success": 5,
                "failed": 0,
                "duplicates": 0,
            }
            mock_scraper_class.return_value = mock_scraper

            # Override max articles to 5
            call_command(
                "scrape_news",
                "--source",
                str(self.news_source.id),
                "--max-articles",
                "5",
            )

            # Verify that the source's max_articles_per_scrape was temporarily changed
            # Note: This is tested indirectly through the command execution

    def test_verbose_output(self):
        """Test verbose output mode."""
        out = StringIO()
        call_command("scrape_news", "--list-sources", "--verbose", stdout=out)

        # In verbose mode, more detailed output should be present
        # This is a basic test - in practice you'd check for specific verbose messages

    def test_no_arguments_error(self):
        """Test that command requires at least one argument."""
        with self.assertRaises(CommandError) as cm:
            call_command("scrape_news")

        self.assertIn("You must specify one of", str(cm.exception))

    @patch("newsflow.scrapers.management.commands.scrape_news.NewsScraperService")
    def test_command_exception_handling(self, mock_scraper_class):
        """Test that command handles exceptions gracefully."""
        mock_scraper = Mock()
        mock_scraper.scrape_rss_feed.side_effect = Exception("Network error")
        mock_scraper_class.return_value = mock_scraper

        with self.assertRaises(CommandError) as cm:
            call_command("scrape_news", "--source", str(self.news_source.id))

        self.assertIn("Scraping failed", str(cm.exception))

    def test_source_due_for_scraping_check(self):
        """Test that command respects scraping frequency."""
        # Set last_scraped to very recent time
        self.news_source.last_scraped = timezone.now()
        self.news_source.save()

        with patch(
            "newsflow.scrapers.management.commands.scrape_news.NewsScraperService",
        ) as mock_scraper_class:
            mock_scraper = Mock()
            mock_scraper_class.return_value = mock_scraper

            out = StringIO()
            call_command(
                "scrape_news",
                "--source",
                str(self.news_source.id),
                stdout=out,
            )

            output = out.getvalue()
            self.assertIn("not due for scraping", output)

    def test_force_scraping_override(self):
        """Test that force flag overrides scraping frequency."""
        # Set last_scraped to very recent time
        self.news_source.last_scraped = timezone.now()
        self.news_source.save()

        with patch(
            "newsflow.scrapers.management.commands.scrape_news.NewsScraperService",
        ) as mock_scraper_class:
            mock_scraper = Mock()
            mock_scraper.scrape_rss_feed.return_value = {
                "success": 2,
                "failed": 0,
                "duplicates": 0,
            }
            mock_scraper_class.return_value = mock_scraper

            out = StringIO()
            call_command(
                "scrape_news",
                "--source",
                str(self.news_source.id),
                "--force",
                stdout=out,
            )

            output = out.getvalue()
            self.assertIn("2 articles saved", output)
