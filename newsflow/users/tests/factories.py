from collections.abc import Sequence
from typing import Any

from factory import Faker
from factory import LazyFunction
from factory import SubFactory
from factory import post_generation
from factory.django import DjangoModelFactory

from newsflow.users.models import User
from newsflow.users.models import UserProfile


class UserFactory(DjangoModelFactory[User]):
    email = Faker("email")
    name = Faker("name")

    @post_generation
    def password(self, create: bool, extracted: Sequence[Any], **kwargs):  # noqa: FBT001
        password = (
            extracted
            if extracted
            else Faker(
                "password",
                length=42,
                special_chars=True,
                digits=True,
                upper_case=True,
                lower_case=True,
            ).evaluate(None, None, extra={"locale": None})
        )
        self.set_password(password)

    @classmethod
    def _after_postgeneration(cls, instance, create, results=None):
        """Save again the instance if creating and at least one hook ran."""
        if create and results and not cls._meta.skip_postgeneration_save:
            # Some post-generation hooks ran, and may have modified us.
            instance.save()

    class Meta:
        model = User
        django_get_or_create = ["email"]


class UserProfileFactory(DjangoModelFactory[UserProfile]):
    """Factory for creating UserProfile instances."""

    user = SubFactory(UserFactory)
    theme_preference = Faker("random_element", elements=["light", "dark", "system"])
    reading_speed = Faker("random_int", min=150, max=300)

    notification_preferences = LazyFunction(
        lambda: {
            "email_notifications": Faker("boolean").evaluate(
                None,
                None,
                {"locale": "en"},
            ),
            "breaking_news": Faker("boolean").evaluate(None, None, {"locale": "en"}),
            "daily_digest": Faker("boolean").evaluate(None, None, {"locale": "en"}),
            "weekly_summary": Faker("boolean").evaluate(None, None, {"locale": "en"}),
            "article_recommendations": Faker("boolean").evaluate(
                None,
                None,
                {"locale": "en"},
            ),
            "category_updates": Faker("boolean").evaluate(None, None, {"locale": "en"}),
        },
    )

    @post_generation
    def preferred_categories(self, create: bool, extracted: Sequence[Any], **kwargs):
        """Add preferred categories to the profile."""
        if not create:
            return

        if extracted:
            # If specific categories were passed, use them
            for category in extracted:
                self.preferred_categories.add(category)
        else:
            # Otherwise, add 2-5 random categories
            from newsflow.core.tests.factories import CategoryFactory

            num_categories = Faker("random_int", min=2, max=5).evaluate(
                None,
                None,
                {"locale": "en"},
            )
            categories = CategoryFactory.create_batch(num_categories)
            for category in categories:
                self.preferred_categories.add(category)

    class Meta:
        model = UserProfile
