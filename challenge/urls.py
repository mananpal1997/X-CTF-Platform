from django.urls import path
from . import views

urlpatterns = [
    path("<int:challenge_id>/", views.start_challenge, name="start_challenge"),
    path("submit-flag/<int:challenge_id>/", views.submit_flag, name="submit_flag"),
]
