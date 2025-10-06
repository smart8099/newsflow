"""
Management command to generate summaries for articles.

This command processes articles without summaries or can regenerate
summaries for all articles if requested.
"""

import time

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from newsflow.news.models import Article
from newsflow.news.summarizer import ArticleSummarizer


class Command(BaseCommand):
    help = "Generate summaries for articles"

    def add_arguments(self, parser):
        parser.add_argument(
            "--regenerate",
            action="store_true",
            help="Regenerate summaries for all articles (not just missing ones)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=25,
            help="Number of articles to process in each batch (default: 25)",
        )
        parser.add_argument(
            "--article-id",
            type=int,
            help="Process only a specific article by ID",
        )
        parser.add_argument(
            "--summary-type",
            choices=["extractive", "abstractive"],
            default="extractive",
            help="Type of summary to generate (default: extractive)",
        )
        parser.add_argument(
            "--min-content-length",
            type=int,
            default=500,
            help="Minimum content length to generate summary (default: 500 chars)",
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
            self.style.SUCCESS("Starting summary generation process..."),
        )

        batch_size = options["batch_size"]
        regenerate = options["regenerate"]
        article_id = options.get("article_id")
        summary_type = options["summary_type"]
        min_content_length = options["min_content_length"]
        category = options.get("category")
        source = options.get("source")

        # Initialize summarizer
        use_transformers = summary_type == "abstractive"
        self.summarizer = ArticleSummarizer(use_transformers=use_transformers)

        if summary_type == "abstractive":
            if (
                self.summarizer.use_transformers
                and self.summarizer.transformer_pipeline
            ):
                self.stdout.write(
                    self.style.SUCCESS(
                        "✓ Using abstractive summarization with transformer models...",
                    ),
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        "⚠ Transformer models not available. Using extractive summarization...",
                    ),
                )
                self.stdout.write(
                    "To enable abstractive summarization, install PyTorch or TensorFlow:\n"
                    "  uv add torch  # for PyTorch\n"
                    "  uv add tensorflow  # for TensorFlow",
                )

        try:
            if article_id:
                # Process single article
                self.process_single_article(article_id, summary_type)
            else:
                # Process articles in batches
                self.process_articles_batch(
                    regenerate,
                    batch_size,
                    summary_type,
                    min_content_length,
                    category,
                    source,
                )

        except Exception as e:
            raise CommandError(f"Error generating summaries: {e}")

    def process_single_article(self, article_id, summary_type):
        """Process a single article."""
        try:
            article = Article.objects.get(id=article_id)
            self.stdout.write(
                f"Processing article {article_id}: {article.title[:50]}...",
            )

            start_time = time.time()
            result = self.generate_article_summary(article, summary_type)
            processing_time = time.time() - start_time

            if result["status"] == "success":
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Generated {summary_type} summary for article {article_id}: "
                        f"{result['summary_length']} chars "
                        f"(compression: {result['compression_ratio']:.1%}) "
                        f"({processing_time:.2f}s)",
                    ),
                )
            else:
                error_msg = result.get("error", "Unknown error occurred")
                self.stderr.write(
                    self.style.ERROR(
                        f"Error processing article {article_id}: {error_msg}",
                    ),
                )

        except Article.DoesNotExist:
            raise CommandError(f"Article with ID {article_id} not found")

    def process_articles_batch(
        self,
        regenerate,
        batch_size,
        summary_type,
        min_content_length,
        category=None,
        source=None,
    ):
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

        # Filter by content length
        articles_queryset = articles_queryset.extra(
            where=["LENGTH(content) >= %s"],
            params=[min_content_length],
        )

        # Filter by summary status
        if regenerate:
            self.stdout.write(
                self.style.WARNING(
                    f"Regenerating {summary_type} summaries for ALL matching articles...",
                ),
            )
        else:
            from django.db import models

            articles_queryset = articles_queryset.filter(
                models.Q(summary__isnull=True) | models.Q(summary=""),
            )
            self.stdout.write(
                f"Generating {summary_type} summaries for articles without summaries...",
            )

        total_count = articles_queryset.count()

        if total_count == 0:
            self.stdout.write(
                self.style.SUCCESS("No articles need summary generation."),
            )
            return

        self.stdout.write(f"Found {total_count} articles to process.")

        # Process in batches
        processed_count = 0
        success_count = 0
        error_count = 0
        skipped_count = 0
        start_time = time.time()

        total_original_length = 0
        total_summary_length = 0

        for batch_start in range(0, total_count, batch_size):
            batch_end = min(batch_start + batch_size, total_count)
            batch_articles = articles_queryset[batch_start:batch_end]

            self.stdout.write(
                f"Processing batch {batch_start + 1}-{batch_end} of {total_count}...",
            )

            # Process batch
            for article in batch_articles:
                try:
                    result = self.generate_article_summary(
                        article,
                        summary_type,
                        force_update=regenerate,
                    )
                    processed_count += 1

                    if result["status"] == "success":
                        success_count += 1
                        total_original_length += result.get("original_length", 0)
                        total_summary_length += result.get("summary_length", 0)
                    elif result["status"] == "skipped":
                        skipped_count += 1
                    else:
                        error_count += 1

                    # Show progress for large batches
                    if processed_count % 10 == 0:
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
        avg_compression = (
            total_summary_length / total_original_length * 100
            if total_original_length > 0
            else 0
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Summary generation completed!\n"
                f"  Total processed: {processed_count}\n"
                f"  Successful: {success_count}\n"
                f"  Skipped: {skipped_count}\n"
                f"  Errors: {error_count}\n"
                f"  Total time: {total_time:.2f}s\n"
                f"  Average rate: {processed_count / total_time:.1f} articles/second\n"
                f"  Average compression ratio: {avg_compression:.1f}%",
            ),
        )

        if error_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠ {error_count} articles had errors. Check error messages above.",
                ),
            )

    def generate_article_summary(self, article, summary_type, force_update=False):
        """Generate summary for a single article."""
        try:
            # Check if already has summary
            if not force_update and article.summary and article.summary.strip():
                return {
                    "status": "skipped",
                    "summary_length": len(article.summary),
                }

            # Generate summary
            summary_result = self.summarizer.summarize_article(article, summary_type)

            # Update article
            with transaction.atomic():
                article.summary = summary_result["summary"]
                article.save(update_fields=["summary"])

            return {
                "status": "success",
                "summary_type": summary_result["summary_type"],
                "summary_length": summary_result["summary_length"],
                "original_length": summary_result["original_length"],
                "compression_ratio": summary_result["compression_ratio"],
                "keywords": summary_result["keywords"],
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }
