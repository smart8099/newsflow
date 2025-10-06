import logging
import time
from contextlib import contextmanager
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from newsflow.news.models import Article
from newsflow.news.models import NewsSource

logger = logging.getLogger(__name__)


class ScrapingMetrics:
    """Utility class for tracking and monitoring scraping metrics."""

    CACHE_PREFIX = "scraping_metrics"
    CACHE_TIMEOUT = 300  # 5 minutes

    @classmethod
    def _cache_key(cls, key: str) -> str:
        """Generate cache key with prefix."""
        return f"{cls.CACHE_PREFIX}:{key}"

    @classmethod
    def record_scraping_attempt(
        cls,
        source_id: int,
        success: bool,
        duration: float = None,
    ):
        """Record a scraping attempt for metrics."""
        try:
            # Update attempt counters
            today = timezone.now().date().isoformat()

            # Daily metrics
            daily_key = cls._cache_key(f"daily:{today}")
            daily_stats = cache.get(
                daily_key,
                {"attempts": 0, "success": 0, "failures": 0},
            )
            daily_stats["attempts"] += 1
            if success:
                daily_stats["success"] += 1
            else:
                daily_stats["failures"] += 1
            cache.set(daily_key, daily_stats, 86400)  # 24 hours

            # Source-specific metrics
            source_key = cls._cache_key(f"source:{source_id}:{today}")
            source_stats = cache.get(
                source_key,
                {"attempts": 0, "success": 0, "failures": 0, "durations": []},
            )
            source_stats["attempts"] += 1
            if success:
                source_stats["success"] += 1
            else:
                source_stats["failures"] += 1

            if duration is not None:
                source_stats["durations"].append(duration)
                # Keep only last 10 durations
                source_stats["durations"] = source_stats["durations"][-10:]

            cache.set(source_key, source_stats, 86400)

            # Hourly metrics for real-time monitoring
            hour = timezone.now().hour
            hourly_key = cls._cache_key(f"hourly:{today}:{hour}")
            hourly_stats = cache.get(
                hourly_key,
                {"attempts": 0, "success": 0, "failures": 0},
            )
            hourly_stats["attempts"] += 1
            if success:
                hourly_stats["success"] += 1
            else:
                hourly_stats["failures"] += 1
            cache.set(hourly_key, hourly_stats, 3600)  # 1 hour

        except Exception as e:
            logger.error(f"Failed to record scraping attempt: {e}")

    @classmethod
    def get_daily_metrics(cls, date: str | None = None) -> dict:
        """Get daily scraping metrics."""
        if date is None:
            date = timezone.now().date().isoformat()

        daily_key = cls._cache_key(f"daily:{date}")
        stats = cache.get(daily_key, {"attempts": 0, "success": 0, "failures": 0})

        # Calculate success rate
        if stats["attempts"] > 0:
            stats["success_rate"] = (stats["success"] / stats["attempts"]) * 100
        else:
            stats["success_rate"] = 0

        return stats

    @classmethod
    def get_source_metrics(cls, source_id: int, date: str | None = None) -> dict:
        """Get metrics for a specific source."""
        if date is None:
            date = timezone.now().date().isoformat()

        source_key = cls._cache_key(f"source:{source_id}:{date}")
        stats = cache.get(
            source_key,
            {"attempts": 0, "success": 0, "failures": 0, "durations": []},
        )

        # Calculate metrics
        if stats["attempts"] > 0:
            stats["success_rate"] = (stats["success"] / stats["attempts"]) * 100
        else:
            stats["success_rate"] = 0

        if stats["durations"]:
            stats["avg_duration"] = sum(stats["durations"]) / len(stats["durations"])
            stats["min_duration"] = min(stats["durations"])
            stats["max_duration"] = max(stats["durations"])
        else:
            stats["avg_duration"] = 0
            stats["min_duration"] = 0
            stats["max_duration"] = 0

        return stats

    @classmethod
    def get_hourly_metrics(cls, date: str | None = None) -> list[dict]:
        """Get hourly metrics for a day."""
        if date is None:
            date = timezone.now().date().isoformat()

        hourly_metrics = []
        for hour in range(24):
            hourly_key = cls._cache_key(f"hourly:{date}:{hour}")
            stats = cache.get(hourly_key, {"attempts": 0, "success": 0, "failures": 0})
            stats["hour"] = hour

            if stats["attempts"] > 0:
                stats["success_rate"] = (stats["success"] / stats["attempts"]) * 100
            else:
                stats["success_rate"] = 0

            hourly_metrics.append(stats)

        return hourly_metrics

    @classmethod
    def get_real_time_stats(cls) -> dict:
        """Get real-time scraping statistics."""
        try:
            # Active sources
            active_sources = NewsSource.objects.active().count()

            # Sources due for scraping
            sources_due = len(NewsSource.objects.needs_scraping())

            # Articles scraped today
            today = timezone.now().date()
            articles_today = Article.objects.filter(scraped_at__date=today).count()

            # Recent scraping activity (last hour)
            last_hour = timezone.now() - timedelta(hours=1)
            recent_articles = Article.objects.filter(scraped_at__gte=last_hour).count()

            # Daily metrics
            daily_metrics = cls.get_daily_metrics()

            return {
                "active_sources": active_sources,
                "sources_due": sources_due,
                "articles_today": articles_today,
                "articles_last_hour": recent_articles,
                "daily_attempts": daily_metrics["attempts"],
                "daily_success_rate": daily_metrics["success_rate"],
                "timestamp": timezone.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to get real-time stats: {e}")
            return {"error": str(e)}

    @classmethod
    def clear_metrics(cls, date: str | None = None):
        """Clear metrics for a specific date."""
        if date is None:
            date = timezone.now().date().isoformat()

        try:
            # Clear daily metrics
            cache.delete(cls._cache_key(f"daily:{date}"))

            # Clear hourly metrics
            for hour in range(24):
                cache.delete(cls._cache_key(f"hourly:{date}:{hour}"))

            # Clear source metrics
            for source in NewsSource.objects.all():
                cache.delete(cls._cache_key(f"source:{source.id}:{date}"))

            logger.info(f"Cleared metrics for date: {date}")

        except Exception as e:
            logger.error(f"Failed to clear metrics: {e}")


class PerformanceMonitor:
    """Context manager for monitoring performance of scraping operations."""

    def __init__(self, operation_name: str, source_id: int | None = None):
        self.operation_name = operation_name
        self.source_id = source_id
        self.start_time = None
        self.end_time = None
        self.success = False
        self.error = None

    def __enter__(self):
        self.start_time = time.time()
        logger.info(f"Starting operation: {self.operation_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration = self.end_time - self.start_time

        if exc_type is None:
            self.success = True
            logger.info(
                f"Operation completed: {self.operation_name} (Duration: {duration:.2f}s)",
            )
        else:
            self.success = False
            self.error = str(exc_val)
            logger.error(
                f"Operation failed: {self.operation_name} (Duration: {duration:.2f}s, Error: {self.error})",
            )

        # Record metrics
        if self.source_id:
            ScrapingMetrics.record_scraping_attempt(
                self.source_id,
                self.success,
                duration,
            )

        return False  # Don't suppress exceptions

    @property
    def duration(self) -> float:
        """Get operation duration in seconds."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0


@contextmanager
def monitor_scraping_operation(operation_name: str, source_id: int | None = None):
    """Context manager for monitoring scraping operations."""
    monitor = PerformanceMonitor(operation_name, source_id)
    try:
        yield monitor
    finally:
        pass


class AlertManager:
    """Manages alerts for scraping issues."""

    ALERT_CACHE_PREFIX = "scraping_alerts"

    # Alert thresholds
    ERROR_RATE_THRESHOLD = 50  # %
    MIN_ARTICLES_PER_HOUR = 5
    MAX_RESPONSE_TIME = 60  # seconds

    @classmethod
    def check_error_rate_alert(cls) -> dict | None:
        """Check if error rate is above threshold."""
        daily_metrics = ScrapingMetrics.get_daily_metrics()

        if daily_metrics["attempts"] >= 10:  # Only alert if we have enough attempts
            if daily_metrics["success_rate"] < (100 - cls.ERROR_RATE_THRESHOLD):
                return {
                    "type": "high_error_rate",
                    "message": f"High error rate detected: {100 - daily_metrics['success_rate']:.1f}% failure rate",
                    "severity": "high",
                    "data": daily_metrics,
                }

        return None

    @classmethod
    def check_low_activity_alert(cls) -> dict | None:
        """Check if scraping activity is too low."""
        last_hour = timezone.now() - timedelta(hours=1)
        recent_articles = Article.objects.filter(scraped_at__gte=last_hour).count()

        if recent_articles < cls.MIN_ARTICLES_PER_HOUR:
            return {
                "type": "low_activity",
                "message": f"Low scraping activity: only {recent_articles} articles in last hour",
                "severity": "medium",
                "data": {"articles_last_hour": recent_articles},
            }

        return None

    @classmethod
    def check_source_health_alerts(cls) -> list[dict]:
        """Check for source-specific health issues."""
        alerts = []

        for source in NewsSource.objects.active():
            # Check if source hasn't been scraped recently
            if source.last_scraped:
                time_since_scrape = timezone.now() - source.last_scraped
                expected_interval = timedelta(
                    minutes=source.scrape_frequency * 2,
                )  # 2x the expected frequency

                if time_since_scrape > expected_interval:
                    alerts.append(
                        {
                            "type": "source_stale",
                            "message": f"Source '{source.name}' hasn't been scraped for {time_since_scrape}",
                            "severity": "medium",
                            "data": {
                                "source_id": source.id,
                                "source_name": source.name,
                                "last_scraped": source.last_scraped.isoformat(),
                                "time_since_scrape": str(time_since_scrape),
                            },
                        },
                    )

            # Check success rate
            if source.success_rate < 70:  # Below 70% success rate
                alerts.append(
                    {
                        "type": "source_low_success_rate",
                        "message": f"Source '{source.name}' has low success rate: {source.success_rate:.1f}%",
                        "severity": "high",
                        "data": {
                            "source_id": source.id,
                            "source_name": source.name,
                            "success_rate": source.success_rate,
                        },
                    },
                )

        return alerts

    @classmethod
    def get_all_alerts(cls) -> list[dict]:
        """Get all current alerts."""
        alerts = []

        # Check system-wide alerts
        error_rate_alert = cls.check_error_rate_alert()
        if error_rate_alert:
            alerts.append(error_rate_alert)

        low_activity_alert = cls.check_low_activity_alert()
        if low_activity_alert:
            alerts.append(low_activity_alert)

        # Check source-specific alerts
        source_alerts = cls.check_source_health_alerts()
        alerts.extend(source_alerts)

        return alerts

    @classmethod
    def should_send_alert(cls, alert: dict) -> bool:
        """Check if alert should be sent (to avoid spam)."""
        alert_key = f"{cls.ALERT_CACHE_PREFIX}:{alert['type']}:{hash(str(alert.get('data', {})))}"

        # Check if we've already sent this alert recently
        if cache.get(alert_key):
            return False

        # Mark alert as sent for the next hour
        cache.set(alert_key, True, 3600)
        return True


class ScrapingHealthCheck:
    """Health check utilities for scraping system."""

    @classmethod
    def check_dependencies(cls) -> dict:
        """Check if all required dependencies are available."""
        health_status = {"status": "healthy", "checks": {}}

        # Check required services
        checks = {
            "redis": cls._check_redis,
            "database": cls._check_database,
            "celery": cls._check_celery,
            "disk_space": cls._check_disk_space,
            "nltk_data": cls._check_nltk_data,
        }

        for check_name, check_func in checks.items():
            try:
                check_result = check_func()
                health_status["checks"][check_name] = check_result

                if not check_result.get("healthy", False):
                    health_status["status"] = "unhealthy"

            except Exception as e:
                health_status["checks"][check_name] = {
                    "healthy": False,
                    "error": str(e),
                }
                health_status["status"] = "unhealthy"

        return health_status

    @classmethod
    def _check_redis(cls) -> dict:
        """Check Redis connectivity."""
        try:
            from django.core.cache import cache

            cache.set("health_check", "ok", 10)
            result = cache.get("health_check")

            return {
                "healthy": result == "ok",
                "message": "Redis is accessible"
                if result == "ok"
                else "Redis check failed",
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    @classmethod
    def _check_database(cls) -> dict:
        """Check database connectivity."""
        try:
            from django.db import connection

            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()

            return {
                "healthy": result[0] == 1,
                "message": "Database is accessible",
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    @classmethod
    def _check_celery(cls) -> dict:
        """Check Celery worker availability."""
        try:
            from celery import current_app

            inspect = current_app.control.inspect()
            active = inspect.active()

            if active:
                worker_count = len(active)
                return {
                    "healthy": True,
                    "message": f"{worker_count} Celery workers active",
                    "workers": worker_count,
                }
            return {
                "healthy": False,
                "message": "No active Celery workers found",
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    @classmethod
    def _check_disk_space(cls) -> dict:
        """Check available disk space."""
        try:
            import shutil

            total, used, free = shutil.disk_usage("/")
            free_gb = free // (1024**3)

            return {
                "healthy": free_gb > 1,  # At least 1GB free
                "message": f"{free_gb}GB free disk space",
                "free_gb": free_gb,
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    @classmethod
    def _check_nltk_data(cls) -> dict:
        """Check NLTK data availability."""
        try:
            import nltk

            required_datasets = ["punkt", "stopwords"]
            missing = []

            for dataset in required_datasets:
                try:
                    nltk.data.find(
                        f"tokenizers/{dataset}"
                        if dataset == "punkt"
                        else f"corpora/{dataset}",
                    )
                except LookupError:
                    missing.append(dataset)

            if missing:
                return {
                    "healthy": False,
                    "message": f"Missing NLTK datasets: {', '.join(missing)}",
                }
            return {
                "healthy": True,
                "message": "All required NLTK datasets available",
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}
