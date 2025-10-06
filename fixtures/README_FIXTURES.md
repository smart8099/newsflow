# NewsFlow Database Fixtures

This directory contains database fixtures for populating your NewsFlow installation with **complete production-ready sample data**.

## Loading Order

Load the fixtures in the following order to maintain referential integrity:

```bash
# 1. Load Categories first (required by articles and user preferences)
uv run python manage.py loaddata fixtures/001_categories.json

# 2. Load ALL News Sources (31 sources - required by articles)
uv run python manage.py loaddata fixtures/002_all_news_sources.json

# 3. Load ALL Sample Articles (567 articles - requires categories and sources)
uv run python manage.py loaddata fixtures/003_all_articles.json

# 4. Load ALL Article-Category relationships
uv run python manage.py loaddata fixtures/004_all_article_categories.json

# 5. Load Sample Users (required by profiles and interactions)
uv run python manage.py loaddata fixtures/005_sample_users.json

# 6. Load User Profiles (requires users)
uv run python manage.py loaddata fixtures/006_user_profiles.json

# 7. Load User Interactions (requires users and articles)
uv run python manage.py loaddata fixtures/007_user_interactions.json

# 8. Load User Preferences (requires profiles, categories, and sources)
uv run python manage.py loaddata fixtures/008_user_preferences.json
```

## Quick Load All

To load all fixtures at once (recommended for development):

```bash
cd /path/to/newsflow
uv run python manage.py loaddata \
  fixtures/001_categories.json \
  fixtures/002_all_news_sources.json \
  fixtures/003_all_articles.json \
  fixtures/004_all_article_categories.json \
  fixtures/005_sample_users.json \
  fixtures/006_user_profiles.json \
  fixtures/007_user_interactions.json \
  fixtures/008_user_preferences.json
```

## Fixture Contents

### 001_categories.json
- 10 news categories: Technology, Business, Politics, Sports, Entertainment, Health, Science, World, General, Environment
- Each category includes name, slug, description, color, icon, and sort order

### 002_all_news_sources.json ⭐ **COMPLETE DATASET**
- **31 major news sources** from various categories and countries
- Includes: TechCrunch, BBC News, CNN, Reuters, The Verge, ESPN, Politico, National Geographic, The Hollywood Reporter, WebMD, and 21 more
- Each source includes RSS feeds, scraping configuration, credibility scores, and bias ratings
- Real production-ready sources for impressive demo

### 003_all_articles.json ⭐ **COMPLETE DATASET**
- **567 real articles** scraped from actual news sources
- Comprehensive coverage across all categories
- Real content with proper metadata, sentiment scores, and view counts
- Articles linked to appropriate news sources for realistic demonstration

### 004_all_article_categories.json
- **Complete many-to-many relationships** linking all 567 articles to their appropriate categories

### 005_sample_users.json
- 6 sample users including 1 admin user
- Diverse user profiles with realistic names and email addresses
- **Note**: All users have dummy passwords. Change passwords before production use.

### 006_user_profiles.json
- User profile settings for all sample users
- Theme preferences, reading speeds, notification settings
- Onboarding status and preferences

### 007_user_interactions.json
- 15 sample user interactions (views, likes, shares, bookmarks)
- Realistic interaction patterns for recommendation engine testing

### 008_user_preferences.json
- User category and source preferences for personalized recommendations
- Many-to-many relationships between users and their preferred content

## Production Deployment

For production deployment:

1. **Essential fixtures (minimum required)**:
   - 001_categories.json
   - 002_news_sources.json

2. **Optional demo content**:
   - Skip user and article fixtures for clean production deployment
   - Load only if you want demo content for testing

3. **Security considerations**:
   - Sample users have dummy passwords - change or remove before production
   - Admin user (admin@newsflow.com) should be removed or password changed
   - Consider creating your own admin user instead

## Custom Data

To create your own fixtures:

```bash
# Export current data to fixtures
uv run python manage.py dumpdata news.Category --indent=2 > custom_categories.json
uv run python manage.py dumpdata news.NewsSource --indent=2 > custom_sources.json
```

## Troubleshooting

**IntegrityError**: Ensure you load fixtures in the correct order
**Duplicate key errors**: Clear the database before loading: `uv run python manage.py flush`
**Missing dependencies**: Make sure all migrations are applied: `uv run python manage.py migrate`
