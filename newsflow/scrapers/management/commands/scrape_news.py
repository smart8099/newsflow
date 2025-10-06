import logging
import sys

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Scrape news articles from configured sources"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=int,
            help="Scrape specific NewsSource by ID",
        )

        parser.add_argument(
            "--source-name",
            type=str,
            help="Scrape specific NewsSource by name",
        )

        parser.add_argument(
            "--all-sources",
            action="store_true",
            help="Scrape all active sources",
        )

        parser.add_argument(
            "--test-mode",
            action="store_true",
            help="Run in test mode (no database writes)",
        )

        parser.add_argument(
            "--max-articles",
            type=int,
            default=None,
            help="Maximum number of articles to scrape per source",
        )

        parser.add_argument(
            "--force",
            action="store_true",
            help="Force scraping even if not due based on frequency",
        )

        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Enable verbose output",
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be scraped without actually scraping",
        )

        parser.add_argument(
            "--url",
            type=str,
            help="Scrape a single article from URL",
        )

        parser.add_argument(
            "--list-sources",
            action="store_true",
            help="List all available news sources",
        )

        parser.add_argument(
            "--stats",
            action="store_true",
            help="Show scraping statistics",
        )

    def handle(self, *args, **options):
        """Main command handler."""
        if options["verbose"]:
            logging.basicConfig(level=logging.DEBUG)
            self.verbosity = 2
        else:
            self.verbosity = 1

        # Handle different command modes
        if options["list_sources"]:
            self.list_sources()
            return

        if options["stats"]:
            self.show_statistics()
            return

        if options["url"]:
            self.scrape_single_url(options["url"], options)
            return

        if options["dry_run"]:
            self.dry_run(options)
            return

        # Main scraping logic
        if not any([options["source"], options["source_name"], options["all_sources"]]):
            raise CommandError(
                "You must specify one of: --source, --source-name, --all-sources, "
                "--url, --list-sources, --stats, or --dry-run",
            )

        try:
            if options["source"]:
                self.scrape_source_by_id(options["source"], options)
            elif options["source_name"]:
                self.scrape_source_by_name(options["source_name"], options)
            elif options["all_sources"]:
                self.scrape_all_sources(options)

        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            raise CommandError(f"Scraping failed: {e}")

    def list_sources(self):
        """List all available news sources."""
        from newsflow.news.models import NewsSource

        sources = NewsSource.objects.all().order_by("name")

        if not sources:
            self.stdout.write(self.style.WARNING("No news sources configured."))
            return

        self.stdout.write(
            self.style.SUCCESS(f"\nFound {sources.count()} news sources:\n"),
        )

        # Header
        self.stdout.write(
            f"{'ID':<4} {'Name':<30} {'Type':<8} {'Active':<6} {'Last Scraped':<20} {'Articles':<8}",
        )
        self.stdout.write("-" * 80)

        for source in sources:
            last_scraped = (
                source.last_scraped.strftime("%Y-%m-%d %H:%M")
                if source.last_scraped
                else "Never"
            )
            active_status = "Yes" if source.is_active else "No"

            self.stdout.write(
                f"{source.id:<4} {source.name[:29]:<30} {source.source_type:<8} "
                f"{active_status:<6} {last_scraped:<20} {source.total_articles_scraped:<8}",
            )

    def show_statistics(self):
        """Show scraping statistics."""
        from newsflow.news.models import NewsSource
        from newsflow.scrapers.services import NewsScraperService

        scraper = NewsScraperService()
        stats = scraper.get_scraping_statistics()

        self.stdout.write(self.style.SUCCESS("\n=== Scraping Statistics ===\n"))

        for key, value in stats.items():
            if isinstance(value, float):
                self.stdout.write(f"{key.replace('_', ' ').title()}: {value:.2f}")
            else:
                self.stdout.write(f"{key.replace('_', ' ').title()}: {value}")

        # Show sources due for scraping
        due_sources = NewsSource.objects.needs_scraping()
        if due_sources:
            self.stdout.write(f"\n{len(due_sources)} sources due for scraping:")
            for source in due_sources[:10]:  # Show first 10
                next_scrape = source.next_scrape_time.strftime("%Y-%m-%d %H:%M")
                self.stdout.write(f"  - {source.name} (due: {next_scrape})")
            if len(due_sources) > 10:
                self.stdout.write(f"  ... and {len(due_sources) - 10} more")

    def dry_run(self, options):
        """Show what would be scraped without actually scraping."""
        from newsflow.news.models import NewsSource

        self.stdout.write(self.style.WARNING("=== DRY RUN MODE ===\n"))

        if options["all_sources"]:
            sources = NewsSource.objects.active()
            if not options["force"]:
                sources = NewsSource.objects.needs_scraping()
        elif options["source"]:
            sources = NewsSource.objects.filter(id=options["source"], is_active=True)
        elif options["source_name"]:
            sources = NewsSource.objects.filter(
                name__icontains=options["source_name"],
                is_active=True,
            )
        else:
            sources = NewsSource.objects.none()

        if not sources:
            self.stdout.write(self.style.WARNING("No sources would be scraped."))
            return

        self.stdout.write(f"Would scrape {sources.count()} sources:")
        for source in sources:
            due_status = "✓" if source.is_due_for_scraping else "✗"
            max_articles = options.get("max_articles") or source.max_articles_per_scrape
            self.stdout.write(
                f"  {due_status} {source.name} ({source.source_type}) - "
                f"max {max_articles} articles",
            )

    def scrape_source_by_id(self, source_id: int, options: dict):
        """Scrape a specific source by ID."""
        from newsflow.news.models import NewsSource

        try:
            source = NewsSource.objects.get(id=source_id)
        except NewsSource.DoesNotExist:
            raise CommandError(f"NewsSource with ID {source_id} not found")

        if not source.is_active:
            self.stdout.write(
                self.style.WARNING(
                    f'Source "{source.name}" is not active. Use --force to scrape anyway.',
                ),
            )
            if not options["force"]:
                return

        self.scrape_source(source, options)

    def scrape_source_by_name(self, source_name: str, options: dict):
        """Scrape a specific source by name."""
        from newsflow.news.models import NewsSource

        try:
            source = NewsSource.objects.get(name__icontains=source_name, is_active=True)
        except NewsSource.DoesNotExist:
            # Try to find similar names
            similar_sources = NewsSource.objects.filter(name__icontains=source_name)
            if similar_sources:
                self.stdout.write(
                    self.style.ERROR(
                        f'No active source found with name "{source_name}".',
                    ),
                )
                self.stdout.write("Did you mean one of these?")
                for src in similar_sources[:5]:
                    status = "active" if src.is_active else "inactive"
                    self.stdout.write(f"  - {src.name} (ID: {src.id}, {status})")
            else:
                self.stdout.write(
                    self.style.ERROR(f'No source found with name "{source_name}".'),
                )
            return
        except NewsSource.MultipleObjectsReturned:
            sources = NewsSource.objects.filter(
                name__icontains=source_name,
                is_active=True,
            )
            self.stdout.write(
                self.style.ERROR(f'Multiple sources found with name "{source_name}":'),
            )
            for src in sources:
                self.stdout.write(f"  - {src.name} (ID: {src.id})")
            self.stdout.write("Please use --source <ID> to specify exactly which one.")
            return

        self.scrape_source(source, options)

    def scrape_all_sources(self, options: dict):
        """Scrape all active sources."""
        from newsflow.news.models import NewsSource

        if options["force"]:
            sources = NewsSource.objects.active()
        else:
            sources = NewsSource.objects.needs_scraping()

        if not sources:
            self.stdout.write(self.style.WARNING("No sources are due for scraping."))
            return

        total_sources = len(sources)
        self.stdout.write(
            self.style.SUCCESS(f"Starting scraping of {total_sources} sources...\n"),
        )

        total_stats = {"success": 0, "failed": 0, "duplicates": 0}

        for i, source in enumerate(sources, 1):
            self.stdout.write(f"[{i}/{total_sources}] Scraping {source.name}...")

            try:
                stats = self.scrape_source(source, options, show_progress=False)

                # Aggregate stats
                total_stats["success"] += stats["success"]
                total_stats["failed"] += stats["failed"]
                total_stats["duplicates"] += stats["duplicates"]

                self.stdout.write(
                    f"  ✓ {stats['success']} articles, {stats['failed']} failed, "
                    f"{stats['duplicates']} duplicates",
                )

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Failed: {e}"))
                continue

        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f"\n=== Summary ===\n"
                f"Sources processed: {total_sources}\n"
                f"Total articles saved: {total_stats['success']}\n"
                f"Total failed: {total_stats['failed']}\n"
                f"Total duplicates: {total_stats['duplicates']}",
            ),
        )

    def scrape_source(self, source, options: dict, show_progress: bool = True) -> dict:
        """Scrape a single source with progress reporting."""
        if show_progress:
            self.stdout.write(f"Scraping source: {source.name} ({source.source_type})")

        # Check if scraping is due
        if not options["force"] and not source.is_due_for_scraping:
            next_scrape = source.next_scrape_time.strftime("%Y-%m-%d %H:%M")
            if show_progress:
                self.stdout.write(
                    self.style.WARNING(
                        f"Source not due for scraping until {next_scrape}. Use --force to override.",
                    ),
                )
            return {"success": 0, "failed": 0, "duplicates": 0}

        # Override max articles if specified
        original_max_articles = source.max_articles_per_scrape
        if options["max_articles"]:
            source.max_articles_per_scrape = options["max_articles"]

        from newsflow.scrapers.services import NewsScraperService

        scraper = NewsScraperService()

        try:
            start_time = timezone.now()

            if options["test_mode"]:
                # In test mode, just validate the source without saving
                if show_progress:
                    self.stdout.write(
                        self.style.WARNING("TEST MODE: No articles will be saved"),
                    )

                # Try to fetch one article to test connectivity
                if source.source_type == "rss" and source.rss_feed:
                    import feedparser

                    feed = feedparser.parse(source.rss_feed)
                    if feed.entries:
                        test_url = feed.entries[0].link
                        article_data = scraper.scrape_article(test_url, source)
                        if article_data:
                            stats = {"success": 1, "failed": 0, "duplicates": 0}
                        else:
                            stats = {"success": 0, "failed": 1, "duplicates": 0}
                    else:
                        stats = {"success": 0, "failed": 1, "duplicates": 0}
                else:
                    # Test website scraping
                    try:
                        from newspaper import build

                        config = scraper._get_newspaper_config(source)
                        news_source = build(source.base_url, config=config)
                        if news_source.articles:
                            stats = {"success": 1, "failed": 0, "duplicates": 0}
                        else:
                            stats = {"success": 0, "failed": 1, "duplicates": 0}
                    except Exception:
                        stats = {"success": 0, "failed": 1, "duplicates": 0}
            # Actual scraping
            elif source.source_type == "rss" and source.rss_feed:
                stats = scraper.scrape_rss_feed(source.id)
            else:
                stats = scraper.scrape_source(source.id)

            end_time = timezone.now()
            duration = (end_time - start_time).total_seconds()

            if show_progress:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Completed in {duration:.2f}s: "
                        f"{stats['success']} articles saved, "
                        f"{stats['failed']} failed, "
                        f"{stats['duplicates']} duplicates",
                    ),
                )

            return stats

        except Exception as e:
            if show_progress:
                self.stdout.write(
                    self.style.ERROR(f"Failed to scrape {source.name}: {e}"),
                )
            raise
        finally:
            # Restore original max articles
            if options["max_articles"]:
                source.max_articles_per_scrape = original_max_articles

    def scrape_single_url(self, url: str, options: dict):
        """Scrape a single article from URL."""
        from newsflow.scrapers.services import NewsScraperService

        self.stdout.write(f"Scraping single article: {url}")

        scraper = NewsScraperService()

        try:
            article_data = scraper.scrape_article(url)

            if not article_data:
                self.stdout.write(self.style.ERROR("Failed to scrape article"))
                return

            # Validate quality
            is_valid, reason = scraper.validate_article_quality(article_data)

            if not is_valid:
                self.stdout.write(
                    self.style.ERROR(f"Article quality validation failed: {reason}"),
                )
                if not options["force"]:
                    return

            # Display article info
            self.stdout.write(self.style.SUCCESS("\n=== Article Information ==="))
            self.stdout.write(f"Title: {article_data['title']}")
            self.stdout.write(f"Author: {article_data['author'] or 'Unknown'}")
            self.stdout.write(f"Published: {article_data['published_at']}")
            self.stdout.write(f"Read time: {article_data['read_time']} minutes")
            self.stdout.write(
                f"Content length: {len(article_data['content'])} characters",
            )
            self.stdout.write(f"Keywords: {', '.join(article_data['keywords'][:5])}")

            if article_data["summary"]:
                self.stdout.write(f"Summary: {article_data['summary'][:200]}...")

            if options["test_mode"]:
                self.stdout.write(
                    self.style.WARNING("\nTEST MODE: Article not saved to database"),
                )
            else:
                self.stdout.write(self.style.SUCCESS("\nArticle scraped successfully!"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to scrape article: {e}"))
            sys.exit(1)
