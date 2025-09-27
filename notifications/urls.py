from django.urls import path
from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notifications_view, name="notifications"),
    path("stream/<int:channel>/", views.stream_view, name="stream"),
]
