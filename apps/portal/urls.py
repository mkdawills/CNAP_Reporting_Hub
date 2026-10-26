from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("tasks/", views.tasks, name="tasks"),
    path("history/", views.history, name="history"),
    path("results/", views.center_results, name="center_results"),
    path("profile/", views.profile, name="profile"),
]
