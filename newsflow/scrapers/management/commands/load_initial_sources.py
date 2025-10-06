import logging

from django.core.management.base import BaseCommand
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Load initial news sources for NewsFlow"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear-existing",
            action="store_true",
            help="Clear all existing news sources before loading new ones",
        )

        parser.add_argument(
            "--category",
            type=str,
            choices=[
                "tech",
                "world",
                "business",
                "sports",
                "science",
                "politics",
                "health",
                "entertainment",
                "all",
            ],
            default="all",
            help="Load sources only for specific category",
        )

        parser.add_argument(
            "--country",
            type=str,
            help="Filter sources by country code (e.g., US, UK, CA)",
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be loaded without actually creating sources",
        )

    def handle(self, *args, **options):
        """Main command handler."""
        if options["clear_existing"] and not options["dry_run"]:
            self.clear_existing_sources()

        # Get sources to load
        sources_to_load = self.get_initial_sources()

        # Filter by category if specified
        if options["category"] != "all":
            sources_to_load = [
                source
                for source in sources_to_load
                if source["primary_category"].lower() == options["category"].lower()
            ]

        # Filter by country if specified
        if options["country"]:
            sources_to_load = [
                source
                for source in sources_to_load
                if source["country"].upper() == options["country"].upper()
            ]

        if options["dry_run"]:
            self.show_dry_run(sources_to_load)
            return

        # Load sources
        self.load_sources(sources_to_load)

    def clear_existing_sources(self):
        """Clear all existing news sources."""
        from newsflow.news.models import NewsSource

        count = NewsSource.objects.count()
        if count > 0:
            self.stdout.write(
                self.style.WARNING(f"Clearing {count} existing news sources..."),
            )
            NewsSource.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Existing sources cleared."))
        else:
            self.stdout.write("No existing sources to clear.")

    def show_dry_run(self, sources: list[dict]):
        """Show what would be loaded in dry run mode."""
        self.stdout.write(self.style.WARNING("=== DRY RUN MODE ==="))
        self.stdout.write(f"Would load {len(sources)} news sources:\n")

        # Group by category
        by_category = {}
        for source in sources:
            category = source["primary_category"]
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(source)

        for category, category_sources in by_category.items():
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n{category.upper()} ({len(category_sources)} sources):",
                ),
            )
            for source in category_sources:
                rss_status = "RSS" if source.get("rss_feed") else "Web"
                self.stdout.write(
                    f"  • {source['name']} ({source['country']}) - {rss_status}",
                )

    def load_sources(self, sources: list[dict]):
        """Load news sources into the database."""
        from newsflow.news.models import Category
        from newsflow.news.models import NewsSource

        self.stdout.write(f"Loading {len(sources)} news sources...\n")

        created_count = 0
        updated_count = 0
        error_count = 0

        # Create categories first
        categories_created = set()

        for source_data in sources:
            try:
                with transaction.atomic():
                    # Create category if it doesn't exist
                    category_name = source_data["primary_category"]
                    if category_name not in categories_created:
                        category, created = Category.objects.get_or_create(
                            name=category_name,
                            defaults={
                                "description": f"{category_name.title()} news and articles",
                                "is_active": True,
                            },
                        )
                        if created:
                            categories_created.add(category_name)
                            self.stdout.write(f"Created category: {category_name}")

                    # Create or update news source
                    source, created = NewsSource.objects.update_or_create(
                        name=source_data["name"],
                        defaults={
                            "base_url": source_data["base_url"],
                            "rss_feed": source_data.get("rss_feed", ""),
                            "description": source_data.get("description", ""),
                            "source_type": source_data.get(
                                "source_type",
                                "rss" if source_data.get("rss_feed") else "website",
                            ),
                            "primary_category": source_data["primary_category"],
                            "country": source_data["country"],
                            "language": source_data.get("language", "en"),
                            "credibility_score": source_data.get(
                                "credibility_score",
                                80,
                            ),
                            "bias_rating": source_data.get("bias_rating", "center"),
                            "scrape_frequency": source_data.get("scrape_frequency", 60),
                            "max_articles_per_scrape": source_data.get(
                                "max_articles_per_scrape",
                                20,
                            ),
                            "is_active": True,
                        },
                    )

                    if created:
                        created_count += 1
                        self.stdout.write(f"✓ Created: {source.name}")
                    else:
                        updated_count += 1
                        self.stdout.write(f"↻ Updated: {source.name}")

            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f"✗ Failed to create {source_data['name']}: {e}"),
                )

        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f"\n=== Summary ===\n"
                f"Created: {created_count} sources\n"
                f"Updated: {updated_count} sources\n"
                f"Errors: {error_count} sources\n"
                f"Categories created: {len(categories_created)}",
            ),
        )

    def get_initial_sources(self) -> list[dict]:
        """Get the list of initial news sources to load."""
        return [
            # Technology News
            {
                "name": "TechCrunch",
                "base_url": "https://techcrunch.com",
                "rss_feed": "https://techcrunch.com/feed/",
                "description": "Leading technology news and startup coverage",
                "primary_category": "Technology",
                "country": "US",
                "language": "en",
                "credibility_score": 85,
                "bias_rating": "left",
                "scrape_frequency": 30,
                "max_articles_per_scrape": 25,
            },
            {
                "name": "The Verge",
                "base_url": "https://www.theverge.com",
                "rss_feed": "https://www.theverge.com/rss/index.xml",
                "description": "Technology, science, art, and culture",
                "primary_category": "Technology",
                "country": "US",
                "language": "en",
                "credibility_score": 82,
                "bias_rating": "left",
                "scrape_frequency": 45,
                "max_articles_per_scrape": 20,
            },
            {
                "name": "Ars Technica",
                "base_url": "https://arstechnica.com",
                "rss_feed": "https://feeds.arstechnica.com/arstechnica/index",
                "description": "In-depth technology news and analysis",
                "primary_category": "Technology",
                "country": "US",
                "language": "en",
                "credibility_score": 90,
                "bias_rating": "center",
                "scrape_frequency": 60,
                "max_articles_per_scrape": 15,
            },
            {
                "name": "Wired",
                "base_url": "https://www.wired.com",
                "rss_feed": "https://www.wired.com/feed/rss",
                "description": "Technology, science, culture, and their impact",
                "primary_category": "Technology",
                "country": "US",
                "language": "en",
                "credibility_score": 88,
                "bias_rating": "left",
                "scrape_frequency": 90,
                "max_articles_per_scrape": 15,
            },
            {
                "name": "Hacker News",
                "base_url": "https://news.ycombinator.com",
                "rss_feed": "https://hnrss.org/frontpage",
                "description": "Startup and technology community news",
                "primary_category": "Technology",
                "country": "US",
                "language": "en",
                "credibility_score": 80,
                "bias_rating": "center",
                "scrape_frequency": 60,
                "max_articles_per_scrape": 30,
            },
            # World News
            {
                "name": "BBC News",
                "base_url": "https://www.bbc.com/news",
                "rss_feed": "https://feeds.bbci.co.uk/news/rss.xml",
                "description": "International news and current affairs",
                "primary_category": "World",
                "country": "UK",
                "language": "en",
                "credibility_score": 92,
                "bias_rating": "center",
                "scrape_frequency": 30,
                "max_articles_per_scrape": 25,
            },
            {
                "name": "Reuters",
                "base_url": "https://www.reuters.com",
                "rss_feed": "https://www.reutersagency.com/feed/?best-topics=tech",
                "description": "International news agency",
                "primary_category": "World",
                "country": "UK",
                "language": "en",
                "credibility_score": 95,
                "bias_rating": "center",
                "scrape_frequency": 30,
                "max_articles_per_scrape": 30,
            },
            {
                "name": "Associated Press",
                "base_url": "https://apnews.com",
                "rss_feed": "https://apnews.com/rss",
                "description": "Global news cooperative",
                "primary_category": "World",
                "country": "US",
                "language": "en",
                "credibility_score": 94,
                "bias_rating": "center",
                "scrape_frequency": 30,
                "max_articles_per_scrape": 25,
            },
            {
                "name": "CNN International",
                "base_url": "https://edition.cnn.com",
                "rss_feed": "http://rss.cnn.com/rss/edition.rss",
                "description": "Global news network",
                "primary_category": "World",
                "country": "US",
                "language": "en",
                "credibility_score": 75,
                "bias_rating": "left",
                "scrape_frequency": 45,
                "max_articles_per_scrape": 20,
            },
            {
                "name": "Al Jazeera English",
                "base_url": "https://www.aljazeera.com",
                "rss_feed": "https://www.aljazeera.com/xml/rss/all.xml",
                "description": "Middle Eastern perspective on global news",
                "primary_category": "World",
                "country": "QA",
                "language": "en",
                "credibility_score": 78,
                "bias_rating": "left",
                "scrape_frequency": 60,
                "max_articles_per_scrape": 20,
            },
            # Business News
            {
                "name": "Financial Times",
                "base_url": "https://www.ft.com",
                "rss_feed": "https://www.ft.com/rss/home",
                "description": "Global business and financial news",
                "primary_category": "Business",
                "country": "UK",
                "language": "en",
                "credibility_score": 92,
                "bias_rating": "center",
                "scrape_frequency": 60,
                "max_articles_per_scrape": 15,
            },
            {
                "name": "Bloomberg",
                "base_url": "https://www.bloomberg.com",
                "rss_feed": "https://feeds.bloomberg.com/markets/news.rss",
                "description": "Business, financial, and market news",
                "primary_category": "Business",
                "country": "US",
                "language": "en",
                "credibility_score": 90,
                "bias_rating": "center",
                "scrape_frequency": 45,
                "max_articles_per_scrape": 20,
            },
            {
                "name": "The Wall Street Journal",
                "base_url": "https://www.wsj.com",
                "rss_feed": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
                "description": "Business and financial journalism",
                "primary_category": "Business",
                "country": "US",
                "language": "en",
                "credibility_score": 91,
                "bias_rating": "right",
                "scrape_frequency": 60,
                "max_articles_per_scrape": 15,
            },
            {
                "name": "Forbes",
                "base_url": "https://www.forbes.com",
                "rss_feed": "https://www.forbes.com/real-time/feed2/",
                "description": "Business, investing, and entrepreneurship",
                "primary_category": "Business",
                "country": "US",
                "language": "en",
                "credibility_score": 78,
                "bias_rating": "right",
                "scrape_frequency": 90,
                "max_articles_per_scrape": 20,
            },
            # Science News
            {
                "name": "Nature News",
                "base_url": "https://www.nature.com/news",
                "rss_feed": "https://www.nature.com/news.rss",
                "description": "Scientific research and discoveries",
                "primary_category": "Science",
                "country": "UK",
                "language": "en",
                "credibility_score": 95,
                "bias_rating": "center",
                "scrape_frequency": 120,
                "max_articles_per_scrape": 10,
            },
            {
                "name": "Science Magazine",
                "base_url": "https://www.science.org/news",
                "rss_feed": "https://www.science.org/rss/news_current.xml",
                "description": "Peer-reviewed scientific news",
                "primary_category": "Science",
                "country": "US",
                "language": "en",
                "credibility_score": 96,
                "bias_rating": "center",
                "scrape_frequency": 120,
                "max_articles_per_scrape": 10,
            },
            {
                "name": "Scientific American",
                "base_url": "https://www.scientificamerican.com",
                "rss_feed": "https://rss.sciam.com/ScientificAmerican-Global",
                "description": "Science news and analysis for general audience",
                "primary_category": "Science",
                "country": "US",
                "language": "en",
                "credibility_score": 88,
                "bias_rating": "center",
                "scrape_frequency": 180,
                "max_articles_per_scrape": 15,
            },
            {
                "name": "New Scientist",
                "base_url": "https://www.newscientist.com",
                "rss_feed": "https://www.newscientist.com/feed/home/",
                "description": "Global science news and insights",
                "primary_category": "Science",
                "country": "UK",
                "language": "en",
                "credibility_score": 85,
                "bias_rating": "center",
                "scrape_frequency": 120,
                "max_articles_per_scrape": 15,
            },
            # Sports News
            {
                "name": "ESPN",
                "base_url": "https://www.espn.com",
                "rss_feed": "https://www.espn.com/espn/rss/news",
                "description": "Sports news and coverage",
                "primary_category": "Sports",
                "country": "US",
                "language": "en",
                "credibility_score": 82,
                "bias_rating": "center",
                "scrape_frequency": 60,
                "max_articles_per_scrape": 25,
            },
            {
                "name": "BBC Sport",
                "base_url": "https://www.bbc.com/sport",
                "rss_feed": "https://feeds.bbci.co.uk/sport/rss.xml",
                "description": "International sports coverage",
                "primary_category": "Sports",
                "country": "UK",
                "language": "en",
                "credibility_score": 88,
                "bias_rating": "center",
                "scrape_frequency": 60,
                "max_articles_per_scrape": 20,
            },
            {
                "name": "Sky Sports",
                "base_url": "https://www.skysports.com",
                "rss_feed": "https://www.skysports.com/rss/12040",
                "description": "UK and international sports news",
                "primary_category": "Sports",
                "country": "UK",
                "language": "en",
                "credibility_score": 80,
                "bias_rating": "center",
                "scrape_frequency": 90,
                "max_articles_per_scrape": 20,
            },
            # Health News
            {
                "name": "WebMD News",
                "base_url": "https://www.webmd.com/news",
                "rss_feed": "https://rssfeeds.webmd.com/rss/rss.aspx?RSSSource=RSS_PUBLIC",
                "description": "Health and medical news",
                "primary_category": "Health",
                "country": "US",
                "language": "en",
                "credibility_score": 82,
                "bias_rating": "center",
                "scrape_frequency": 120,
                "max_articles_per_scrape": 15,
            },
            {
                "name": "Medical News Today",
                "base_url": "https://www.medicalnewstoday.com",
                "rss_feed": "https://www.medicalnewstoday.com/rss",
                "description": "Medical and health news for professionals and consumers",
                "primary_category": "Health",
                "country": "UK",
                "language": "en",
                "credibility_score": 85,
                "bias_rating": "center",
                "scrape_frequency": 120,
                "max_articles_per_scrape": 15,
            },
            # Politics News
            {
                "name": "Politico",
                "base_url": "https://www.politico.com",
                "rss_feed": "https://www.politico.com/rss/politicopicks.xml",
                "description": "American political news and analysis",
                "primary_category": "Politics",
                "country": "US",
                "language": "en",
                "credibility_score": 82,
                "bias_rating": "left",
                "scrape_frequency": 45,
                "max_articles_per_scrape": 20,
            },
            {
                "name": "The Hill",
                "base_url": "https://thehill.com",
                "rss_feed": "https://thehill.com/feed/",
                "description": "Congressional and political news",
                "primary_category": "Politics",
                "country": "US",
                "language": "en",
                "credibility_score": 75,
                "bias_rating": "center",
                "scrape_frequency": 60,
                "max_articles_per_scrape": 20,
            },
            {
                "name": "NPR Politics",
                "base_url": "https://www.npr.org/sections/politics/",
                "rss_feed": "https://www.npr.org/rss/rss.php?id=1014",
                "description": "National Public Radio political coverage",
                "primary_category": "Politics",
                "country": "US",
                "language": "en",
                "credibility_score": 89,
                "bias_rating": "left",
                "scrape_frequency": 60,
                "max_articles_per_scrape": 15,
            },
            {
                "name": "The Guardian Politics",
                "base_url": "https://www.theguardian.com/politics",
                "rss_feed": "https://www.theguardian.com/politics/rss",
                "description": "British and international political news",
                "primary_category": "Politics",
                "country": "UK",
                "language": "en",
                "credibility_score": 85,
                "bias_rating": "left",
                "scrape_frequency": 60,
                "max_articles_per_scrape": 20,
            },
            {
                "name": "BBC Politics",
                "base_url": "https://www.bbc.com/news/politics",
                "rss_feed": "https://feeds.bbci.co.uk/news/politics/rss.xml",
                "description": "BBC political news coverage",
                "primary_category": "Politics",
                "country": "UK",
                "language": "en",
                "credibility_score": 92,
                "bias_rating": "center",
                "scrape_frequency": 45,
                "max_articles_per_scrape": 20,
            },
            {
                "name": "Reuters Politics",
                "base_url": "https://www.reuters.com/news/politics",
                "rss_feed": "https://www.reutersagency.com/feed/?best-topics=political-general",
                "description": "Reuters political news coverage",
                "primary_category": "Politics",
                "country": "UK",
                "language": "en",
                "credibility_score": 95,
                "bias_rating": "center",
                "scrape_frequency": 45,
                "max_articles_per_scrape": 20,
            },
            # Entertainment
            {
                "name": "Variety",
                "base_url": "https://variety.com",
                "rss_feed": "https://variety.com/feed/",
                "description": "Entertainment industry news",
                "primary_category": "Entertainment",
                "country": "US",
                "language": "en",
                "credibility_score": 80,
                "bias_rating": "center",
                "scrape_frequency": 120,
                "max_articles_per_scrape": 15,
            },
            {
                "name": "The Hollywood Reporter",
                "base_url": "https://www.hollywoodreporter.com",
                "rss_feed": "https://www.hollywoodreporter.com/feed/",
                "description": "Entertainment business and celebrity news",
                "primary_category": "Entertainment",
                "country": "US",
                "language": "en",
                "credibility_score": 78,
                "bias_rating": "center",
                "scrape_frequency": 120,
                "max_articles_per_scrape": 15,
            },
        ]
