#!/usr/bin/env python
"""
Simple test script for the recommendation system.

This script demonstrates the key functionality of the NewsFlow recommendation engine.
"""

import os
import sys

import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from newsflow.news.models import Article
from newsflow.news.models import Category
from newsflow.recommendations.analytics import UserPreferenceAnalyzer
from newsflow.recommendations.engine import ContentBasedRecommender
from newsflow.recommendations.filters import CategoryBasedFilter
from newsflow.recommendations.hybrid import HybridRecommender
from newsflow.users.models import User


def test_basic_functionality():
    """Test basic recommendation system functionality."""
    print("🧪 Testing NewsFlow Recommendation System")
    print("=" * 50)

    # Check if we have data
    article_count = Article.objects.count()
    category_count = Category.objects.count()
    user_count = User.objects.count()

    print("📊 Database Status:")
    print(f"   Articles: {article_count}")
    print(f"   Categories: {category_count}")
    print(f"   Users: {user_count}")

    if article_count == 0:
        print(
            "❌ No articles found. Please run 'python manage.py scrape_news --all-sources' first.",
        )
        return False

    if user_count == 0:
        print("❌ No users found. Please create a superuser first.")
        return False

    print("\n🔍 Testing Content-Based Recommender...")
    try:
        content_recommender = ContentBasedRecommender()

        # Test article vectorization
        article_vectors, article_ids = content_recommender._build_article_vectors()
        print(f"   ✅ Built vectors for {len(article_ids)} articles")

        # Test similar articles
        if article_ids:
            sample_article_id = article_ids[0]
            similar_articles = content_recommender.get_similar_articles(
                sample_article_id,
                limit=3,
            )
            print(f"   ✅ Found {len(similar_articles)} similar articles")

    except Exception as e:
        print(f"   ❌ Content-based recommender failed: {e}")
        return False

    print("\n📈 Testing Category-Based Filter...")
    try:
        category_filter = CategoryBasedFilter()

        # Test trending articles
        trending = category_filter.get_trending_globally(limit=5)
        print(f"   ✅ Found {len(trending)} trending articles")

        # Test category-specific trending
        if category_count > 0:
            first_category = Category.objects.first()
            category_trending = category_filter.get_trending_in_category(
                first_category.id,
                limit=3,
            )
            print(
                f"   ✅ Found {len(category_trending)} trending articles in {first_category.name}",
            )

    except Exception as e:
        print(f"   ❌ Category filter failed: {e}")
        return False

    print("\n🎯 Testing Hybrid Recommender...")
    try:
        hybrid_recommender = HybridRecommender()

        # Test explore feed (no user required)
        explore_feed = hybrid_recommender.get_explore_feed(limit=5)
        print(f"   ✅ Generated explore feed with {len(explore_feed)} articles")

        # Test personalized feed (requires user)
        if user_count > 0:
            first_user = User.objects.first()
            personalized_feed = hybrid_recommender.get_personalized_feed(
                first_user.id,
                limit=5,
            )
            print(
                f"   ✅ Generated personalized feed with {len(personalized_feed)} articles",
            )

    except Exception as e:
        print(f"   ❌ Hybrid recommender failed: {e}")
        return False

    print("\n📊 Testing User Analytics...")
    try:
        analyzer = UserPreferenceAnalyzer()

        if user_count > 0:
            first_user = User.objects.first()
            analytics = analyzer.analyze_reading_patterns(first_user.id, days=30)
            print(f"   ✅ Analyzed reading patterns for user {first_user.email}")
            print(f"       Articles read: {analytics['total_articles_read']}")
            print(f"       Categories explored: {len(analytics['categories'])}")

    except Exception as e:
        print(f"   ❌ User analytics failed: {e}")
        return False

    print("\n🚀 Testing Article Model Helper Methods...")
    try:
        if article_count > 0:
            sample_article = Article.objects.first()
            engagement_score = sample_article.get_engagement_score()
            similar_articles = sample_article.get_similar(limit=3)

            print(f"   ✅ Article '{sample_article.title[:50]}...'")
            print(f"       Engagement score: {engagement_score}")
            print(f"       Similar articles: {len(similar_articles)}")

    except Exception as e:
        print(f"   ❌ Article helper methods failed: {e}")
        return False

    print("\n🎉 All tests passed! Recommendation system is working correctly.")
    print("\n📝 Next Steps:")
    print(
        "   1. Generate test data: python manage.py generate_test_data --users 5 --interactions 100",
    )
    print("   2. Test API endpoints with a REST client")
    print("   3. Set up Celery for background tasks")
    print("   4. Monitor performance and tune parameters")

    return True


def show_api_endpoints():
    """Show available API endpoints."""
    print("\n🌐 Available API Endpoints:")
    print("   GET  /api/recommendations/feed/           - Personalized feed")
    print("   GET  /api/recommendations/similar/<id>/   - Similar articles")
    print("   GET  /api/recommendations/trending/       - Trending articles")
    print("   GET  /api/recommendations/explore/        - Exploration feed")
    print("   GET  /api/recommendations/analytics/      - User analytics")
    print("   POST /api/recommendations/interaction/    - Record interaction")


if __name__ == "__main__":
    success = test_basic_functionality()

    if success:
        show_api_endpoints()

        print("\n🔧 Management Commands:")
        print("   python manage.py generate_test_data --help")
        print("   python manage.py validate_feeds --help")

        sys.exit(0)
    else:
        print("\n❌ Tests failed. Please check the errors above.")
        sys.exit(1)
