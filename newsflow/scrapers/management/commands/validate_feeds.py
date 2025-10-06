import logging

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from newsflow.scrapers.utils import RSSValidator

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Validate RSS feeds and auto-detect feeds for news sources"

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            type=str,
            help="Validate a specific RSS feed URL",
        )

        parser.add_argument(
            "--website",
            type=str,
            help="Discover RSS feeds for a website",
        )

        parser.add_argument(
            "--validate-all",
            action="store_true",
            help="Validate all existing news source RSS feeds",
        )

        parser.add_argument(
            "--auto-detect",
            action="store_true",
            help="Auto-detect RSS feeds for sources without feeds",
        )

        parser.add_argument(
            "--fix-invalid",
            action="store_true",
            help="Try to fix invalid RSS feeds by auto-detection",
        )

        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Enable verbose output",
        )

    def handle(self, *args, **options):
        """Main command handler."""
        if options["verbose"]:
            logging.basicConfig(level=logging.DEBUG)

        validator = RSSValidator()

        if options["url"]:
            self.validate_single_feed(validator, options["url"])
        elif options["website"]:
            self.discover_feeds_for_website(validator, options["website"])
        elif options["validate_all"]:
            self.validate_all_sources(validator)
        elif options["auto_detect"]:
            self.auto_detect_feeds(validator)
        elif options["fix_invalid"]:
            self.fix_invalid_feeds(validator)
        else:
            raise CommandError(
                "You must specify one of: --url, --website, --validate-all, --auto-detect, or --fix-invalid",
            )

    def validate_single_feed(self, validator: RSSValidator, feed_url: str):
        """Validate a single RSS feed URL."""
        self.stdout.write(f"Validating RSS feed: {feed_url}")

        is_valid, reason, feed_info = validator.validate_rss_feed(feed_url)

        if is_valid:
            self.stdout.write(self.style.SUCCESS(f"✓ Valid RSS feed: {reason}"))
            self.stdout.write(f"Title: {feed_info.get('title', 'N/A')}")
            self.stdout.write(
                f"Description: {feed_info.get('description', 'N/A')[:100]}...",
            )
            self.stdout.write(f"Entries: {feed_info.get('entry_count', 0)}")
            self.stdout.write(f"Language: {feed_info.get('language', 'N/A')}")
            self.stdout.write(f"Last Updated: {feed_info.get('last_updated', 'N/A')}")
            self.stdout.write(
                f"Validation Score: {feed_info.get('validation_score', 0):.1f}%",
            )
        else:
            self.stdout.write(self.style.ERROR(f"✗ Invalid RSS feed: {reason}"))

    def discover_feeds_for_website(self, validator: RSSValidator, website_url: str):
        """Discover RSS feeds for a website."""
        self.stdout.write(f"Discovering RSS feeds for: {website_url}")

        discovered_feeds = validator.discover_rss_feeds(website_url)

        if not discovered_feeds:
            self.stdout.write(self.style.WARNING("No RSS feeds discovered."))
            return

        self.stdout.write(
            f"\\nDiscovered {len(discovered_feeds)} potential RSS feeds:\\n",
        )

        for i, feed in enumerate(discovered_feeds, 1):
            status = (
                "✓ Valid"
                if feed["is_valid"]
                else f"✗ Invalid ({feed['validation_reason']})"
            )
            entry_count = feed.get("feed_info", {}).get("entry_count", 0)

            self.stdout.write(
                f"{i}. {feed['url']} - {status} "
                f"({entry_count} entries, {feed['discovery_method']})",
            )

        # Show best feed
        valid_feeds = [feed for feed in discovered_feeds if feed["is_valid"]]
        if valid_feeds:
            best_feed = validator.auto_detect_best_feed(website_url)
            if best_feed:
                self.stdout.write(
                    self.style.SUCCESS(f"\\nRecommended: {best_feed['url']}"),
                )

    def validate_all_sources(self, validator: RSSValidator):
        """Validate RSS feeds for all existing news sources."""
        from newsflow.news.models import NewsSource

        sources = NewsSource.objects.filter(rss_feed__isnull=False).exclude(rss_feed="")

        if not sources:
            self.stdout.write(
                self.style.WARNING("No news sources with RSS feeds found."),
            )
            return

        self.stdout.write(f"Validating {sources.count()} RSS feeds...\\n")

        valid_count = 0
        invalid_count = 0

        for source in sources:
            self.stdout.write(f"Validating {source.name}: {source.rss_feed}")

            is_valid, reason, feed_info = validator.validate_rss_feed(source.rss_feed)

            if is_valid:
                valid_count += 1
                entry_count = feed_info.get("entry_count", 0)
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ Valid ({entry_count} entries)"),
                )
            else:
                invalid_count += 1
                self.stdout.write(
                    self.style.ERROR(f"  ✗ Invalid: {reason}"),
                )

        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f"\\n=== Summary ===\\n"
                f"Valid feeds: {valid_count}\\n"
                f"Invalid feeds: {invalid_count}\\n"
                f"Total: {valid_count + invalid_count}",
            ),
        )

    def auto_detect_feeds(self, validator: RSSValidator):
        """Auto-detect RSS feeds for sources without feeds."""
        from django.db import models

        from newsflow.news.models import NewsSource

        sources = NewsSource.objects.filter(
            models.Q(rss_feed__isnull=True) | models.Q(rss_feed=""),
        )

        if not sources:
            self.stdout.write(
                self.style.WARNING("No news sources without RSS feeds found."),
            )
            return

        self.stdout.write(
            f"Auto-detecting RSS feeds for {sources.count()} sources...\\n",
        )

        detected_count = 0

        for source in sources:
            self.stdout.write(f"Checking {source.name}: {source.base_url}")

            best_feed = validator.auto_detect_best_feed(source.base_url)

            if best_feed and best_feed["is_valid"]:
                detected_count += 1
                entry_count = best_feed.get("feed_info", {}).get("entry_count", 0)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ Found RSS feed: {best_feed['url']} ({entry_count} entries)",
                    ),
                )

                # Ask if user wants to update the source
                response = input(f"Update {source.name} with this RSS feed? [y/N]: ")
                if response.lower() in ["y", "yes"]:
                    source.rss_feed = best_feed["url"]
                    source.source_type = "rss"
                    source.save()
                    self.stdout.write(self.style.SUCCESS(f"  Updated {source.name}"))
            else:
                self.stdout.write(
                    self.style.WARNING("  - No valid RSS feed found"),
                )

        self.stdout.write(
            self.style.SUCCESS(f"\\nDetected RSS feeds for {detected_count} sources"),
        )

    def fix_invalid_feeds(self, validator: RSSValidator):
        """Try to fix invalid RSS feeds by auto-detection."""
        from newsflow.news.models import NewsSource

        sources = NewsSource.objects.filter(rss_feed__isnull=False).exclude(rss_feed="")

        self.stdout.write(f"Checking {sources.count()} RSS feeds for issues...\\n")

        fixed_count = 0

        for source in sources:
            is_valid, reason, feed_info = validator.validate_rss_feed(source.rss_feed)

            if not is_valid:
                self.stdout.write(f"{source.name}: Invalid RSS feed ({reason})")

                # Try to auto-detect better feed
                best_feed = validator.auto_detect_best_feed(source.base_url)

                if (
                    best_feed
                    and best_feed["is_valid"]
                    and best_feed["url"] != source.rss_feed
                ):
                    entry_count = best_feed.get("feed_info", {}).get("entry_count", 0)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  ✓ Found alternative: {best_feed['url']} ({entry_count} entries)",
                        ),
                    )

                    # Ask if user wants to update
                    response = input(f"Replace RSS feed for {source.name}? [y/N]: ")
                    if response.lower() in ["y", "yes"]:
                        source.rss_feed = best_feed["url"]
                        source.save()
                        fixed_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(f"  Updated {source.name}"),
                        )
                else:
                    self.stdout.write(
                        self.style.WARNING("  - No better RSS feed found"),
                    )

        self.stdout.write(
            self.style.SUCCESS(f"\\nFixed {fixed_count} RSS feeds"),
        )
