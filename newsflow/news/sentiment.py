"""
Sentiment analysis for NewsFlow articles.

Provides sentiment analysis using VADER and transformer models
to classify article sentiment as positive, neutral, or negative.
"""

import logging

from django.core.cache import cache
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """
    Sentiment analysis using VADER and optional transformer models.

    VADER is used for fast sentiment analysis, with optional transformer
    models for more accurate results on longer texts.
    """

    def __init__(self, use_transformers: bool = False):
        """
        Initialize the sentiment analyzer.

        Args:
            use_transformers: Whether to use transformer models (slower but more accurate)
        """
        self.use_transformers = use_transformers
        self.vader_analyzer = SentimentIntensityAnalyzer()
        self.transformer_pipeline = None

        if use_transformers:
            self._init_transformer_model()

    def _init_transformer_model(self):
        """Initialize the transformer model for sentiment analysis."""
        try:
            from transformers import pipeline

            # Use a lightweight sentiment analysis model
            self.transformer_pipeline = pipeline(
                "sentiment-analysis",
                model="cardiffnlp/twitter-roberta-base-sentiment-latest",
                device=-1,  # Use CPU (no GPU required)
                truncation=True,
                max_length=512,
            )
            logger.info("Transformer model loaded successfully")

        except ImportError:
            logger.warning("Transformers not available, falling back to VADER only")
            self.use_transformers = False
        except Exception as e:
            logger.error(f"Error loading transformer model: {e}")
            self.use_transformers = False

    def analyze_sentiment(self, text: str) -> dict:
        """
        Analyze sentiment of text.

        Args:
            text: Text to analyze

        Returns:
            Dictionary with score, label, and confidence
        """
        if not text or not text.strip():
            return {
                "score": 0.0,
                "label": "neutral",
                "confidence": 0.0,
                "method": "default",
            }

        # Check cache first
        cache_key = f"sentiment_{hash(text[:500])}"  # Use first 500 chars for cache key
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        # Use transformer model if available and text is substantial
        if self.use_transformers and self.transformer_pipeline and len(text) > 100:
            result = self._analyze_with_transformer(text)
            result["method"] = "transformer"
        else:
            result = self._analyze_with_vader(text)
            result["method"] = "vader"

        # Cache the result for 1 hour
        cache.set(cache_key, result, 3600)

        return result

    def _analyze_with_vader(self, text: str) -> dict:
        """
        Analyze sentiment using VADER.

        Args:
            text: Text to analyze

        Returns:
            Sentiment analysis result
        """
        try:
            # Truncate text for performance (VADER works well on shorter texts)
            text_sample = text[:2000] if len(text) > 2000 else text

            scores = self.vader_analyzer.polarity_scores(text_sample)

            # VADER returns compound score from -1 to 1
            compound_score = scores["compound"]

            # Classify based on compound score
            if compound_score >= 0.05:
                label = "positive"
                confidence = min(compound_score * 2, 1.0)  # Scale to 0-1
            elif compound_score <= -0.05:
                label = "negative"
                confidence = min(abs(compound_score) * 2, 1.0)
            else:
                label = "neutral"
                confidence = 1.0 - abs(compound_score) * 2

            return {
                "score": compound_score,
                "label": label,
                "confidence": max(0.0, min(1.0, confidence)),
                "details": {
                    "positive": scores["pos"],
                    "neutral": scores["neu"],
                    "negative": scores["neg"],
                    "compound": scores["compound"],
                },
            }

        except Exception as e:
            logger.error(f"Error in VADER sentiment analysis: {e}")
            return {
                "score": 0.0,
                "label": "neutral",
                "confidence": 0.0,
                "error": str(e),
            }

    def _analyze_with_transformer(self, text: str) -> dict:
        """
        Analyze sentiment using transformer model.

        Args:
            text: Text to analyze

        Returns:
            Sentiment analysis result
        """
        try:
            # Truncate text for transformer model
            text_sample = text[:1000] if len(text) > 1000 else text

            # Get prediction
            result = self.transformer_pipeline(text_sample)[0]

            # Map labels to our format
            label_mapping = {
                "LABEL_0": "negative",  # For some models
                "LABEL_1": "neutral",
                "LABEL_2": "positive",
                "NEGATIVE": "negative",  # For RoBERTa models
                "NEUTRAL": "neutral",
                "POSITIVE": "positive",
            }

            raw_label = result["label"].upper()
            mapped_label = label_mapping.get(raw_label, "neutral")
            confidence = result["score"]

            # Convert to score from -1 to 1
            if mapped_label == "positive":
                score = confidence * 0.5 + 0.5  # Map to 0.5-1.0
            elif mapped_label == "negative":
                score = -confidence * 0.5 - 0.5  # Map to -1.0 to -0.5
            else:
                score = 0.0

            return {
                "score": score,
                "label": mapped_label,
                "confidence": confidence,
                "details": {
                    "raw_label": result["label"],
                    "raw_score": result["score"],
                },
            }

        except Exception as e:
            logger.error(f"Error in transformer sentiment analysis: {e}")
            # Fallback to VADER
            return self._analyze_with_vader(text)

    def batch_analyze(self, texts: list[str], batch_size: int = 10) -> list[dict]:
        """
        Analyze sentiment for multiple texts.

        Args:
            texts: List of texts to analyze
            batch_size: Batch size for processing

        Returns:
            List of sentiment analysis results
        """
        results = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            for text in batch:
                result = self.analyze_sentiment(text)
                results.append(result)

            # Log progress for large batches
            if len(texts) > 50 and (i + batch_size) % 50 == 0:
                logger.info(f"Processed {i + batch_size}/{len(texts)} texts")

        return results

    def get_sentiment_distribution(self, texts: list[str]) -> dict:
        """
        Get sentiment distribution for a collection of texts.

        Args:
            texts: List of texts to analyze

        Returns:
            Dictionary with sentiment distribution statistics
        """
        if not texts:
            return {
                "positive": 0,
                "neutral": 0,
                "negative": 0,
                "total": 0,
                "average_score": 0.0,
            }

        results = self.batch_analyze(texts)

        distribution = {"positive": 0, "neutral": 0, "negative": 0}
        total_score = 0.0

        for result in results:
            distribution[result["label"]] += 1
            total_score += result["score"]

        total_count = len(results)
        average_score = total_score / total_count if total_count > 0 else 0.0

        return {
            **distribution,
            "total": total_count,
            "average_score": average_score,
            "positive_pct": (distribution["positive"] / total_count * 100)
            if total_count > 0
            else 0,
            "neutral_pct": (distribution["neutral"] / total_count * 100)
            if total_count > 0
            else 0,
            "negative_pct": (distribution["negative"] / total_count * 100)
            if total_count > 0
            else 0,
        }


class ArticleSentimentMixin:
    """
    Mixin for adding sentiment analysis capabilities to models.
    """

    @classmethod
    def analyze_article_sentiment(cls, article):
        """
        Analyze sentiment for an article and update the model.

        Args:
            article: Article instance to analyze

        Returns:
            Sentiment analysis result
        """
        analyzer = SentimentAnalyzer()

        # Combine title and content for analysis
        text_to_analyze = f"{article.title} {article.content}"

        result = analyzer.analyze_sentiment(text_to_analyze)

        # Update article fields
        article.sentiment_score = result["score"]
        article.sentiment_label = result["label"]
        article.save(update_fields=["sentiment_score", "sentiment_label"])

        logger.info(
            f"Analyzed sentiment for article {article.id}: "
            f"{result['label']} (score: {result['score']:.3f})",
        )

        return result

    @classmethod
    def get_sentiment_stats(cls, queryset=None):
        """
        Get sentiment statistics for a queryset of articles.

        Args:
            queryset: Article queryset (defaults to all articles)

        Returns:
            Dictionary with sentiment statistics
        """
        if queryset is None:
            from newsflow.news.models import Article

            queryset = Article.objects.all()

        # Filter articles with sentiment data
        articles_with_sentiment = queryset.exclude(
            sentiment_label__isnull=True,
        ).exclude(sentiment_label="")

        if not articles_with_sentiment.exists():
            return {
                "total": 0,
                "positive": 0,
                "neutral": 0,
                "negative": 0,
                "average_score": 0.0,
                "coverage": 0.0,
            }

        from django.db.models import Avg
        from django.db.models import Count
        from django.db.models import Q

        # Get sentiment distribution
        sentiment_counts = articles_with_sentiment.aggregate(
            total=Count("id"),
            positive=Count("id", filter=Q(sentiment_label="positive")),
            neutral=Count("id", filter=Q(sentiment_label="neutral")),
            negative=Count("id", filter=Q(sentiment_label="negative")),
            average_score=Avg("sentiment_score"),
        )

        total_articles = queryset.count()
        analyzed_articles = sentiment_counts["total"]

        return {
            **sentiment_counts,
            "coverage": (analyzed_articles / total_articles * 100)
            if total_articles > 0
            else 0,
            "positive_pct": (sentiment_counts["positive"] / analyzed_articles * 100)
            if analyzed_articles > 0
            else 0,
            "neutral_pct": (sentiment_counts["neutral"] / analyzed_articles * 100)
            if analyzed_articles > 0
            else 0,
            "negative_pct": (sentiment_counts["negative"] / analyzed_articles * 100)
            if analyzed_articles > 0
            else 0,
        }
