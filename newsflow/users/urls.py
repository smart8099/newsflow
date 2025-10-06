from django.urls import path

from .views import toggle_theme
from .views import user_detail_view
from .views import user_redirect_view
from .views import user_update_view

app_name = "users"
urlpatterns = [
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("~update/", view=user_update_view, name="update"),
    path("toggle-theme/", view=toggle_theme, name="toggle_theme"),
    path("<uuid:uuid>/", view=user_detail_view, name="detail"),
]
