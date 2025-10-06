"""
Utility functions for news scraping operations.
"""

import logging
import re
from urllib.parse import urljoin
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from django.conf import settings

logger = logging.getLogger(__name__)

# Common RSS feed patterns to search for
RSS_FEED_PATTERNS = [
    "/rss",
    "/rss.xml",
    "/feed",
    "/feed.xml",
    "/feeds",
    "/feeds/all.xml",
    "/feeds/rss.xml",
    "/atom.xml",
    "/feed/",
    "/rss/",
    "/feeds/",
    "/index.xml",
    "/news.xml",
    "/all.rss",
    "/latest.rss",
]

# RSS feed link patterns in HTML
RSS_LINK_PATTERNS = [
    r'<link[^>]*type=["\']application/rss\+xml["\'][^>]*href=["\']([^"\']+)["\']',
    r'<link[^>]*href=["\']([^"\']+)["\'][^>]*type=["\']application/rss\+xml["\']',
    r'<link[^>]*type=["\']application/atom\+xml["\'][^>]*href=["\']([^"\']+)["\']',
    r'<link[^>]*href=["\']([^"\']+)["\'][^>]*type=["\']application/atom\+xml["\']',
]


class RSSValidator:
    """Utility class for RSS feed validation and discovery."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": getattr(
                    settings,
                    "SCRAPER_USER_AGENT",
                    "NewsFlow/1.0 (+https://newsflow.com)",
                ),
            },
        )
        self.timeout = getattr(settings, "SCRAPER_REQUEST_TIMEOUT", 30)

    def validate_rss_feed(self, feed_url: str) -> tuple[bool, str, dict]:
        """
        Validate an RSS feed URL and return detailed information.

        Args:
            feed_url: RSS feed URL to validate

        Returns:
            Tuple of (is_valid, reason, feed_info)
        """
        if not feed_url or not feed_url.strip():
            return False, "Empty feed URL", {}

        feed_url = feed_url.strip()

        # Basic URL validation
        try:
            parsed = urlparse(feed_url)
            if parsed.scheme not in ("http", "https"):
                return False, "Invalid URL scheme", {}
            if not parsed.netloc:
                return False, "Invalid URL format", {}
        except Exception as e:
            return False, f"URL parsing error: {e}", {}

        logger.debug(f"Validating RSS feed: {feed_url}")

        try:
            # Fetch the feed with timeout
            response = self.session.get(
                feed_url,
                timeout=self.timeout,
                headers={"Accept": "application/rss+xml, application/xml, text/xml"},
            )
            response.raise_for_status()

            # Parse with feedparser
            feed = feedparser.parse(response.content)

            # Check for parsing errors
            if feed.bozo and feed.bozo_exception:
                # Some feeds have minor issues but are still usable
                error_msg = str(feed.bozo_exception)
                if "not well-formed" in error_msg.lower():
                    return False, f"Malformed XML: {error_msg}", {}
                # Warning but continue validation
                logger.warning(f"RSS feed has minor issues: {error_msg}")

            # Check if feed has required elements
            if not hasattr(feed, "feed") or not feed.feed:
                return False, "Invalid RSS format: missing feed element", {}

            # Check for entries
            if not hasattr(feed, "entries") or not feed.entries:
                return False, "RSS feed has no entries", {}

            # Validate feed metadata
            feed_info = {
                "title": getattr(feed.feed, "title", ""),
                "description": getattr(feed.feed, "description", ""),
                "link": getattr(feed.feed, "link", ""),
                "language": getattr(feed.feed, "language", ""),
                "entry_count": len(feed.entries),
                "last_updated": getattr(feed.feed, "updated", ""),
                "generator": getattr(feed.feed, "generator", ""),
            }

            # Validate entries have required fields
            valid_entries = 0
            for entry in feed.entries[:5]:  # Check first 5 entries
                if hasattr(entry, "link") and hasattr(entry, "title"):
                    valid_entries += 1

            if valid_entries == 0:
                return (
                    False,
                    "RSS entries missing required fields (link, title)",
                    feed_info,
                )

            # Check entry quality
            if valid_entries < len(feed.entries[:5]) * 0.5:
                return (
                    False,
                    f"Too many invalid entries ({valid_entries}/{len(feed.entries[:5])})",
                    feed_info,
                )

            feed_info["valid_entries"] = valid_entries
            feed_info["validation_score"] = (
                valid_entries / min(5, len(feed.entries))
            ) * 100

            logger.info(
                f"RSS feed validation successful: {feed_url} ({feed_info['entry_count']} entries)",
            )
            return True, "Valid RSS feed", feed_info

        except requests.exceptions.Timeout:
            return False, "Request timeout", {}
        except requests.exceptions.ConnectionError:
            return False, "Connection error", {}
        except requests.exceptions.HTTPError as e:
            return False, f"HTTP error: {e.response.status_code}", {}
        except Exception as e:
            return False, f"Validation error: {e!s}", {}

    def discover_rss_feeds(self, website_url: str) -> list[dict]:
        """
        Discover RSS feeds for a website.

        Args:
            website_url: Website URL to search for RSS feeds

        Returns:
            List of discovered feed dictionaries with URL, title, type
        """
        discovered_feeds = []

        if not website_url or not website_url.strip():
            return discovered_feeds

        website_url = website_url.strip()
        logger.debug(f"Discovering RSS feeds for: {website_url}")

        # Method 1: Check common RSS feed URL patterns
        discovered_feeds.extend(self._check_common_patterns(website_url))

        # Method 2: Parse HTML for RSS feed links
        discovered_feeds.extend(self._parse_html_for_feeds(website_url))

        # Remove duplicates and validate
        unique_feeds = {}
        for feed in discovered_feeds:
            if feed["url"] not in unique_feeds:
                unique_feeds[feed["url"]] = feed

        # Validate discovered feeds
        validated_feeds = []
        for feed in unique_feeds.values():
            is_valid, reason, feed_info = self.validate_rss_feed(feed["url"])
            feed["is_valid"] = is_valid
            feed["validation_reason"] = reason
            feed["feed_info"] = feed_info
            validated_feeds.append(feed)

        # Sort by validity and quality
        validated_feeds.sort(
            key=lambda x: (x["is_valid"], x.get("feed_info", {}).get("entry_count", 0)),
            reverse=True,
        )

        logger.info(
            f"Discovered {len(validated_feeds)} potential RSS feeds for {website_url}",
        )
        return validated_feeds

    def _check_common_patterns(self, base_url: str) -> list[dict]:
        """Check common RSS feed URL patterns."""
        feeds = []

        for pattern in RSS_FEED_PATTERNS:
            feed_url = urljoin(base_url, pattern)
            feeds.append(
                {
                    "url": feed_url,
                    "title": f"RSS Feed ({pattern})",
                    "type": "rss",
                    "discovery_method": "pattern",
                },
            )

        return feeds

    def _parse_html_for_feeds(self, website_url: str) -> list[dict]:
        """Parse website HTML to find RSS feed links."""
        feeds = []

        try:
            response = self.session.get(website_url, timeout=self.timeout)
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.content, "html.parser")

            # Look for RSS link tags
            rss_links = soup.find_all(
                "link",
                {"type": ["application/rss+xml", "application/atom+xml"]},
            )

            for link in rss_links:
                href = link.get("href")
                if href:
                    # Convert relative URLs to absolute
                    feed_url = urljoin(website_url, href)
                    title = link.get("title", "RSS Feed")
                    feed_type = "atom" if "atom" in link.get("type", "") else "rss"

                    feeds.append(
                        {
                            "url": feed_url,
                            "title": title,
                            "type": feed_type,
                            "discovery_method": "html_link",
                        },
                    )

            # Also search for RSS links in the HTML content using regex
            html_content = response.text
            for pattern in RSS_LINK_PATTERNS:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                for match in matches:
                    feed_url = urljoin(website_url, match)
                    feeds.append(
                        {
                            "url": feed_url,
                            "title": "RSS Feed (regex)",
                            "type": "rss",
                            "discovery_method": "html_regex",
                        },
                    )

        except Exception as e:
            logger.warning(
                f"Failed to parse HTML for RSS feeds from {website_url}: {e}",
            )

        return feeds

    def auto_detect_best_feed(self, website_url: str) -> dict | None:
        """
        Auto-detect the best RSS feed for a website.

        Args:
            website_url: Website URL

        Returns:
            Best RSS feed dictionary or None if none found
        """
        discovered_feeds = self.discover_rss_feeds(website_url)

        if not discovered_feeds:
            return None

        # Filter valid feeds
        valid_feeds = [feed for feed in discovered_feeds if feed["is_valid"]]

        if not valid_feeds:
            logger.warning(f"No valid RSS feeds found for {website_url}")
            return None

        # Scoring criteria
        best_feed = None
        best_score = 0

        for feed in valid_feeds:
            score = 0
            feed_info = feed.get("feed_info", {})

            # Entry count score (more entries = better, up to 100 points)
            entry_count = feed_info.get("entry_count", 0)
            score += min(entry_count * 2, 100)

            # Validation score
            score += feed_info.get("validation_score", 0)

            # Discovery method preference
            if feed["discovery_method"] == "html_link":
                score += 50  # Prefer explicit HTML link tags
            elif feed["discovery_method"] == "pattern":
                score += 20  # Common patterns are good

            # Feed type preference
            if feed["type"] == "rss":
                score += 10  # Slight preference for RSS over Atom

            # URL quality (prefer shorter, cleaner URLs)
            url_length = len(feed["url"])
            if url_length < 50:
                score += 10
            elif url_length > 100:
                score -= 10

            # Prefer feeds with titles and descriptions
            if feed_info.get("title"):
                score += 20
            if feed_info.get("description"):
                score += 10

            if score > best_score:
                best_score = score
                best_feed = feed

        if best_feed:
            logger.info(
                f"Auto-detected best RSS feed for {website_url}: {best_feed['url']} (score: {best_score})",
            )

        return best_feed


def validate_and_enhance_source(source_data: dict) -> tuple[bool, dict, list[str]]:
    """
    Validate and enhance a news source with RSS feed auto-detection.

    Args:
        source_data: Dictionary with source information

    Returns:
        Tuple of (is_valid, enhanced_data, warnings)
    """
    validator = RSSValidator()
    warnings = []
    enhanced_data = source_data.copy()

    # Validate base URL
    base_url = source_data.get("base_url", "").strip()
    if not base_url:
        return False, enhanced_data, ["Missing base URL"]

    try:
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return False, enhanced_data, ["Invalid base URL format"]
    except Exception:
        return False, enhanced_data, ["Invalid base URL"]

    # Check if RSS feed is provided
    rss_feed = source_data.get("rss_feed", "").strip()

    if rss_feed:
        # Validate provided RSS feed
        is_valid, reason, feed_info = validator.validate_rss_feed(rss_feed)
        if not is_valid:
            warnings.append(f"Provided RSS feed invalid: {reason}")
            # Try to auto-detect better feed
            best_feed = validator.auto_detect_best_feed(base_url)
            if best_feed and best_feed["is_valid"]:
                enhanced_data["rss_feed"] = best_feed["url"]
                enhanced_data["source_type"] = "rss"
                warnings.append(f"Auto-detected better RSS feed: {best_feed['url']}")
            else:
                enhanced_data["source_type"] = "website"
                warnings.append("Falling back to website scraping")
        else:
            enhanced_data["feed_info"] = feed_info
            enhanced_data["source_type"] = "rss"
    else:
        # Try to auto-detect RSS feed
        best_feed = validator.auto_detect_best_feed(base_url)
        if best_feed and best_feed["is_valid"]:
            enhanced_data["rss_feed"] = best_feed["url"]
            enhanced_data["source_type"] = "rss"
            enhanced_data["feed_info"] = best_feed["feed_info"]
            warnings.append(f"Auto-detected RSS feed: {best_feed['url']}")
        else:
            enhanced_data["source_type"] = "website"
            warnings.append("No RSS feed found, will use website scraping")

    return True, enhanced_data, warnings


def get_rss_feed_info(feed_url: str) -> dict:
    """
    Get detailed information about an RSS feed.

    Args:
        feed_url: RSS feed URL

    Returns:
        Dictionary with feed information
    """
    validator = RSSValidator()
    is_valid, reason, feed_info = validator.validate_rss_feed(feed_url)

    return {
        "is_valid": is_valid,
        "validation_reason": reason,
        "feed_info": feed_info,
    }
