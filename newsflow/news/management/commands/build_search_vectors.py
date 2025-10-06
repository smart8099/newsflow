"""
Management command to build search vectors for articles.

This command updates the search_vector field for articles that don't have one
or rebuilds them for all articles if requested.
"""

import time

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from newsflow.news.models import Article


class Command(BaseCommand):
    help = "Build search vectors for articles"

    def add_arguments(self, parser):
        parser.add_argument(
            "--rebuild",
            action="store_true",
            help="Rebuild search vectors for all articles (not just missing ones)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of articles to process in each batch (default: 100)",
        )
        parser.add_argument(
            "--article-id",
            type=int,
            help="Process only a specific article by ID",
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("Starting search vector build process..."),
        )

        batch_size = options["batch_size"]
        rebuild = options["rebuild"]
        article_id = options.get("article_id")

        try:
            if article_id:
                # Process single article
                self.process_single_article(article_id)
            else:
                # Process articles in batches
                self.process_articles_batch(rebuild, batch_size)

        except Exception as e:
            raise CommandError(f"Error building search vectors: {e}")

    def process_single_article(self, article_id):
        """Process a single article."""
        try:
            article = Article.objects.get(id=article_id)
            self.stdout.write(
                f"Processing article {article_id}: {article.title[:50]}...",
            )

            start_time = time.time()
            article.update_search_vector()
            processing_time = time.time() - start_time

            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ Updated search vector for article {article_id} "
                    f"({processing_time:.2f}s)",
                ),
            )

        except Article.DoesNotExist:
            raise CommandError(f"Article with ID {article_id} not found")

    def process_articles_batch(self, rebuild, batch_size):
        """Process articles in batches."""
        # Get articles to process
        if rebuild:
            articles_queryset = Article.objects.all()
            self.stdout.write(
                self.style.WARNING(
                    "Rebuilding search vectors for ALL articles...",
                ),
            )
        else:
            articles_queryset = Article.objects.filter(search_vector__isnull=True)
            self.stdout.write(
                "Building search vectors for articles without vectors...",
            )

        total_count = articles_queryset.count()

        if total_count == 0:
            self.stdout.write(
                self.style.SUCCESS("No articles need search vector updates."),
            )
            return

        self.stdout.write(f"Found {total_count} articles to process.")

        # Process in batches
        processed_count = 0
        success_count = 0
        error_count = 0
        start_time = time.time()

        for batch_start in range(0, total_count, batch_size):
            batch_end = min(batch_start + batch_size, total_count)
            batch_articles = articles_queryset[batch_start:batch_end]

            self.stdout.write(
                f"Processing batch {batch_start + 1}-{batch_end} of {total_count}...",
            )

            # Process batch with transaction
            with transaction.atomic():
                for article in batch_articles:
                    try:
                        article.update_search_vector()
                        success_count += 1
                        processed_count += 1

                        # Show progress for large batches
                        if processed_count % 50 == 0:
                            elapsed_time = time.time() - start_time
                            rate = processed_count / elapsed_time
                            eta = (
                                (total_count - processed_count) / rate
                                if rate > 0
                                else 0
                            )

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
                f"\n✓ Search vector build completed!\n"
                f"  Total processed: {processed_count}\n"
                f"  Successful: {success_count}\n"
                f"  Errors: {error_count}\n"
                f"  Total time: {total_time:.2f}s\n"
                f"  Average rate: {processed_count / total_time:.1f} articles/second",
            ),
        )

        if error_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠ {error_count} articles had errors. Check error messages above.",
                ),
            )
