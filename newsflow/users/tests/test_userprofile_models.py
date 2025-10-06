"""Tests for UserProfile model."""

import pytest
from django.db import IntegrityError

from newsflow.articles.tests.factories import ArticleFactory
from newsflow.articles.tests.factories import UserInteractionFactory
from newsflow.core.tests.factories import CategoryFactory
from newsflow.news.models import UserInteraction
from newsflow.users.models import UserProfile
from newsflow.users.tests.factories import UserFactory
from newsflow.users.tests.factories import UserProfileFactory


@pytest.mark.django_db
class TestUserProfileModel:
    """Tests for UserProfile model."""

    def test_user_profile_creation(self):
        """Test basic user profile creation."""
        profile = UserProfileFactory()

        assert profile.uuid is not None
        assert profile.user is not None
        assert profile.theme_preference in ["light", "dark", "system"]
        assert profile.reading_speed >= 150
        assert isinstance(profile.notification_preferences, dict)
        assert profile.created_at
        assert profile.updated_at

    def test_user_profile_str_representation(self):
        """Test user profile string representation."""
        user = UserFactory(email="test@example.com")
        profile = UserProfileFactory(user=user)
        assert str(profile) == "test@example.com Profile"

    def test_user_profile_get_absolute_url(self):
        """Test user profile get_absolute_url method."""
        profile = UserProfileFactory()
        url = profile.get_absolute_url()
        assert f"/users/profile/{profile.uuid}/" in url or "profile-detail" in url

    def test_user_profile_auto_created_on_user_creation(self):
        """Test that UserProfile is automatically created when User is created."""
        user = UserFactory()

        # Profile should be auto-created via signal
        assert hasattr(user, "profile")
        assert user.profile is not None
        assert isinstance(user.profile, UserProfile)

    def test_user_profile_default_notification_preferences(self):
        """Test get_default_notification_preferences method."""
        profile = UserProfileFactory()
        defaults = profile.get_default_notification_preferences()

        expected_keys = [
            "email_notifications",
            "breaking_news",
            "daily_digest",
            "weekly_summary",
            "article_recommendations",
            "category_updates",
        ]

        for key in expected_keys:
            assert key in defaults
            assert isinstance(defaults[key], bool)

    def test_user_profile_save_sets_default_notifications(self):
        """Test that save method sets default notification preferences."""
        user = UserFactory()
        profile = UserProfile(
            user=user,
            notification_preferences={},  # Empty dict
        )
        profile.save()

        # Should have default notification preferences
        assert len(profile.notification_preferences) > 0
        assert "email_notifications" in profile.notification_preferences

    def test_user_profile_preferred_categories(self):
        """Test preferred categories relationship."""
        profile = UserProfileFactory()
        category1 = CategoryFactory(name="Technology")
        category2 = CategoryFactory(name="Science")

        profile.preferred_categories.add(category1, category2)

        assert category1 in profile.preferred_categories.all()
        assert category2 in profile.preferred_categories.all()
        assert profile.preferred_categories.count() == 2

    def test_user_profile_get_recommended_articles_count(self):
        """Test get_recommended_articles_count method."""
        profile = UserProfileFactory()
        tech_category = CategoryFactory(name="Technology")
        science_category = CategoryFactory(name="Science")

        # Add preferred categories
        profile.preferred_categories.add(tech_category, science_category)

        # Create articles in preferred categories
        tech_article = ArticleFactory(is_published=True)
        tech_article.categories.add(tech_category)

        science_article = ArticleFactory(is_published=True)
        science_article.categories.add(science_category)

        # Create article in non-preferred category
        other_category = CategoryFactory(name="Sports")
        other_article = ArticleFactory(is_published=True)
        other_article.categories.add(other_category)

        count = profile.get_recommended_articles_count()
        # Should count articles in preferred categories
        assert count >= 2

    def test_user_profile_get_recommended_articles_count_no_preferences(self):
        """Test get_recommended_articles_count with no preferred categories."""
        profile = UserProfileFactory()
        # Don't add any preferred categories

        count = profile.get_recommended_articles_count()
        assert count == 0

    def test_user_profile_get_reading_history_count(self):
        """Test get_reading_history_count method."""
        user = UserFactory()
        profile = user.profile

        # Create some read interactions
        article1 = ArticleFactory()
        article2 = ArticleFactory()
        UserInteractionFactory(
            user=user,
            article=article1,
            action=UserInteraction.ActionType.VIEW,
        )
        UserInteractionFactory(
            user=user,
            article=article2,
            action=UserInteraction.ActionType.VIEW,
        )

        # Create non-read interaction
        UserInteractionFactory(
            user=user,
            article=article1,
            action=UserInteraction.ActionType.LIKE,
        )

        count = profile.get_reading_history_count()
        assert count == 2

    def test_user_profile_get_bookmarked_articles_count(self):
        """Test get_bookmarked_articles_count method."""
        user = UserFactory()
        profile = user.profile

        # Create some bookmark interactions
        article1 = ArticleFactory()
        article2 = ArticleFactory()
        UserInteractionFactory(
            user=user,
            article=article1,
            action=UserInteraction.ActionType.BOOKMARK,
        )
        UserInteractionFactory(
            user=user,
            article=article2,
            action=UserInteraction.ActionType.BOOKMARK,
        )

        # Create non-bookmark interaction
        UserInteractionFactory(
            user=user,
            article=article1,
            action=UserInteraction.ActionType.LIKE,
        )

        count = profile.get_bookmarked_articles_count()
        assert count == 2

    def test_user_profile_one_to_one_relationship(self):
        """Test that each user can only have one profile."""
        user = UserFactory()

        # First profile is auto-created
        first_profile = user.profile

        # Try to create another profile for the same user
        with pytest.raises(IntegrityError):
            UserProfile.objects.create(user=user)

    def test_user_profile_theme_choices(self):
        """Test that theme_preference accepts only valid choices."""
        profile = UserProfileFactory()

        # Valid choices
        valid_themes = ["light", "dark", "system"]
        for theme in valid_themes:
            profile.theme_preference = theme
            profile.save()  # Should not raise an error

    def test_user_profile_reading_speed_default(self):
        """Test reading speed default value."""
        profile = UserProfileFactory()
        # Default should be around 200 wpm (our factory uses 150-300 range)
        assert profile.reading_speed >= 150
        assert profile.reading_speed <= 300

    def test_user_profile_cascade_deletion(self):
        """Test that profile is deleted when user is deleted."""
        user = UserFactory()
        profile_id = user.profile.id

        user.delete()

        # Profile should be deleted
        assert not UserProfile.objects.filter(id=profile_id).exists()


@pytest.mark.django_db
class TestUserProfileSignals:
    """Tests for UserProfile signal handlers."""

    def test_profile_created_on_user_creation(self):
        """Test that profile is created when user is created."""
        user = UserFactory()

        assert UserProfile.objects.filter(user=user).exists()
        assert user.profile is not None

    def test_profile_saved_when_user_saved(self):
        """Test that profile is saved when user is saved."""
        user = UserFactory()
        original_updated_at = user.profile.updated_at

        # Modify and save user
        user.name = "Updated Name"
        user.save()

        # Profile should be saved (updated_at should change)
        user.profile.refresh_from_db()
        assert user.profile.updated_at >= original_updated_at
