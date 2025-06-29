from django.urls import path, include

urlpatterns = [
    path("admin/", include("admin_panel.urls")),
    path("challenge/", include("challenge.urls")),
    path("user/", include("user_auth.urls")),
    path("notifications/", include("notifications.urls")),
    path("", include("main.urls")),
    path("", include("user_auth.urls")),
]
