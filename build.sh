#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "🚀 Starting NewsFlow build process..."

# Install Python dependencies
echo "📦 Installing Python dependencies with uv..."
uv sync --frozen

# Install Node.js dependencies
echo "📦 Installing Node.js dependencies..."
npm ci

# Build CSS assets
echo "🎨 Building CSS assets..."
npm run build-css

# Collect static files
echo "📁 Collecting static files..."
uv run python manage.py collectstatic --noinput --clear

# Run database migrations
echo "🗃️ Running database migrations..."
uv run python manage.py migrate

# Download NLTK data if needed
echo "🧠 Setting up NLTK data..."
uv run python -c "
import os
import nltk
from pathlib import Path

# Set NLTK data path to project directory
nltk_data_dir = Path('nltk_data')
nltk_data_dir.mkdir(exist_ok=True)
nltk.data.path.insert(0, str(nltk_data_dir))

# Download required NLTK data
try:
    nltk.download('punkt', download_dir=str(nltk_data_dir), quiet=True)
    nltk.download('stopwords', download_dir=str(nltk_data_dir), quiet=True)
    nltk.download('wordnet', download_dir=str(nltk_data_dir), quiet=True)
    nltk.download('vader_lexicon', download_dir=str(nltk_data_dir), quiet=True)
    print('✅ NLTK data downloaded successfully')
except Exception as e:
    print(f'⚠️ NLTK download warning: {e}')
"

# Load fixture data (only if no articles exist)
echo "📊 Loading sample data if needed..."
uv run python -c "
from newsflow.news.models import Article
if Article.objects.count() == 0:
    print('Loading fixture data...')
    import subprocess
    fixtures = [
        'fixtures/001_categories.json',
        'fixtures/002_all_news_sources.json',
        'fixtures/003_all_articles.json',
        'fixtures/004_all_article_categories.json',
        'fixtures/005_sample_users.json',
        'fixtures/006_user_profiles.json',
        'fixtures/007_user_interactions.json',
        'fixtures/008_user_preferences.json'
    ]
    for fixture in fixtures:
        try:
            subprocess.run(['uv', 'run', 'python', 'manage.py', 'loaddata', fixture], check=True)
            print(f'✅ Loaded {fixture}')
        except subprocess.CalledProcessError as e:
            print(f'⚠️ Warning loading {fixture}: {e}')
else:
    print('✅ Database already has data, skipping fixtures')
"

echo "✅ Build completed successfully!"
