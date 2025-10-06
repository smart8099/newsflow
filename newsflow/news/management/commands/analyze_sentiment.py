"""
Management command to analyze sentiment for articles.

This command processes articles without sentiment data or can reanalyze
all articles if requested.
"""

import time

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from newsflow.news.models import Article
from newsflow.news.sentiment import SentimentAnalyzer


class Command(BaseCommand):
    help = "Analyze sentiment for articles"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reanalyze",
            action="store_true",
            help="Reanalyze sentiment for all articles (not just missing ones)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Number of articles to process in each batch (default: 50)",
        )
        parser.add_argument(
            "--article-id",
            type=int,
            help="Process only a specific article by ID",
        )
        parser.add_argument(
            "--use-transformers",
            action="store_true",
            help="Use transformer models for sentiment analysis (slower but more accurate)",
        )
        parser.add_argument(
            "--category",
            type=str,
            help="Process only articles in a specific category",
        )
        parser.add_argument(
            "--source",
            type=str,
            help="Process only articles from a specific source",
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("Starting sentiment analysis process..."),
        )

        batch_size = options["batch_size"]
        reanalyze = options["reanalyze"]
        article_id = options.get("article_id")
        use_transformers = options["use_transformers"]
        category = options.get("category")
        source = options.get("source")

        # Initialize sentiment analyzer
        self.analyzer = SentimentAnalyzer(use_transformers=use_transformers)

        if use_transformers:
            self.stdout.write(
                self.style.WARNING(
                    "Using transformer models (slower but more accurate)...",
                ),
            )

        try:
            if article_id:
                # Process single article
                self.process_single_article(article_id)
            else:
                # Process articles in batches
                self.process_articles_batch(
                    reanalyze,
                    batch_size,
                    category,
                    source,
                )

        except Exception as e:
            raise CommandError(f"Error analyzing sentiment: {e}")

    def process_single_article(self, article_id):
        """Process a single article."""
        try:
            article = Article.objects.get(id=article_id)
            self.stdout.write(
                f"Processing article {article_id}: {article.title[:50]}...",
            )

            start_time = time.time()
            result = self.analyze_article_sentiment(article)
            processing_time = time.time() - start_time

            if result["status"] == "success":
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Analyzed sentiment for article {article_id}: "
                        f"{result['sentiment_label']} (score: {result['sentiment_score']:.3f}) "
                        f"({processing_time:.2f}s)",
                    ),
                )
            else:
                self.stderr.write(
                    self.style.ERROR(
                        f"Error analyzing article {article_id}: {result['error']}",
                    ),
                )

        except Article.DoesNotExist:
            raise CommandError(f"Article with ID {article_id} not found")

    def process_articles_batch(self, reanalyze, batch_size, category=None, source=None):
        """Process articles in batches."""
        # Build queryset
        articles_queryset = Article.objects.all()

        # Apply filters
        if category:
            articles_queryset = articles_queryset.filter(
                categories__name__icontains=category,
            )
        if source:
            articles_queryset = articles_queryset.filter(source__name__icontains=source)

        # Filter by sentiment status
        if reanalyze:
            self.stdout.write(
                self.style.WARNING(
                    "Reanalyzing sentiment for ALL matching articles...",
                ),
            )
        else:
            from django.db import models

            articles_queryset = articles_queryset.filter(
                models.Q(sentiment_label__isnull=True) | models.Q(sentiment_label=""),
            )
            self.stdout.write(
                "Analyzing sentiment for articles without sentiment data...",
            )

        total_count = articles_queryset.count()

        if total_count == 0:
            self.stdout.write(
                self.style.SUCCESS("No articles need sentiment analysis."),
            )
            return

        self.stdout.write(f"Found {total_count} articles to process.")

        # Process in batches
        processed_count = 0
        success_count = 0
        error_count = 0
        skipped_count = 0
        start_time = time.time()

        sentiment_distribution = {"positive": 0, "neutral": 0, "negative": 0}

        for batch_start in range(0, total_count, batch_size):
            batch_end = min(batch_start + batch_size, total_count)
            batch_articles = articles_queryset[batch_start:batch_end]

            self.stdout.write(
                f"Processing batch {batch_start + 1}-{batch_end} of {total_count}...",
            )

            # Process batch
            for article in batch_articles:
                try:
                    result = self.analyze_article_sentiment(
                        article,
                        force_update=reanalyze,
                    )
                    processed_count += 1

                    if result["status"] == "success":
                        success_count += 1
                        sentiment_distribution[result["sentiment_label"]] += 1
                    elif result["status"] == "skipped":
                        skipped_count += 1
                    else:
                        error_count += 1

                    # Show progress for large batches
                    if processed_count % 25 == 0:
                        elapsed_time = time.time() - start_time
                        rate = processed_count / elapsed_time
                        eta = (total_count - processed_count) / rate if rate > 0 else 0

                        self.stdout.write(
                            f"  Progress: {processed_count}/{total_count} "
                            f"({processed_count / total_count * 100:.1f}%) "
                            f"- Rate: {rate:.1f}/s - ETA: {eta:.0f}s",
                        )

                except Exception as e:
                    error_count += 1
                    processed_count += 1
                    self.stderr.write(
                        self.style.ERROR(
                            f"Error processing article {article.id}: {e}",
                        ),
                    )

        # Final summary
        total_time = time.time() - start_time
        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Sentiment analysis completed!\n"
                f"  Total processed: {processed_count}\n"
                f"  Successful: {success_count}\n"
                f"  Skipped: {skipped_count}\n"
                f"  Errors: {error_count}\n"
                f"  Total time: {total_time:.2f}s\n"
                f"  Average rate: {processed_count / total_time:.1f} articles/second",
            ),
        )

        # Show sentiment distribution
        if success_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n📊 Sentiment Distribution:\n"
                    f"  Positive: {sentiment_distribution['positive']} "
                    f"({sentiment_distribution['positive'] / success_count * 100:.1f}%)\n"
                    f"  Neutral: {sentiment_distribution['neutral']} "
                    f"({sentiment_distribution['neutral'] / success_count * 100:.1f}%)\n"
                    f"  Negative: {sentiment_distribution['negative']} "
                    f"({sentiment_distribution['negative'] / success_count * 100:.1f}%)",
                ),
            )

        if error_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠ {error_count} articles had errors. Check error messages above.",
                ),
            )

    def analyze_article_sentiment(self, article, force_update=False):
        """Analyze sentiment for a single article."""
        try:
            # Check if already analyzed
            if not force_update and not article.needs_sentiment_analysis():
                return {
                    "status": "skipped",
                    "sentiment_label": article.sentiment_label,
                    "sentiment_score": article.sentiment_score,
                }

            # Prepare text for analysis
            text_to_analyze = f"{article.title} {article.content}"

            # Analyze sentiment
            sentiment_result = self.analyzer.analyze_sentiment(text_to_analyze)

            # Update article
            with transaction.atomic():
                article.sentiment_score = sentiment_result["score"]
                article.sentiment_label = sentiment_result["label"]
                article.save(update_fields=["sentiment_score", "sentiment_label"])

            return {
                "status": "success",
                "sentiment_label": sentiment_result["label"],
                "sentiment_score": sentiment_result["score"],
                "confidence": sentiment_result.get("confidence", 0.0),
                "method": sentiment_result.get("method", "unknown"),
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }
