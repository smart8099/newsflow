"""
Management command to generate test data for the recommendation system.

Creates sample user interactions, reading patterns, and preference data
to test the recommendation algorithms.
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from faker import Faker

from newsflow.news.models import Article
from newsflow.news.models import Category
from newsflow.news.models import UserInteraction
from newsflow.users.models import User
from newsflow.users.models import UserProfile

fake = Faker()


class Command(BaseCommand):
    help = "Generate test data for the recommendation system"

    def add_arguments(self, parser):
        parser.add_argument(
            "--users",
            type=int,
            default=10,
            help="Number of test users to create (default: 10)",
        )

        parser.add_argument(
            "--interactions",
            type=int,
            default=500,
            help="Number of interactions to create per user (default: 500)",
        )

        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days of history to generate (default: 30)",
        )

        parser.add_argument(
            "--clean",
            action="store_true",
            help="Clean existing test data before generating new data",
        )

    def handle(self, *args, **options):
        """Generate test data for recommendations."""
        self.stdout.write(self.style.SUCCESS("Starting test data generation..."))

        # Clean existing test data if requested
        if options["clean"]:
            self.clean_test_data()

        # Get configuration
        num_users = options["users"]
        interactions_per_user = options["interactions"]
        days_history = options["days"]

        # Get existing data
        articles = list(Article.objects.all()[:1000])  # Limit to 1000 articles
        categories = list(Category.objects.all())

        if not articles:
            self.stdout.write(
                self.style.ERROR(
                    "No articles found. Please scrape some articles first.",
                ),
            )
            return

        if not categories:
            self.stdout.write(
                self.style.ERROR(
                    "No categories found. Please create categories first.",
                ),
            )
            return

        self.stdout.write(
            f"Found {len(articles)} articles and {len(categories)} categories",
        )

        # Create test users
        test_users = self.create_test_users(num_users, categories)

        # Generate interactions
        self.generate_interactions(
            test_users,
            articles,
            interactions_per_user,
            days_history,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Test data generation completed!\n"
                f"Created {len(test_users)} users with {interactions_per_user} interactions each",
            ),
        )

    def clean_test_data(self):
        """Clean existing test data."""
        self.stdout.write("Cleaning existing test data...")

        # Delete test users and their data
        test_users = User.objects.filter(email__startswith="test_user_")

        # Delete interactions
        UserInteraction.objects.filter(user__in=test_users).delete()

        # Delete profiles
        UserProfile.objects.filter(user__in=test_users).delete()

        # Delete users
        user_count = test_users.count()
        test_users.delete()

        self.stdout.write(f"Cleaned {user_count} test users and their data")

    def create_test_users(self, num_users, categories):
        """Create test users with different reading profiles."""
        test_users = []

        # Define user archetypes
        archetypes = [
            {
                "name": "Tech Enthusiast",
                "preferred_categories": ["Technology", "Science"],
                "reading_velocity": "high",
                "engagement_level": "high",
            },
            {
                "name": "News Junkie",
                "preferred_categories": ["Politics", "World News", "Business"],
                "reading_velocity": "very_high",
                "engagement_level": "medium",
            },
            {
                "name": "Sports Fan",
                "preferred_categories": ["Sports"],
                "reading_velocity": "medium",
                "engagement_level": "high",
            },
            {
                "name": "Health Conscious",
                "preferred_categories": ["Health", "Science"],
                "reading_velocity": "medium",
                "engagement_level": "medium",
            },
            {
                "name": "Entertainment Lover",
                "preferred_categories": ["Entertainment", "Sports"],
                "reading_velocity": "low",
                "engagement_level": "high",
            },
            {
                "name": "Business Professional",
                "preferred_categories": ["Business", "Technology", "Politics"],
                "reading_velocity": "high",
                "engagement_level": "low",
            },
            {
                "name": "Casual Reader",
                "preferred_categories": [],  # No specific preferences
                "reading_velocity": "low",
                "engagement_level": "low",
            },
        ]

        for i in range(num_users):
            # Select archetype
            archetype = random.choice(archetypes)

            # Create user
            user = User.objects.create_user(
                email=f"test_user_{i}@example.com",
                name=f"Test User {i}",
                password="testpass123",
            )

            # Create user profile
            profile = UserProfile.objects.create(user=user)

            # Set preferred categories
            if archetype["preferred_categories"]:
                available_categories = [
                    cat
                    for cat in categories
                    if cat.name in archetype["preferred_categories"]
                ]
                if available_categories:
                    profile.preferred_categories.set(
                        random.sample(
                            available_categories,
                            min(len(available_categories), 3),
                        ),
                    )

            # Add some reading preferences
            profile.reading_preferences = {
                "archetype": archetype["name"],
                "reading_velocity": archetype["reading_velocity"],
                "engagement_level": archetype["engagement_level"],
                "created_for_testing": True,
            }
            profile.save()

            test_users.append(
                {
                    "user": user,
                    "profile": profile,
                    "archetype": archetype,
                },
            )

            self.stdout.write(f"Created user: {user.email} ({archetype['name']})")

        return test_users

    def generate_interactions(
        self,
        test_users,
        articles,
        interactions_per_user,
        days_history,
    ):
        """Generate realistic user interactions."""
        self.stdout.write("Generating user interactions...")

        from newsflow.news.models import UserInteraction

        interaction_types = [
            UserInteraction.ActionType.VIEW,
            UserInteraction.ActionType.LIKE,
            UserInteraction.ActionType.SHARE,
            UserInteraction.ActionType.BOOKMARK,
            UserInteraction.ActionType.COMMENT,
        ]
        type_weights = [70, 15, 5, 7, 3]  # Weighted probabilities

        for user_data in test_users:
            user = user_data["user"]
            archetype = user_data["archetype"]
            profile = user_data["profile"]

            # Get user's preferred categories
            preferred_categories = list(profile.preferred_categories.all())

            # Filter articles based on preferences
            if preferred_categories:
                # 80% from preferred categories, 20% random
                preferred_articles = [
                    a for a in articles if a.category in preferred_categories
                ]

                if preferred_articles:
                    user_articles = random.choices(
                        preferred_articles,
                        k=int(interactions_per_user * 0.8),
                    ) + random.choices(articles, k=int(interactions_per_user * 0.2))
                else:
                    user_articles = random.choices(articles, k=interactions_per_user)
            else:
                # Casual reader - completely random
                user_articles = random.choices(articles, k=interactions_per_user)

            # Generate interactions over time
            for i, article in enumerate(user_articles):
                # Random time within the history period
                days_ago = random.uniform(0, days_history)
                interaction_time = timezone.now() - timedelta(days=days_ago)

                # Choose interaction type based on archetype
                if archetype["engagement_level"] == "high":
                    # More likely to like/share
                    weights = [60, 25, 10, 5, 0]
                elif archetype["engagement_level"] == "medium":
                    weights = [75, 15, 5, 5, 0]
                else:
                    # Low engagement - mostly views
                    weights = [90, 5, 2, 3, 0]

                interaction_type = random.choices(interaction_types, weights=weights)[0]

                # Calculate reading time for views
                reading_time = None
                if interaction_type == UserInteraction.ActionType.VIEW:
                    if archetype["reading_velocity"] == "very_high":
                        reading_time = random.randint(30, 120)  # 30s - 2min
                    elif archetype["reading_velocity"] == "high":
                        reading_time = random.randint(60, 300)  # 1-5min
                    elif archetype["reading_velocity"] == "medium":
                        reading_time = random.randint(120, 600)  # 2-10min
                    else:  # low
                        reading_time = random.randint(30, 180)  # 30s - 3min

                # Create interaction
                UserInteraction.objects.create(
                    user=user,
                    article=article,
                    interaction_type=interaction_type,
                    reading_time=reading_time,
                    created_at=interaction_time,
                )

                # Progress indicator
                if (i + 1) % 50 == 0:
                    self.stdout.write(
                        f"  {user.email}: {i + 1}/{interactions_per_user} interactions",
                    )

            self.stdout.write(
                f"Generated {interactions_per_user} interactions for {user.email}",
            )

    def simulate_reading_patterns(self, user_data, days_history):
        """Simulate realistic reading patterns (peak hours, streaks, etc.)."""
        # This could be extended to create more realistic patterns
        # like reading mostly in the morning, weekend patterns, etc.
