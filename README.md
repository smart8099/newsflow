# NewsFlow - AI-Powered News Aggregation Platform

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.1.12-green.svg)](https://djangoproject.com)
[![Built with Cookiecutter Django](https://img.shields.io/badge/built%20with-Cookiecutter%20Django-ff69b4.svg?logo=cookiecutter)](https://github.com/cookiecutter/cookiecutter-django/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License](https://img.shields.io/badge/License-MIT-red.svg)](LICENSE)

NewsFlow is a sophisticated AI-powered news aggregation platform that curates personalized news experiences from 100+ global sources. Built with Django 5.1, it features intelligent content-based recommendations, real-time news scraping, and a modern responsive interface.

## 🚀 Features

### **Core Features**
- **AI-Powered Recommendations**: Content-based filtering using TF-IDF and cosine similarity
- **Multi-Source Aggregation**: Scrapes from 100+ RSS feeds and news APIs
- **Real-time Updates**: Automated news collection with Celery workers
- **Advanced Search**: Full-text search with PostgreSQL and auto-suggestions
- **User Interaction Tracking**: Comprehensive analytics for personalization

### **User Experience**
- **Responsive Design**: Mobile-first interface with Tailwind CSS
- **Dark/Light/System Theme**: Automatic theme switching
- **Infinite Scroll**: Seamless content loading with HTMX
- **Bookmark System**: Works for authenticated and anonymous users
- **Social Sharing**: Integrated sharing across multiple platforms

### **Content Management**
- **10 News Categories**: Technology, Business, Politics, Sports, Entertainment, Health, Science, World, General, Environment
- **Sentiment Analysis**: Automatic article sentiment classification
- **Reading Time Estimation**: Smart reading time calculation
- **Content Filtering**: Advanced filtering by date, source, category, and sentiment

### **Security & Authentication**
- **Email-Based Auth**: Custom user model with django-allauth
- **Multi-Factor Authentication**: TOTP and backup codes support
- **Email Verification**: Mandatory email verification
- **Social Login**: Support for Google, GitHub, and more (configurable)

## 🏗️ Architecture

### **Backend Stack**
- **Django 5.1.12**: Web framework with modern async support
- **PostgreSQL**: Primary database with full-text search
- **Redis**: Caching and Celery message broker
- **Celery**: Distributed task queue for background jobs
- **uv**: Fast Python package manager

### **Frontend Stack**
- **Tailwind CSS**: Utility-first CSS framework
- **HTMX**: Dynamic content without JavaScript complexity
- **Flowbite**: Pre-built UI components
- **Vanilla JavaScript**: Lightweight interactivity

### **AI/ML Components**
- **scikit-learn**: TF-IDF vectorization and cosine similarity
- **NLTK**: Natural language processing for content analysis
- **NumPy**: Numerical computations for recommendations

### **Infrastructure**
- **WhiteNoise**: Static file serving
- **django-compressor**: Asset compression and optimization
- **Sentry**: Error tracking and performance monitoring (optional)

## 📋 Requirements

- **Python**: 3.12+
- **Node.js**: 18+ (for Tailwind CSS)
- **PostgreSQL**: 14+
- **Redis**: 6+

## 🚀 Quick Start

### 1. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/your-username/newsflow.git
cd newsflow

# Install Python dependencies with uv
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync

# Install Node.js dependencies
npm install
```

### 2. Environment Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit configuration
nano .env
```

**Required Environment Variables:**
```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/newsflow

# Redis
REDIS_URL=redis://localhost:6379/0

# Email (for user verification)
EMAIL_HOST=smtp.gmail.com
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# Django
SECRET_KEY=your-super-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

### 3. Database Setup

```bash
# Create database
createdb newsflow

# Run migrations
uv run python manage.py migrate

# Load initial data - Complete production dataset!
uv run python manage.py loaddata fixtures/001_categories.json
uv run python manage.py loaddata fixtures/002_all_news_sources.json
uv run python manage.py loaddata fixtures/003_all_articles.json
uv run python manage.py loaddata fixtures/004_all_article_categories.json

# Optional: Load sample users and interactions for AI recommendations demo
uv run python manage.py loaddata fixtures/005_sample_users.json
uv run python manage.py loaddata fixtures/006_user_profiles.json
uv run python manage.py loaddata fixtures/007_user_interactions.json
uv run python manage.py loaddata fixtures/008_user_preferences.json

# Create superuser
uv run python manage.py createsuperuser
```

### 4. Start Development

```bash
# Start all services (recommended)
python dev.py

# Or start separately:
# Terminal 1: Django server
uv run python manage.py runserver

# Terminal 2: CSS watcher
npm run dev-css

# Terminal 3: Celery worker
cd newsflow && uv run celery -A config.celery_app worker -l info

# Terminal 4: Celery beat (scheduler)
cd newsflow && uv run celery -A config.celery_app beat
```

Visit `http://localhost:8000` to see your NewsFlow installation!

## 📊 Production-Ready Sample Data 🎯

NewsFlow comes with **complete production-ready fixtures** perfect for impressing recruiters and demonstrating AI capabilities:

### Complete Dataset Included
- **31 real news sources** from major publications
- **567 actual articles** scraped from live feeds
- **Full categorization** and metadata
- **AI recommendation data** with user interactions
- **User profiles** with realistic preferences

### Already Loaded!
If you followed the setup instructions above, you already have a fully populated database ready for demonstration. No additional setup required!

### What This Gives You
- **Immediate impressive demo** - Launch and show a fully functional news platform
- **AI recommendations working** - Real user interaction data powers the ML algorithms
- **Complete content coverage** - Articles across Technology, Business, Politics, Sports, Entertainment, Health, Science, World News, and Environment
- **Professional appearance** - Real content from recognizable sources like BBC, CNN, TechCrunch, Reuters, etc.

## Basic Commands

### Setting Up Your Users

- To create a **normal user account**, just go to Sign Up and fill out the form. **Email verification is optional** - you can use the account immediately after signup for easy demo purposes.

- **Sample users included**: The fixtures provide 6 demo users (including 1 admin) ready for testing AI recommendations

- To create a **superuser account**, use this command:

      uv run python manage.py createsuperuser

For convenience, you can keep your normal user logged in on Chrome and your superuser logged in on Firefox (or similar), so that you can see how the site behaves for both kinds of users.

### Type checks

Running type checks with mypy:

    uv run mypy newsflow

### Test coverage

To run the tests, check your test coverage, and generate an HTML coverage report:

    uv run coverage run -m pytest
    uv run coverage html
    uv run open htmlcov/index.html

#### Running tests with pytest

    uv run pytest

### Live reloading and Sass CSS compilation

Moved to [Live reloading and SASS compilation](https://cookiecutter-django.readthedocs.io/en/latest/2-local-development/developing-locally.html#using-webpack-or-gulp).

### Celery

This app comes with Celery.

To run a celery worker:

```bash
cd newsflow
uv run celery -A config.celery_app worker -l info
```

Please note: For Celery's import magic to work, it is important _where_ the celery commands are run. If you are in the same folder with _manage.py_, you should be right.

To run [periodic tasks](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html), you'll need to start the celery beat scheduler service. You can start it as a standalone process:

```bash
cd newsflow
uv run celery -A config.celery_app beat
```

or you can embed the beat service inside a worker with the `-B` option (not recommended for production use):

```bash
cd newsflow
uv run celery -A config.celery_app worker -B -l info
```

### Email Server

In development, it is often nice to be able to see emails that are being sent from your application. If you choose to use [Mailpit](https://github.com/axllent/mailpit) when generating the project a local SMTP server with a web interface will be available.

1.  [Download the latest Mailpit release](https://github.com/axllent/mailpit/releases) for your OS.

2.  Copy the binary file to the project root.

3.  Make it executable:

        chmod +x mailpit

4.  Spin up another terminal window and start it there:

        ./mailpit

5.  Check out <http://127.0.0.1:8025/> to see how it goes.

Now you have your own mail server running locally, ready to receive whatever you send it.

## Deployment

The following details how to deploy this application.
