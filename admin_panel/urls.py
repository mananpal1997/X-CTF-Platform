from django.urls import path
from . import views

app_name = "admin"

urlpatterns = [
    path("", views.admin_index, name="admin_index"),
    path("users/", views.user_list, name="user_list"),
    path("users/<int:user_id>/edit/", views.user_edit, name="user_edit"),
    path("challenges/", views.challenge_list, name="challenge_list"),
    path(
        "challenges/<int:challenge_id>/edit-metadata/",
        views.challenge_edit_metadata,
        name="challenge_edit_metadata",
    ),
    path("sandboxes/", views.sandbox_list, name="sandbox_list"),
    path("submissions/", views.submission_list, name="submission_list"),
    path("docker-containers/", views.docker_containers, name="docker_containers"),
    path(
        "docker-containers/stop/<str:container_id>/",
        views.docker_stop_container,
        name="docker_stop_container",
    ),
    path(
        "docker-containers/remove/<str:container_id>/",
        views.docker_remove_container,
        name="docker_remove_container",
    ),
    path("send-notifications/", views.send_notifications, name="send_notifications"),
]
