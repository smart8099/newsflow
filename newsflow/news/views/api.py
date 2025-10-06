"""
API views for AJAX/HTMX functionality in news app.
"""

import json
from datetime import timedelta

from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from ..models import Article
from ..models import CategoryChoices
from ..models import NewsSource
from ..models import UserInteraction


@csrf_exempt
def track_article_click(request):
    """
    AJAX endpoint to track article clicks for analytics.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            article_id = data.get("article_id")

            if not article_id:
                return JsonResponse(
                    {"status": "error", "message": "Article ID required"},
                )

            # Get the article
            try:
                article = Article.objects.get(id=article_id)
            except Article.DoesNotExist:
                return JsonResponse({"status": "error", "message": "Article not found"})

            # Increment view count
            article.increment_view_count()

            # Record user interaction if user is authenticated
            if request.user.is_authenticated:
                UserInteraction.record_interaction(
                    user=request.user,
                    article=article,
                    action=UserInteraction.ActionType.CLICK,
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
                )

                # Mark article as read for web clicks (as requested)
                from ..models import ReadArticle

                ReadArticle.objects.get_or_create(
                    user=request.user,
                    article=article,
                )

            return JsonResponse({"status": "success"})

        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})

    return JsonResponse({"status": "error", "message": "Invalid request method"})


@csrf_exempt
def bookmark_article(request):
    """
    AJAX endpoint to bookmark/unbookmark articles.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"status": "error", "message": "Authentication required"})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            article_id = data.get("article_id")

            if not article_id:
                return JsonResponse(
                    {"status": "error", "message": "Article ID required"},
                )

            try:
                article = Article.objects.get(id=article_id)
            except Article.DoesNotExist:
                return JsonResponse({"status": "error", "message": "Article not found"})

            # Toggle bookmark
            from ..models import BookmarkedArticle

            bookmark, created = BookmarkedArticle.objects.get_or_create(
                user=request.user,
                article=article,
            )

            if not created:
                # Remove bookmark
                bookmark.delete()
                is_bookmarked = False
            else:
                is_bookmarked = True

            # Record interaction (only record bookmark action)
            if is_bookmarked:
                UserInteraction.record_interaction(
                    user=request.user,
                    article=article,
                    action=UserInteraction.ActionType.BOOKMARK,
                )

            return JsonResponse(
                {
                    "status": "success",
                    "is_bookmarked": is_bookmarked,
                },
            )

        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})

    return JsonResponse({"status": "error", "message": "Invalid request method"})


@csrf_exempt
def like_article(request):
    """
    AJAX endpoint to like/unlike articles.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"status": "error", "message": "Authentication required"})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            article_id = data.get("article_id")

            if not article_id:
                return JsonResponse(
                    {"status": "error", "message": "Article ID required"},
                )

            try:
                article = Article.objects.get(id=article_id)
            except Article.DoesNotExist:
                return JsonResponse({"status": "error", "message": "Article not found"})

            # Toggle like
            from ..models import LikedArticle

            like, created = LikedArticle.objects.get_or_create(
                user=request.user,
                article=article,
            )

            if not created:
                # Remove like
                like.delete()
                is_liked = False
            else:
                is_liked = True

            # Record interaction (only record like action)
            if is_liked:
                UserInteraction.record_interaction(
                    user=request.user,
                    article=article,
                    action=UserInteraction.ActionType.LIKE,
                )

            return JsonResponse(
                {
                    "status": "success",
                    "is_liked": is_liked,
                },
            )

        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})

    return JsonResponse({"status": "error", "message": "Invalid request method"})


def load_more_articles(request):
    """
    HTMX endpoint for infinite scrolling.
    Returns additional articles as HTML fragments using the same templates as main pages.
    """
    page = request.GET.get("page", "1")
    category = request.GET.get("category", "all")
    page_type = request.GET.get("type", "home")
    query = request.GET.get("q", "")

    # Get filter parameters
    sentiment = request.GET.get("sentiment")
    source = request.GET.get("source")
    sort = request.GET.get("sort", "latest")

    try:
        page_num = int(page)
        per_page = 6  # Load 6 articles per page to match main page sections
        offset = (page_num - 1) * per_page
    except (ValueError, TypeError):
        return render(request, "news/partials/infinite_scroll_end.html")

    def apply_filters(queryset):
        """Apply common filters to queryset."""
        if sentiment:
            queryset = queryset.filter(sentiment_label=sentiment)
        if source:
            queryset = queryset.filter(source__id=source)
        return queryset

    # Get articles based on page type
    if page_type == "search":
        if not query:
            articles = []
        else:
            try:
                # Use advanced search
                search_type = request.GET.get("search_type", "phrase")
                if search_type in ["phrase", "plain", "web"]:
                    articles_qs = Article.objects.advanced_search(query, search_type)
                else:
                    articles_qs = Article.objects.search(query)

                articles_qs = apply_filters(articles_qs)
                articles = list(articles_qs[offset : offset + per_page])
            except Exception:
                articles = []

    elif page_type == "category":
        queryset = (
            Article.objects.published()
            .select_related("source")
            .prefetch_related("categories")
        )
        if category != "all":
            queryset = queryset.filter(
                Q(source__primary_category=category) | Q(categories__slug=category),
            ).distinct()

        queryset = apply_filters(queryset)
        articles = list(queryset[offset : offset + per_page])

    elif page_type == "trending":
        queryset = (
            Article.objects.published()
            .filter(
                published_at__gte=timezone.now() - timedelta(hours=24),
            )
            .select_related("source")
            .prefetch_related("categories")
        )
        queryset = apply_filters(queryset)
        articles = list(queryset.order_by("-view_count")[offset : offset + per_page])

    elif page_type == "for-you":
        # Simplified for-you logic for infinite scroll
        if request.user.is_authenticated:
            user_interactions = UserInteraction.objects.filter(
                user=request.user,
            ).values_list("article_id", flat=True)
            queryset = Article.objects.published().exclude(id__in=user_interactions)
        else:
            queryset = Article.objects.published()

        queryset = apply_filters(queryset)
        articles = list(
            queryset.order_by("-view_count", "-published_at")[
                offset : offset + per_page
            ],
        )

    else:  # home or default
        queryset = (
            Article.objects.published()
            .select_related("source")
            .prefetch_related("categories")
        )
        queryset = apply_filters(queryset)
        articles = list(queryset.order_by("-published_at")[offset : offset + per_page])

    # Calculate pagination info
    has_more = len(articles) == per_page
    next_page = page_num + 1 if has_more else None

    context = {
        "articles": articles,
        "page_type": page_type,
        "next_page": next_page,
        "has_more": has_more,
    }

    return render(request, "news/partials/infinite_scroll_content.html", context)


@csrf_exempt
@csrf_exempt
def save_user_preferences(request):
    """
    AJAX endpoint to save user category and source preferences.
    Used by the onboarding modal.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"status": "error", "message": "Authentication required"})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            categories = data.get("categories", [])
            sources = data.get("sources", [])

            print(
                f"Received preferences - Categories: {categories}, Sources: {sources}",
            )  # Debug

            # Validate categories
            valid_categories = [code for code, _ in CategoryChoices.choices]
            categories = [cat for cat in categories if cat in valid_categories]

            # Validate sources
            if sources:
                valid_sources = list(
                    NewsSource.objects.filter(
                        id__in=sources,
                    ).values_list("id", flat=True),
                )
            else:
                valid_sources = []

            # Save preferences
            user_profile = request.user.profile

            # Get category and source objects
            from ..models import Category

            category_objects = Category.objects.filter(slug__in=categories)
            source_objects = NewsSource.objects.filter(id__in=valid_sources)

            # Mark as onboarded and set preferences
            user_profile.is_onboarded = True
            user_profile.save()

            # Set ManyToMany relationships
            user_profile.preferred_categories.set(category_objects)
            user_profile.preferred_sources.set(source_objects)

            print(
                f"Successfully saved preferences for user {request.user.email}",
            )  # Debug

            return JsonResponse(
                {
                    "status": "success",
                    "message": "Preferences saved successfully",
                },
            )

        except Exception as e:
            return JsonResponse(
                {
                    "status": "error",
                    "message": f"Error saving preferences: {e!s}",
                },
            )

    return JsonResponse({"status": "error", "message": "Invalid request method"})


@require_GET
def autocomplete_suggestions(request):
    """
    HTML autocomplete suggestions for HTMX search dropdown.
    Returns rendered HTML instead of JSON for better integration.
    """
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return render(
            request,
            "news/partials/autocomplete_suggestions.html",
            {"suggestions": []},
        )

    try:
        # Get article title suggestions
        title_suggestions = Article.objects.autocomplete_search(query, 5)
        suggestions = []

        # Add title suggestions with proper icons
        for item in title_suggestions[:3]:
            suggestions.append(
                {
                    "text": item["title"][:60]
                    + ("..." if len(item["title"]) > 60 else ""),
                    "full_text": item["title"],
                    "type": "article",
                    "icon": "📰",
                },
            )

        # Add category suggestions if query matches
        for code, name in CategoryChoices.choices:
            if query.lower() in name.lower() and len(suggestions) < 5:
                suggestions.append(
                    {
                        "text": name,
                        "full_text": name,
                        "type": "category",
                        "icon": "📂",
                    },
                )

        # Add source suggestions if query matches
        source_suggestions = NewsSource.objects.filter(
            name__icontains=query,
            is_active=True,
        ).values("name")[:2]

        for source in source_suggestions:
            if len(suggestions) < 5:
                suggestions.append(
                    {
                        "text": source["name"],
                        "full_text": source["name"],
                        "type": "source",
                        "icon": "🌐",
                    },
                )

        return render(
            request,
            "news/partials/autocomplete_suggestions.html",
            {
                "suggestions": suggestions,
                "query": query,
            },
        )

    except Exception:
        # Return empty suggestions on error
        return render(
            request,
            "news/partials/autocomplete_suggestions.html",
            {"suggestions": []},
        )


@csrf_exempt
def track_share(request):
    """AJAX endpoint to track article shares."""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            article_id = data.get("article_id")
            platform = data.get("platform", "unknown")

            if not article_id:
                return JsonResponse(
                    {"status": "error", "message": "Article ID required"},
                )

            try:
                article = Article.objects.get(id=article_id)
            except Article.DoesNotExist:
                return JsonResponse({"status": "error", "message": "Article not found"})

            # Record interaction for authenticated users
            if request.user.is_authenticated:
                UserInteraction.record_interaction(
                    user=request.user,
                    article=article,
                    action=UserInteraction.ActionType.SHARE,
                    metadata={"platform": platform},
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
                )

            return JsonResponse(
                {
                    "status": "success",
                    "message": "Share tracked",
                    "platform": platform,
                },
            )

        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "Invalid JSON"})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})

    return JsonResponse({"status": "error", "message": "POST method required"})
