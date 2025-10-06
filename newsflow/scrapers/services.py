import logging
import random
import re
import socket
import time
from datetime import datetime
from datetime import timedelta
from urllib.parse import urlparse

import feedparser
import nltk
import requests
import tldextract
from dateutil import parser as date_parser
from django.conf import settings
from django.db import models
from django.db import transaction
from django.utils import timezone
from newspaper import Article as NewspaperArticle
from newspaper import Config
from newspaper import build
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError
from requests.exceptions import HTTPError
from requests.exceptions import RequestException
from requests.exceptions import Timeout
from urllib3.util.retry import Retry

from newsflow.news.models import Article
from newsflow.news.models import Category
from newsflow.news.models import NewsSource

logger = logging.getLogger(__name__)

# User agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "NewsFlow/1.0 (+https://newsflow.com/bot)",
]

# Network-related exceptions to handle
NETWORK_EXCEPTIONS = (
    ConnectionError,
    Timeout,
    HTTPError,
    RequestException,
    socket.timeout,
    socket.gaierror,
)


class NewsScraperService:
    """
    Core service for scraping news articles from various sources.

    Supports RSS feeds, website scraping, and API integration.
    Includes quality validation, duplicate detection, and error handling.
    """

    def __init__(self):
        self.session = self._setup_session()
        self.timeout = getattr(settings, "SCRAPER_REQUEST_TIMEOUT", 30)
        self.retry_attempts = getattr(settings, "SCRAPER_RETRY_ATTEMPTS", 3)
        self.rate_limit = getattr(settings, "SCRAPER_RATE_LIMIT", 2)
        self.max_rate_limit_delay = getattr(
            settings,
            "SCRAPER_MAX_RATE_LIMIT_DELAY",
            60,
        )
        self.connection_timeout = getattr(settings, "SCRAPER_CONNECTION_TIMEOUT", 10)
        self.read_timeout = getattr(settings, "SCRAPER_READ_TIMEOUT", 30)

        # Request counters for rate limiting
        self.request_count = 0
        self.last_request_time = 0

        # Download required NLTK data if not present
        self._ensure_nltk_data()

        logger.info("NewsScraperService initialized with enhanced error handling")

    def _setup_session(self) -> requests.Session:
        """Setup requests session with retry strategy and timeouts."""
        session = requests.Session()

        # Setup retry strategy
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            backoff_factor=1,
            respect_retry_after_header=True,
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers
        session.headers.update(
            {
                "User-Agent": self._get_random_user_agent(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
        )

        return session

    def _get_random_user_agent(self) -> str:
        """Get a random user agent for request rotation."""
        return random.choice(USER_AGENTS)

    def _rotate_user_agent(self):
        """Rotate user agent for the session."""
        self.session.headers["User-Agent"] = self._get_random_user_agent()
        logger.debug(
            f"Rotated user agent: {self.session.headers['User-Agent'][:50]}...",
        )

    def _ensure_nltk_data(self):
        """Download required NLTK data for text processing."""
        required_data = [
            ("tokenizers/punkt", "punkt"),
            ("tokenizers/punkt_tab", "punkt_tab"),
            ("corpora/stopwords", "stopwords"),
        ]

        for data_path, download_name in required_data:
            try:
                nltk.data.find(data_path)
            except LookupError:
                logger.info(f"Downloading NLTK {download_name}...")
                try:
                    nltk.download(download_name, quiet=True)
                except Exception as e:
                    logger.warning(f"Failed to download NLTK {download_name}: {e}")

    def _get_newspaper_config(self, source: NewsSource) -> Config:
        """Get newspaper configuration for a source."""
        config = Config()
        config.language = source.language or "en"
        config.request_timeout = self.timeout
        config.browser_user_agent = self.session.headers["User-Agent"]

        # Custom headers from source configuration
        if source.headers:
            config.headers = source.headers

        return config

    def _rate_limit_delay(self):
        """Apply intelligent rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        # Base delay
        delay = self.rate_limit

        # Increase delay based on request frequency
        if time_since_last < 1:
            delay = min(delay * 2, self.max_rate_limit_delay)

        # Add some randomness to avoid thundering herd
        delay += random.uniform(0, 0.5)

        if delay > 0.1:  # Only log significant delays
            logger.debug(f"Rate limiting: sleeping for {delay:.2f} seconds")

        time.sleep(delay)
        self.last_request_time = time.time()
        self.request_count += 1

        # Rotate user agent periodically
        if self.request_count % 10 == 0:
            self._rotate_user_agent()

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL for duplicate detection."""
        try:
            extracted = tldextract.extract(url)
            return f"{extracted.domain}.{extracted.suffix}"
        except Exception:
            return urlparse(url).netloc

    def _is_duplicate_article(self, url: str, title: str, source: NewsSource) -> bool:
        """
        Check if article is a duplicate based on URL or title similarity.
        """
        # Check exact URL match
        if Article.objects.filter(url=url).exists():
            return True

        # Check for similar titles within the same source (last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        similar_articles = Article.objects.filter(
            source=source,
            scraped_at__gte=week_ago,
        ).values_list("title", flat=True)

        # Simple fuzzy matching for titles
        title_words = set(title.lower().split())
        for existing_title in similar_articles:
            existing_words = set(existing_title.lower().split())
            # If 80% of words match, consider it duplicate
            if (
                len(title_words.intersection(existing_words))
                / len(title_words.union(existing_words))
                > 0.8
            ):
                return True

        return False

    def _clean_author(self, authors) -> str:
        """Clean and truncate author field to fit database constraints."""
        if not authors:
            return ""

        # Join authors if it's a list
        if isinstance(authors, list):
            author_text = ", ".join(authors)
        else:
            author_text = str(authors)

        # Truncate to fit database constraint (200 chars)
        if len(author_text) > 200:
            author_text = author_text[:197] + "..."

        return author_text.strip()

    def _clean_content(self, content: str) -> str:
        """Clean and normalize article content."""
        if not content:
            return ""

        # Remove extra whitespace and normalize
        content = re.sub(r"\s+", " ", content).strip()

        # Remove common footer text patterns
        patterns_to_remove = [
            r"Follow us on.*",
            r"Subscribe to.*",
            r"Read more at.*",
            r"© \d{4}.*",
        ]

        for pattern in patterns_to_remove:
            content = re.sub(pattern, "", content, flags=re.IGNORECASE)

        return content.strip()

    def _calculate_read_time(self, content: str, words_per_minute: int = 200) -> int:
        """Calculate estimated reading time in minutes."""
        if not content:
            return 1

        # Remove HTML tags and count words
        text = re.sub(r"<[^>]+>", "", content)
        word_count = len(text.split())

        # Calculate read time (minimum 1 minute)
        return max(1, round(word_count / words_per_minute))

    def _extract_keywords(self, content: str, max_keywords: int = 10) -> list[str]:
        """Extract keywords from article content using NLTK."""
        if not content:
            return []

        try:
            from collections import Counter

            # Simple keyword extraction
            words = re.findall(r"\b[a-zA-Z]{3,}\b", content.lower())

            # Remove common stop words
            try:
                from nltk.corpus import stopwords

                stop_words = set(stopwords.words("english"))
                words = [word for word in words if word not in stop_words]
            except Exception:
                # Fallback basic stop words
                basic_stop_words = {
                    "the",
                    "a",
                    "an",
                    "and",
                    "or",
                    "but",
                    "in",
                    "on",
                    "at",
                    "to",
                    "for",
                    "of",
                    "with",
                    "by",
                }
                words = [word for word in words if word not in basic_stop_words]

            # Get most common words
            word_freq = Counter(words)
            return [word for word, _ in word_freq.most_common(max_keywords)]

        except Exception as e:
            logger.warning(f"Failed to extract keywords: {e}")
            return []

    def validate_article_quality(self, article_data: dict) -> tuple[bool, str]:
        """
        Validate article quality based on content length, title, and metadata.

        Returns:
            Tuple of (is_valid, reason)
        """
        title = article_data.get("title", "").strip()
        content = article_data.get("content", "").strip()

        # Check title
        if not title or len(title) < 10:
            return False, "Title too short or missing"

        if len(title) > 500:
            return False, "Title too long"

        # Check content
        if not content:
            return False, "No content found"

        # Count words in content
        text_content = re.sub(r"<[^>]+>", "", content)
        word_count = len(text_content.split())

        if word_count < 50:
            return False, f"Content too short ({word_count} words)"

        # Check for valid publish date
        publish_date = article_data.get("published_at")
        if not publish_date:
            return False, "No publish date found"

        # Check if date is reasonable (not in future, not too old)
        now = timezone.now()
        if publish_date > now:
            return False, "Publish date in future"

        if publish_date < now - timedelta(days=365):
            return False, "Article too old (>1 year)"

        return True, "Valid article"

    def scrape_article(self, url: str, source: NewsSource | None = None) -> dict | None:
        """
        Scrape a single article from URL using newspaper4k with comprehensive error handling.

        Args:
            url: Article URL to scrape
            source: Optional NewsSource for configuration

        Returns:
            Dictionary with article data or None if failed
        """
        if not url or not url.strip():
            logger.warning("Empty or invalid URL provided")
            return None

        url = url.strip()
        logger.debug(f"Starting to scrape article: {url}")

        # Validate URL format
        if not self._is_valid_url(url):
            logger.warning(f"Invalid URL format: {url}")
            return None

        self._rate_limit_delay()

        # Retry logic for network issues
        for attempt in range(self.retry_attempts):
            try:
                config = self._get_newspaper_config(source) if source else Config()
                config.request_timeout = (self.connection_timeout, self.read_timeout)
                config.number_threads = 1  # Avoid threading issues

                article = NewspaperArticle(url, config=config)

                # Download with error handling
                try:
                    article.download()
                except Exception as download_error:
                    error_msg = str(download_error).lower()

                    # Check for binary data or unsupported content
                    if any(
                        keyword in error_msg
                        for keyword in ["binary data", "pdf", "image", "video"]
                    ):
                        logger.debug(
                            f"Skipping binary/unsupported content at {url}: {download_error}",
                        )
                        return None

                    if self._is_network_error(download_error):
                        if attempt < self.retry_attempts - 1:
                            wait_time = (2**attempt) + random.uniform(0, 1)
                            logger.warning(
                                f"Network error downloading {url} (attempt {attempt + 1}/{self.retry_attempts}). "
                                f"Retrying in {wait_time:.2f}s: {download_error}",
                            )
                            time.sleep(wait_time)
                            continue
                        logger.error(
                            f"Failed to download {url} after {self.retry_attempts} attempts: {download_error}",
                        )
                        return None
                    logger.error(
                        f"Non-network error downloading {url}: {download_error}",
                    )
                    return None

                # Check if download was successful
                if not article.html or len(article.html.strip()) < 100:
                    logger.warning(f"Downloaded content too short or empty for {url}")
                    return None

                # Parse content
                try:
                    article.parse()
                except Exception as parse_error:
                    logger.error(
                        f"Failed to parse article content for {url}: {parse_error}",
                    )
                    return None

                # Extract keywords and summary (optional, don't fail if this fails)
                try:
                    article.nlp()
                except Exception as nlp_error:
                    logger.warning(f"NLP processing failed for {url}: {nlp_error}")

                # Parse publish date with fallbacks
                publish_date = self._extract_publish_date(article, url)

                # Clean and prepare data
                content = self._clean_content(article.text)
                title = article.title.strip() if article.title else ""

                # Additional validation
                if not title and not content:
                    logger.warning(f"No title or content extracted from {url}")
                    return None

                # Handle keywords safely - newspaper4k can return different types
                try:
                    if hasattr(article, "keywords") and article.keywords:
                        if isinstance(article.keywords, list):
                            keywords = [str(k) for k in article.keywords if k]
                        elif isinstance(article.keywords, str):
                            keywords = [article.keywords]
                        else:
                            # Handle dict or other types
                            keywords = self._extract_keywords(content)
                    else:
                        keywords = self._extract_keywords(content)
                except Exception as keyword_error:
                    logger.warning(
                        f"Keyword extraction failed for {url}: {keyword_error}",
                    )
                    keywords = self._extract_keywords(content)

                # Handle summary safely
                try:
                    summary = str(article.summary) if article.summary else ""
                except Exception:
                    summary = ""

                article_data = {
                    "url": url,
                    "title": title,
                    "content": content,
                    "summary": summary,
                    "author": self._clean_author(article.authors),
                    "published_at": publish_date,
                    "top_image": article.top_image or "",
                    "keywords": keywords,
                    "read_time": self._calculate_read_time(content),
                }

                logger.debug(f"Successfully scraped article: {title[:50]}...")
                return article_data

            except Exception as e:
                if self._is_network_error(e) and attempt < self.retry_attempts - 1:
                    wait_time = (2**attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"Network error scraping {url} (attempt {attempt + 1}/{self.retry_attempts}). "
                        f"Retrying in {wait_time:.2f}s: {e}",
                    )
                    time.sleep(wait_time)
                    continue
                logger.error(
                    f"Failed to scrape article {url} (attempt {attempt + 1}/{self.retry_attempts}): {e}",
                )
                break

        return None

    def _extract_date_from_content(self, content: str) -> datetime | None:
        """Try to extract publish date from article content."""
        if not content:
            return None

        # Look for common date patterns in first 500 characters
        text_sample = content[:500]

        # Common date patterns
        date_patterns = [
            r"\b(\w+ \d{1,2}, \d{4})\b",  # January 1, 2023
            r"\b(\d{1,2}/\d{1,2}/\d{4})\b",  # 1/1/2023
            r"\b(\d{4}-\d{2}-\d{2})\b",  # 2023-01-01
        ]

        for pattern in date_patterns:
            matches = re.findall(pattern, text_sample)
            for match in matches:
                try:
                    parsed_date = date_parser.parse(match)
                    return timezone.make_aware(parsed_date)
                except Exception:
                    continue

        return None

    def _is_valid_url(self, url: str) -> bool:
        """Validate URL format and scheme."""
        try:
            parsed = urlparse(url)
            return parsed.scheme in ("http", "https") and parsed.netloc
        except Exception:
            return False

    def _is_network_error(self, error: Exception) -> bool:
        """Check if error is network-related and should be retried."""
        return isinstance(error, NETWORK_EXCEPTIONS)

    def _extract_publish_date(self, article: NewspaperArticle, url: str) -> datetime:
        """Extract publish date with multiple fallback methods."""
        # Try newspaper's publish_date first
        if article.publish_date:
            try:
                return timezone.make_aware(article.publish_date)
            except Exception as e:
                logger.debug(f"Failed to process newspaper publish_date for {url}: {e}")

        # Try to extract from article content
        extracted_date = self._extract_date_from_content(article.text)
        if extracted_date:
            return extracted_date

        # Try to extract from URL path
        url_date = self._extract_date_from_url(url)
        if url_date:
            return url_date

        # Fallback to current time
        logger.debug(f"Could not extract publish date for {url}, using current time")
        return timezone.now()

    def _extract_date_from_url(self, url: str) -> datetime | None:
        """Try to extract date from URL path."""
        try:
            # Common URL date patterns: /2023/12/31/ or /2023-12-31/
            date_patterns = [
                r"/(\d{4})/(\d{1,2})/(\d{1,2})/",  # /2023/12/31/
                r"/(\d{4})-(\d{1,2})-(\d{1,2})",  # /2023-12-31
                r"/(\d{4})(\d{2})(\d{2})/",  # /20231231/
            ]

            for pattern in date_patterns:
                match = re.search(pattern, url)
                if match:
                    try:
                        if len(match.groups()) == 3:
                            year, month, day = match.groups()
                            date_obj = datetime(int(year), int(month), int(day))
                            return timezone.make_aware(date_obj)
                    except (ValueError, TypeError):
                        continue

        except Exception as e:
            logger.debug(f"Error extracting date from URL {url}: {e}")

        return None

    def scrape_rss_feed(self, source_id: int) -> dict[str, int]:
        """
        Scrape articles from RSS feed with comprehensive error handling.

        Args:
            source_id: NewsSource ID to scrape

        Returns:
            Dictionary with scraping statistics
        """
        try:
            source = NewsSource.objects.get(id=source_id)
        except NewsSource.DoesNotExist:
            logger.error(f"NewsSource {source_id} not found")
            return {"success": 0, "failed": 0, "duplicates": 0}

        if not source.rss_feed:
            logger.error(f"No RSS feed URL for source {source.name}")
            return {"success": 0, "failed": 0, "duplicates": 0}

        if not self._is_valid_url(source.rss_feed):
            logger.error(
                f"Invalid RSS feed URL for source {source.name}: {source.rss_feed}",
            )
            return {"success": 0, "failed": 0, "duplicates": 0}

        stats = {"success": 0, "failed": 0, "duplicates": 0}
        feed = None

        logger.info(f"Starting RSS feed scraping for {source.name}: {source.rss_feed}")

        # Retry RSS feed parsing with exponential backoff
        for attempt in range(self.retry_attempts):
            try:
                self._rate_limit_delay()

                # Parse RSS feed with timeout
                try:
                    response = self.session.get(
                        source.rss_feed,
                        timeout=(self.connection_timeout, self.read_timeout),
                        headers={
                            "Accept": "application/rss+xml, application/xml, text/xml",
                        },
                    )
                    response.raise_for_status()
                    feed = feedparser.parse(response.content)
                except NETWORK_EXCEPTIONS as e:
                    if attempt < self.retry_attempts - 1:
                        wait_time = (2**attempt) + random.uniform(0, 1)
                        logger.warning(
                            f"Network error fetching RSS feed {source.rss_feed} "
                            f"(attempt {attempt + 1}/{self.retry_attempts}). "
                            f"Retrying in {wait_time:.2f}s: {e}",
                        )
                        time.sleep(wait_time)
                        continue
                    logger.error(
                        f"Failed to fetch RSS feed {source.rss_feed} after {self.retry_attempts} attempts: {e}",
                    )
                    return stats

                break  # Success, exit retry loop

            except Exception as e:
                logger.error(
                    f"Unexpected error parsing RSS feed {source.rss_feed}: {e}",
                )
                return stats

        if not feed:
            logger.error(f"Failed to parse RSS feed for {source.name}")
            return stats

        # Check for RSS parsing issues
        if feed.bozo:
            logger.warning(
                f"RSS feed parsing issues for {source.name}: {feed.bozo_exception}",
            )
            # Continue processing if not critical

        if not hasattr(feed, "entries") or not feed.entries:
            logger.warning(f"No entries found in RSS feed for {source.name}")
            return stats

        logger.info(f"Found {len(feed.entries)} entries in RSS feed for {source.name}")

        # Process entries up to max_articles_per_scrape
        max_articles = source.max_articles_per_scrape
        entries_to_process = feed.entries[:max_articles]

        for i, entry in enumerate(entries_to_process):
            try:
                # Validate entry has required fields
                if not hasattr(entry, "link") or not entry.link:
                    logger.debug(f"RSS entry {i} missing link, skipping")
                    stats["failed"] += 1
                    continue

                article_url = entry.link.strip()

                # Validate URL
                if not self._is_valid_url(article_url):
                    logger.debug(f"Invalid URL in RSS entry: {article_url}")
                    stats["failed"] += 1
                    continue

                # Check for duplicates first
                entry_title = getattr(entry, "title", "")
                if self._is_duplicate_article(article_url, entry_title, source):
                    stats["duplicates"] += 1
                    continue

                # Scrape full article content
                article_data = self.scrape_article(article_url, source)

                if not article_data:
                    stats["failed"] += 1
                    continue

                # Enhance with RSS metadata if article scraping missed something
                article_data = self._enhance_with_rss_metadata(article_data, entry)

                # Validate article quality
                is_valid, reason = self.validate_article_quality(article_data)
                if not is_valid:
                    logger.debug(f"Article rejected: {reason} - {article_url}")
                    stats["failed"] += 1
                    continue

                # Save article
                saved_article = self._save_article(article_data, source)
                if saved_article:
                    stats["success"] += 1
                else:
                    stats["failed"] += 1

            except Exception as e:
                logger.error(f"Failed to process RSS entry {i} from {source.name}: {e}")
                stats["failed"] += 1
                continue

        # Update source statistics
        try:
            source.mark_scraped(stats["success"])
        except Exception as e:
            logger.error(f"Failed to update source statistics for {source.name}: {e}")

        logger.info(
            f"RSS scraping completed for {source.name}: "
            f"{stats['success']} success, {stats['failed']} failed, {stats['duplicates']} duplicates",
        )

        return stats

    def _enhance_with_rss_metadata(self, article_data: dict, entry) -> dict:
        """Enhance article data with RSS feed metadata."""
        # Use RSS title if article title is missing or very short
        if (not article_data["title"] or len(article_data["title"]) < 10) and hasattr(
            entry,
            "title",
        ):
            article_data["title"] = entry.title.strip()

        # Use RSS summary if article summary is missing
        if not article_data["summary"] and hasattr(entry, "summary"):
            article_data["summary"] = entry.summary.strip()

        # Use RSS author if article author is missing
        if not article_data["author"] and hasattr(entry, "author"):
            article_data["author"] = entry.author.strip()

        # Use RSS publish date if article date is current time (fallback)
        if (
            article_data["published_at"]
            and abs((article_data["published_at"] - timezone.now()).total_seconds())
            < 60
            and hasattr(entry, "published_parsed")
            and entry.published_parsed
        ):
            try:
                pub_date = datetime(*entry.published_parsed[:6])
                article_data["published_at"] = timezone.make_aware(pub_date)
            except Exception as e:
                logger.debug(f"Failed to parse RSS published date: {e}")

        return article_data

    def scrape_source(self, source_id: int) -> dict[str, int]:
        """
        Scrape all articles from a news source using newspaper.build().

        Args:
            source_id: NewsSource ID to scrape

        Returns:
            Dictionary with scraping statistics
        """
        try:
            source = NewsSource.objects.get(id=source_id)
        except NewsSource.DoesNotExist:
            logger.error(f"NewsSource {source_id} not found")
            return {"success": 0, "failed": 0, "duplicates": 0}

        # Prefer RSS feed if available
        if source.source_type == "rss" and source.rss_feed:
            return self.scrape_rss_feed(source_id)

        stats = {"success": 0, "failed": 0, "duplicates": 0}

        try:
            config = self._get_newspaper_config(source)

            # Build newspaper source
            self._rate_limit_delay()
            news_source = build(source.base_url, config=config)

            logger.info(f"Found {news_source.size()} articles for {source.name}")

            # Limit articles based on source configuration
            max_articles = min(source.max_articles_per_scrape, news_source.size())
            articles_to_process = news_source.articles[:max_articles]

            for article in articles_to_process:
                try:
                    # Check for duplicates first
                    if self._is_duplicate_article(article.url, "", source):
                        stats["duplicates"] += 1
                        continue

                    # Download and parse article
                    article.download()
                    article.parse()
                    article.nlp()

                    # Parse publish date
                    publish_date = None
                    if article.publish_date:
                        publish_date = timezone.make_aware(article.publish_date)
                    else:
                        publish_date = (
                            self._extract_date_from_content(article.text)
                            or timezone.now()
                        )

                    # Prepare article data
                    content = self._clean_content(article.text)

                    # Handle keywords safely - newspaper4k can return different types
                    try:
                        if hasattr(article, "keywords") and article.keywords:
                            if isinstance(article.keywords, list):
                                keywords = [str(k) for k in article.keywords if k]
                            elif isinstance(article.keywords, str):
                                keywords = [article.keywords]
                            else:
                                # Handle dict or other types
                                keywords = self._extract_keywords(content)
                        else:
                            keywords = self._extract_keywords(content)
                    except Exception as keyword_error:
                        logger.warning(
                            f"Keyword extraction failed for {article.url}: {keyword_error}",
                        )
                        keywords = self._extract_keywords(content)

                    # Handle summary safely
                    try:
                        summary = str(article.summary) if article.summary else ""
                    except Exception:
                        summary = ""

                    article_data = {
                        "url": article.url,
                        "title": article.title.strip() if article.title else "",
                        "content": content,
                        "summary": summary,
                        "author": self._clean_author(article.authors),
                        "published_at": publish_date,
                        "top_image": article.top_image or "",
                        "keywords": keywords,
                        "read_time": self._calculate_read_time(content),
                    }

                    # Validate article quality
                    is_valid, reason = self.validate_article_quality(article_data)
                    if not is_valid:
                        logger.debug(f"Article rejected: {reason} - {article.url}")
                        stats["failed"] += 1
                        continue

                    # Save article
                    self._save_article(article_data, source)
                    stats["success"] += 1

                except Exception as e:
                    logger.error(f"Failed to process article from {source.name}: {e}")
                    stats["failed"] += 1
                    continue

            # Update source statistics
            source.mark_scraped(stats["success"])

            logger.info(
                f"Website scraping completed for {source.name}: "
                f"{stats['success']} success, {stats['failed']} failed, {stats['duplicates']} duplicates",
            )

        except Exception as e:
            logger.error(f"Failed to scrape source {source.name}: {e}")
            stats["failed"] += 1

        return stats

    def _save_article(self, article_data: dict, source: NewsSource) -> Article | None:
        """Save article to database with transaction safety."""
        try:
            with transaction.atomic():
                # Auto-categorize based on source primary category
                article = Article.objects.create(
                    title=article_data["title"],
                    url=article_data["url"],
                    content=article_data["content"],
                    summary=article_data["summary"],
                    author=article_data["author"],
                    source=source,
                    published_at=article_data["published_at"],
                    top_image=article_data["top_image"],
                    keywords=article_data["keywords"],
                    read_time=article_data["read_time"],
                )

                # Add to source's primary category if exists
                try:
                    category = Category.objects.get(
                        name__iexact=source.primary_category,
                    )
                    article.categories.add(category)
                except Category.DoesNotExist:
                    pass

                logger.debug(f"Saved article: {article.title[:50]}...")
                return article

        except Exception as e:
            logger.error(f"Failed to save article {article_data['url']}: {e}")
            return None

    def get_scraping_statistics(self, source_id: int | None = None) -> dict:
        """Get scraping statistics for monitoring."""
        stats = {}

        if source_id:
            try:
                source = NewsSource.objects.get(id=source_id)
                stats = {
                    "source_name": source.name,
                    "total_articles": source.total_articles_scraped,
                    "last_scraped": source.last_scraped,
                    "success_rate": source.success_rate,
                    "average_response_time": source.average_response_time,
                    "next_scrape_time": source.next_scrape_time,
                    "is_due_for_scraping": source.is_due_for_scraping,
                }
            except NewsSource.DoesNotExist:
                stats["error"] = f"Source {source_id} not found"
        else:
            # Global statistics
            all_sources = NewsSource.objects.active()
            stats = {
                "total_sources": all_sources.count(),
                "sources_due_for_scraping": len(NewsSource.objects.needs_scraping()),
                "total_articles_today": Article.objects.filter(
                    scraped_at__date=timezone.now().date(),
                ).count(),
                "avg_success_rate": all_sources.aggregate(
                    avg_rate=models.Avg("success_rate"),
                )["avg_rate"]
                or 0,
            }

        return stats
