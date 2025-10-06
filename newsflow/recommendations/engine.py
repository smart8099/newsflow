"""
Content-based recommendation engine for NewsFlow.

This module implements TF-IDF based content recommendation using scikit-learn
to provide personalized article recommendations based on user reading history.
"""

import logging
import re
from datetime import timedelta

import numpy as np
from django.core.cache import cache
from django.db.models import Q
from django.db.models import QuerySet
from django.utils import timezone
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from newsflow.news.models import Article
from newsflow.news.models import UserInteraction
from newsflow.users.models import UserProfile

logger = logging.getLogger(__name__)


class ContentBasedRecommender:
    """
    Content-based recommendation engine using TF-IDF vectorization.

    This recommender analyzes article content and user reading patterns
    to provide personalized recommendations based on textual similarity.
    """

    def __init__(self, max_features: int = 5000, cache_timeout: int = 3600):
        """
        Initialize the content-based recommender.

        Args:
            max_features: Maximum number of features for TF-IDF vectorizer
            cache_timeout: Cache timeout in seconds (default: 1 hour)
        """
        self.vectorizer = TfidfVectorizer(
            max_features=max_features,
            stop_words="english",
            ngram_range=(1, 2),  # Use unigrams and bigrams
            min_df=2,  # Ignore terms that appear in less than 2 documents
            max_df=0.95,  # Ignore terms that appear in more than 95% of documents
            strip_accents="unicode",
            lowercase=True,
            analyzer="word",
            token_pattern=r"\b\w+\b",
            use_idf=True,
            smooth_idf=True,
            sublinear_tf=True,  # Use logarithmic tf scaling
        )
        self.cache_timeout = cache_timeout
        self.article_vectors = None
        self.article_ids = None

    def preprocess_text(self, text: str) -> str:
        """
        Clean and normalize text for processing.

        Args:
            text: Raw text to preprocess

        Returns:
            Preprocessed text string
        """
        if not text:
            return ""

        # Convert to lowercase
        text = text.lower()

        # Remove HTML tags if any
        text = re.sub(r"<[^>]+>", " ", text)

        # Remove URLs
        text = re.sub(r"https?://\S+|www\.\S+", " ", text)

        # Remove email addresses
        text = re.sub(r"\S+@\S+", " ", text)

        # Remove special characters but keep spaces
        text = re.sub(r"[^a-zA-Z0-9\s]", " ", text)

        # Remove extra whitespace
        text = " ".join(text.split())

        return text

    def _get_article_text(self, article: Article) -> str:
        """
        Combine article title, content, and keywords for vectorization.

        Args:
            article: Article model instance

        Returns:
            Combined text for vectorization
        """
        # Weight title more heavily by repeating it
        title_weight = 3
        title_text = " ".join([article.title] * title_weight) if article.title else ""

        # Include content
        content_text = article.content if article.content else ""

        # Include keywords if available (ensure they are strings)
        keyword_text = ""
        if article.keywords and isinstance(article.keywords, list):
            # Filter to ensure all items are strings
            string_keywords = [str(kw) for kw in article.keywords if kw]
            keyword_text = " ".join(string_keywords)

        # Include category names
        categories = article.categories.all()
        category_text = " ".join([cat.name for cat in categories]) if categories else ""

        # Combine all text
        combined_text = f"{title_text} {content_text} {keyword_text} {category_text}"

        return self.preprocess_text(combined_text)

    def _build_article_vectors(
        self,
        force_rebuild: bool = False,
    ) -> tuple[np.ndarray, list[int]]:
        """
        Build TF-IDF vectors for all articles.

        Args:
            force_rebuild: Force rebuilding vectors even if cached

        Returns:
            Tuple of (article vectors matrix, article IDs list)
        """
        cache_key = "recommendation_article_vectors"

        if not force_rebuild:
            cached_data = cache.get(cache_key)
            if cached_data:
                self.article_vectors, self.article_ids = cached_data
                return self.article_vectors, self.article_ids

        # Get recent articles (last 30 days)
        cutoff_date = timezone.now() - timedelta(days=30)
        articles = (
            Article.objects.filter(
                published_at__gte=cutoff_date,
            )
            .prefetch_related("categories")
            .order_by("-published_at")[:5000]
        )

        if not articles:
            logger.warning("No articles found for vectorization")
            return np.array([]), []

        # Extract text from articles
        article_texts = [self._get_article_text(article) for article in articles]
        article_ids = [article.id for article in articles]

        # Fit and transform
        try:
            article_vectors = self.vectorizer.fit_transform(article_texts)
            self.article_vectors = article_vectors
            self.article_ids = article_ids

            # Cache the results
            cache.set(cache_key, (article_vectors, article_ids), self.cache_timeout)

            logger.info(f"Built TF-IDF vectors for {len(article_ids)} articles")
            return article_vectors, article_ids

        except Exception as e:
            logger.error(f"Error building article vectors: {e}")
            return np.array([]), []

    def get_user_profile_vector(self, user_id: int) -> np.ndarray | None:
        """
        Create a TF-IDF vector representing user's interests.

        Args:
            user_id: User ID to create profile for

        Returns:
            User profile vector or None if insufficient data
        """
        cache_key = f"user_profile_vector_{user_id}"
        cached_vector = cache.get(cache_key)
        if cached_vector is not None:
            return cached_vector

        # Ensure article vectors are built
        if self.article_vectors is None:
            self._build_article_vectors()

        # Get user's reading history (last 50 articles)
        user_interactions = (
            UserInteraction.objects.filter(
                user_id=user_id,
                action__in=[
                    UserInteraction.ActionType.VIEW,
                    UserInteraction.ActionType.LIKE,
                    UserInteraction.ActionType.SHARE,
                    UserInteraction.ActionType.BOOKMARK,
                ],
            )
            .select_related("article")
            .order_by(
                "-created",
            )[:50]
        )

        if not user_interactions:
            logger.info(f"No interaction history for user {user_id}")
            return None

        # Group interactions by article to handle multiple actions per article
        from collections import defaultdict

        article_interactions = defaultdict(list)

        for interaction in user_interactions:
            article_interactions[interaction.article].append(interaction)

        # Calculate combined weights per article
        now = timezone.now()
        weighted_texts = []

        for article, interactions in article_interactions.items():
            # Calculate the strongest engagement for this article
            max_engagement_weight = 0
            most_recent_interaction = None

            # Action weights mapping
            action_weights = {
                UserInteraction.ActionType.VIEW: 1.0,
                UserInteraction.ActionType.LIKE: 2.0,
                UserInteraction.ActionType.BOOKMARK: 2.5,
                UserInteraction.ActionType.SHARE: 3.0,
                UserInteraction.ActionType.COMMENT: 2.2,
                UserInteraction.ActionType.CLICK: 1.1,
            }

            # Find the strongest engagement and most recent interaction
            for interaction in interactions:
                action_weight = action_weights.get(interaction.action, 1.0)
                max_engagement_weight = max(max_engagement_weight, action_weight)

                if (
                    most_recent_interaction is None
                    or interaction.created > most_recent_interaction.created
                ):
                    most_recent_interaction = interaction

            # Calculate time decay based on most recent interaction
            days_old = (now - most_recent_interaction.created).days
            time_weight = np.exp(-days_old / 30)

            # Bonus for multiple interactions (engagement depth)
            interaction_count = len(interactions)
            depth_bonus = (
                1.0 + (interaction_count - 1) * 0.2
            )  # 20% bonus per additional interaction

            # Combine all weight factors
            final_weight = time_weight * max_engagement_weight * depth_bonus

            # Get article text and repeat based on weight
            article_text = self._get_article_text(article)
            repetitions = max(1, int(final_weight * 3))

            weighted_texts.extend([article_text] * repetitions)

        # Combine all weighted texts
        combined_text = " ".join(weighted_texts)

        try:
            # Transform using existing vocabulary
            user_vector = self.vectorizer.transform([combined_text])

            # Cache the result
            cache.set(cache_key, user_vector, 600)  # Cache for 10 minutes

            return user_vector

        except Exception as e:
            logger.error(f"Error creating user profile vector: {e}")
            return None

    def get_recommendations(
        self,
        user_id: int,
        limit: int = 10,
        exclude_read: bool = True,
        min_score: float = 0.1,
    ) -> QuerySet:
        """
        Get personalized article recommendations for a user.

        Args:
            user_id: User ID to get recommendations for
            limit: Maximum number of recommendations
            exclude_read: Whether to exclude already read articles
            min_score: Minimum similarity score threshold

        Returns:
            QuerySet of recommended articles with relevance scores
        """
        # Build article vectors if not already built
        if self.article_vectors is None:
            self._build_article_vectors()

        if not self.article_ids:
            logger.warning("No articles available for recommendations")
            return Article.objects.none()

        # Get user profile vector
        user_vector = self.get_user_profile_vector(user_id)
        if user_vector is None:
            # Fallback to category-based recommendations
            logger.info(
                f"No user profile vector for user {user_id}, falling back to category preferences",
            )
            return self._get_category_based_fallback(user_id, limit, exclude_read)

        # Calculate similarity scores
        try:
            similarities = cosine_similarity(
                user_vector,
                self.article_vectors,
            ).flatten()
        except Exception as e:
            logger.error(f"Error calculating similarities: {e}")
            return self._get_category_based_fallback(user_id, limit, exclude_read)

        # Get articles to exclude
        excluded_ids = set()
        if exclude_read:
            viewed_articles = UserInteraction.objects.filter(
                user_id=user_id,
                action=UserInteraction.ActionType.VIEW,
            ).values_list("article_id", flat=True)
            excluded_ids.update(viewed_articles)

        # Filter and sort recommendations
        recommendations = []
        for idx, (article_id, score) in enumerate(
            zip(self.article_ids, similarities, strict=False),
        ):
            if article_id not in excluded_ids and score >= min_score:
                recommendations.append((article_id, score))

        # Sort by score and apply diversity
        recommendations.sort(key=lambda x: x[1], reverse=True)

        # Apply source diversity (no more than 2 articles from same source)
        diverse_recommendations = self._apply_diversity(recommendations, limit)

        # Get article IDs and scores
        recommended_ids = [r[0] for r in diverse_recommendations]
        scores_dict = {r[0]: r[1] for r in diverse_recommendations}

        if not recommended_ids:
            logger.info(f"No content-based recommendations found for user {user_id}")
            return self._get_category_based_fallback(user_id, limit, exclude_read)

        # Fetch articles and annotate with scores
        articles = Article.objects.filter(
            id__in=recommended_ids,
        ).select_related("source", "category")

        # Add relevance scores to articles
        for article in articles:
            article.relevance_score = scores_dict.get(article.id, 0.0)
            article.recommendation_reason = self._get_recommendation_reason(
                article,
                user_id,
            )

        # Sort by relevance score
        articles = sorted(articles, key=lambda a: a.relevance_score, reverse=True)

        return articles[:limit]

    def get_similar_articles(self, article_id: int, limit: int = 5) -> QuerySet:
        """
        Find articles similar to a given article.

        Args:
            article_id: ID of the reference article
            limit: Maximum number of similar articles

        Returns:
            QuerySet of similar articles
        """
        # Build article vectors if not already built
        if self.article_vectors is None:
            self._build_article_vectors()

        if article_id not in self.article_ids:
            # Article not in index, need to vectorize it
            try:
                article = Article.objects.prefetch_related("categories").get(
                    id=article_id,
                )
                article_text = self._get_article_text(article)
                article_vector = self.vectorizer.transform([article_text])
            except Article.DoesNotExist:
                logger.error(f"Article {article_id} not found")
                return Article.objects.none()
            except Exception as e:
                logger.error(f"Error vectorizing article {article_id}: {e}")
                return Article.objects.none()
        else:
            # Get vector from index
            idx = self.article_ids.index(article_id)
            article_vector = self.article_vectors[idx : idx + 1]

        # Calculate similarities
        try:
            similarities = cosine_similarity(
                article_vector,
                self.article_vectors,
            ).flatten()
        except Exception as e:
            logger.error(f"Error calculating article similarities: {e}")
            return Article.objects.none()

        # Get top similar articles (excluding the article itself)
        similar_indices = []
        for idx, (aid, score) in enumerate(
            zip(self.article_ids, similarities, strict=False),
        ):
            if aid != article_id and score > 0.2:  # Minimum similarity threshold
                similar_indices.append((aid, score))

        # Sort by similarity
        similar_indices.sort(key=lambda x: x[1], reverse=True)
        similar_indices = similar_indices[:limit]

        if not similar_indices:
            # Fallback to same categories
            article = Article.objects.prefetch_related("categories").get(id=article_id)
            article_categories = article.categories.all()
            if article_categories:
                return (
                    Article.objects.filter(
                        categories__in=article_categories,
                    )
                    .exclude(id=article_id)
                    .distinct()
                    .order_by("-published_at")[:limit]
                )
            return Article.objects.exclude(id=article_id).order_by("-published_at")[
                :limit
            ]

        # Get articles
        similar_ids = [sid for sid, _ in similar_indices]
        scores_dict = {sid: score for sid, score in similar_indices}

        articles = (
            Article.objects.filter(
                id__in=similar_ids,
            )
            .select_related("source")
            .prefetch_related("categories")
        )

        # Add similarity scores
        for article in articles:
            article.relevance_score = scores_dict.get(article.id, 0.0)
            article.recommendation_reason = "Similar content"

        # Sort by relevance
        articles = sorted(articles, key=lambda a: a.relevance_score, reverse=True)

        return articles

    def _apply_diversity(
        self,
        recommendations: list[tuple[int, float]],
        limit: int,
    ) -> list[tuple[int, float]]:
        """
        Apply diversity constraints to recommendations.

        Ensures no more than 2 articles from the same source.

        Args:
            recommendations: List of (article_id, score) tuples
            limit: Maximum number of recommendations

        Returns:
            Diverse list of recommendations
        """
        diverse_recs = []
        source_counts = {}

        # Get article sources in batch
        article_ids = [r[0] for r in recommendations]
        article_sources = dict(
            Article.objects.filter(
                id__in=article_ids,
            ).values_list("id", "source_id"),
        )

        for article_id, score in recommendations:
            source_id = article_sources.get(article_id)

            if source_id:
                count = source_counts.get(source_id, 0)
                if count >= 2:  # Skip if already have 2 from this source
                    continue
                source_counts[source_id] = count + 1

            diverse_recs.append((article_id, score))

            if len(diverse_recs) >= limit:
                break

        return diverse_recs

    def _get_category_based_fallback(
        self,
        user_id: int,
        limit: int,
        exclude_read: bool,
    ) -> QuerySet:
        """
        Fallback to category-based recommendations when content-based fails.

        Args:
            user_id: User ID
            limit: Maximum number of recommendations
            exclude_read: Whether to exclude read articles

        Returns:
            QuerySet of articles from preferred categories
        """
        try:
            user_profile = UserProfile.objects.get(user_id=user_id)
            preferred_category_codes = user_profile.get_preferred_category_codes()

            if not preferred_category_codes:
                # No preferences, return latest articles
                queryset = Article.objects.published()
            else:
                # Filter by source category or article categories
                queryset = (
                    Article.objects.published()
                    .filter(
                        Q(source__primary_category__in=preferred_category_codes)
                        | Q(categories__slug__in=preferred_category_codes),
                    )
                    .distinct()
                )

            if exclude_read:
                viewed_ids = UserInteraction.objects.filter(
                    user_id=user_id,
                    action=UserInteraction.ActionType.VIEW,
                ).values_list("article_id", flat=True)
                queryset = queryset.exclude(id__in=viewed_ids)

            articles = list(
                queryset.select_related("source")
                .prefetch_related("categories")
                .order_by("-published_at")[:limit],
            )

            # Add metadata
            for article in articles:
                article.relevance_score = 0.5  # Default score for fallback
                article.recommendation_reason = "From your preferred categories"

            return articles

        except UserProfile.DoesNotExist:
            # No user profile, return latest articles
            articles = list(
                Article.objects.published()
                .select_related("source")
                .order_by("-published_at")[:limit],
            )
            for article in articles:
                article.relevance_score = 0.5
                article.recommendation_reason = "Latest articles"
            return articles

    def _get_recommendation_reason(self, article: Article, user_id: int) -> str:
        """
        Generate a human-readable recommendation reason.

        Args:
            article: Recommended article
            user_id: User ID

        Returns:
            Recommendation reason string
        """
        # Check if based on category preference
        try:
            user_profile = UserProfile.objects.get(user_id=user_id)
            preferred_category_codes = user_profile.get_preferred_category_codes()

            # Check source category
            if article.source.primary_category in preferred_category_codes:
                category_name = dict(article.source.CATEGORY_CHOICES).get(
                    article.source.primary_category,
                    article.source.primary_category,
                )
                return f"Based on your interest in {category_name}"

            # Check article categories
            article_categories = article.categories.all()
            for category in article_categories:
                if category.slug in preferred_category_codes:
                    return f"Based on your interest in {category.name}"
        except UserProfile.DoesNotExist:
            pass

        # Check for similar articles read
        article_categories = article.categories.all()
        if article_categories:
            recent_similar = (
                UserInteraction.objects.filter(
                    user_id=user_id,
                    article__categories__in=article_categories,
                    action=UserInteraction.ActionType.VIEW,
                )
                .select_related("article")
                .order_by("-created")
                .first()
            )

            if recent_similar:
                return f"Similar to '{recent_similar.article.title[:30]}...'"

        return "Recommended for you"
