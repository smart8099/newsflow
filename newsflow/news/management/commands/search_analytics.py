"""
Management command to analyze and report search analytics.

This command provides insights into search behavior, popular queries,
and search performance metrics.
"""

import json
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Avg
from django.db.models import Count
from django.utils import timezone

from newsflow.news.models import SearchAnalytics


class Command(BaseCommand):
    help = "Analyze and report search analytics"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Number of days to analyze (default: 7)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Number of items to show in reports (default: 20)",
        )
        parser.add_argument(
            "--report",
            choices=["summary", "popular", "failed", "performance", "users"],
            default="summary",
            help="Type of report to generate (default: summary)",
        )
        parser.add_argument(
            "--export",
            type=str,
            help="Export results to JSON file",
        )

    def handle(self, *args, **options):
        days = options["days"]
        limit = options["limit"]
        report_type = options["report"]
        export_file = options.get("export")

        since = timezone.now() - timedelta(days=days)

        self.stdout.write(
            self.style.SUCCESS(
                f"📊 Search Analytics Report - Last {days} days",
            ),
        )
        self.stdout.write("=" * 60)

        report_data = {}

        if report_type == "summary" or report_type == "all":
            report_data["summary"] = self.generate_summary_report(since)

        if report_type == "popular" or report_type == "all":
            report_data["popular"] = self.generate_popular_queries_report(since, limit)

        if report_type == "failed" or report_type == "all":
            report_data["failed"] = self.generate_failed_queries_report(since, limit)

        if report_type == "performance" or report_type == "all":
            report_data["performance"] = self.generate_performance_report(since)

        if report_type == "users" or report_type == "all":
            report_data["users"] = self.generate_user_behavior_report(since, limit)

        # Export to file if requested
        if export_file:
            self.export_to_json(report_data, export_file)

    def generate_summary_report(self, since):
        """Generate overall summary statistics."""
        self.stdout.write(
            self.style.SUCCESS("\n📈 Summary Statistics"),
        )
        self.stdout.write("-" * 30)

        total_searches = SearchAnalytics.objects.filter(created__gte=since).count()
        unique_queries = (
            SearchAnalytics.objects.filter(
                created__gte=since,
            )
            .values("normalized_query")
            .distinct()
            .count()
        )

        successful_searches = SearchAnalytics.objects.filter(
            created__gte=since,
            result_count__gt=0,
        ).count()

        failed_searches = SearchAnalytics.objects.filter(
            created__gte=since,
            result_count=0,
        ).count()

        success_rate = (
            (successful_searches / total_searches * 100) if total_searches > 0 else 0
        )

        avg_results = (
            SearchAnalytics.objects.filter(
                created__gte=since,
                result_count__gt=0,
            ).aggregate(avg_results=Avg("result_count"))["avg_results"]
            or 0
        )

        unique_users = (
            SearchAnalytics.objects.filter(
                created__gte=since,
                user__isnull=False,
            )
            .values("user")
            .distinct()
            .count()
        )

        anonymous_searches = SearchAnalytics.objects.filter(
            created__gte=since,
            user__isnull=True,
        ).count()

        summary_data = {
            "total_searches": total_searches,
            "unique_queries": unique_queries,
            "successful_searches": successful_searches,
            "failed_searches": failed_searches,
            "success_rate": success_rate,
            "avg_results_per_search": avg_results,
            "unique_users": unique_users,
            "anonymous_searches": anonymous_searches,
        }

        self.stdout.write(f"Total Searches: {total_searches:,}")
        self.stdout.write(f"Unique Queries: {unique_queries:,}")
        self.stdout.write(f"Successful Searches: {successful_searches:,}")
        self.stdout.write(f"Failed Searches: {failed_searches:,}")
        self.stdout.write(f"Success Rate: {success_rate:.1f}%")
        self.stdout.write(f"Avg Results per Search: {avg_results:.1f}")
        self.stdout.write(f"Unique Users: {unique_users:,}")
        self.stdout.write(f"Anonymous Searches: {anonymous_searches:,}")

        return summary_data

    def generate_popular_queries_report(self, since, limit):
        """Generate popular queries report."""
        self.stdout.write(
            self.style.SUCCESS(f"\n🔥 Top {limit} Popular Queries"),
        )
        self.stdout.write("-" * 30)

        popular_queries = (
            SearchAnalytics.objects.filter(
                created__gte=since,
                result_count__gt=0,
            )
            .values("normalized_query")
            .annotate(
                search_count=Count("id"),
                avg_results=Avg("result_count"),
            )
            .order_by("-search_count")[:limit]
        )

        popular_data = []
        for i, query_data in enumerate(popular_queries, 1):
            query = query_data["normalized_query"]
            count = query_data["search_count"]
            avg_results = query_data["avg_results"]

            self.stdout.write(
                f'{i:2d}. "{query}" - {count} searches (avg {avg_results:.1f} results)',
            )

            popular_data.append(
                {
                    "rank": i,
                    "query": query,
                    "search_count": count,
                    "avg_results": avg_results,
                },
            )

        return popular_data

    def generate_failed_queries_report(self, since, limit):
        """Generate failed queries report."""
        self.stdout.write(
            self.style.WARNING(f"\n❌ Top {limit} Failed Queries (0 results)"),
        )
        self.stdout.write("-" * 30)

        failed_queries = (
            SearchAnalytics.objects.filter(
                created__gte=since,
                result_count=0,
            )
            .values("normalized_query")
            .annotate(
                search_count=Count("id"),
            )
            .order_by("-search_count")[:limit]
        )

        failed_data = []
        for i, query_data in enumerate(failed_queries, 1):
            query = query_data["normalized_query"]
            count = query_data["search_count"]

            self.stdout.write(f'{i:2d}. "{query}" - {count} failed searches')

            failed_data.append(
                {
                    "rank": i,
                    "query": query,
                    "failed_count": count,
                },
            )

        return failed_data

    def generate_performance_report(self, since):
        """Generate search performance report."""
        self.stdout.write(
            self.style.SUCCESS("\n⚡ Performance Metrics"),
        )
        self.stdout.write("-" * 30)

        # Response time analysis
        from django.db.models import Max
        from django.db.models import Min

        performance_data = SearchAnalytics.objects.filter(
            created__gte=since,
            response_time_ms__isnull=False,
        ).aggregate(
            avg_response_time=Avg("response_time_ms"),
            min_response_time=Min("response_time_ms"),
            max_response_time=Max("response_time_ms"),
        )

        # Search type distribution
        search_types = (
            SearchAnalytics.objects.filter(
                created__gte=since,
            )
            .values("search_type")
            .annotate(
                count=Count("id"),
            )
            .order_by("-count")
        )

        perf_data = {
            "response_times": performance_data,
            "search_types": list(search_types),
        }

        if performance_data["avg_response_time"]:
            self.stdout.write(
                f"Avg Response Time: {performance_data['avg_response_time']:.0f}ms",
            )
            self.stdout.write(
                f"Min Response Time: {performance_data['min_response_time']}ms",
            )
            self.stdout.write(
                f"Max Response Time: {performance_data['max_response_time']}ms",
            )
        else:
            self.stdout.write("No response time data available")

        self.stdout.write("\nSearch Type Distribution:")
        for search_type in search_types:
            self.stdout.write(
                f"  {search_type['search_type']}: {search_type['count']} searches",
            )

        return perf_data

    def generate_user_behavior_report(self, since, limit):
        """Generate user behavior report."""
        self.stdout.write(
            self.style.SUCCESS(f"\n👥 Top {limit} Active Users"),
        )
        self.stdout.write("-" * 30)

        active_users = (
            SearchAnalytics.objects.filter(
                created__gte=since,
                user__isnull=False,
            )
            .values(
                "user__email",
            )
            .annotate(
                search_count=Count("id"),
                unique_queries=Count("normalized_query", distinct=True),
                avg_results=Avg("result_count"),
            )
            .order_by("-search_count")[:limit]
        )

        user_data = []
        for i, user_data_item in enumerate(active_users, 1):
            email = user_data_item["user__email"]
            search_count = user_data_item["search_count"]
            unique_queries = user_data_item["unique_queries"]
            avg_results = user_data_item["avg_results"]

            self.stdout.write(
                f"{i:2d}. {email} - {search_count} searches, "
                f"{unique_queries} unique queries, avg {avg_results:.1f} results",
            )

            user_data.append(
                {
                    "rank": i,
                    "email": email,
                    "search_count": search_count,
                    "unique_queries": unique_queries,
                    "avg_results": avg_results,
                },
            )

        return user_data

    def export_to_json(self, data, filename):
        """Export report data to JSON file."""
        try:
            # Convert datetime objects to strings for JSON serialization
            def serialize_datetime(obj):
                if hasattr(obj, "isoformat"):
                    return obj.isoformat()
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

            with open(filename, "w") as f:
                json.dump(data, f, indent=2, default=serialize_datetime)

            self.stdout.write(
                self.style.SUCCESS(f"\n✓ Report exported to {filename}"),
            )

        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f"Error exporting to {filename}: {e}"),
            )
