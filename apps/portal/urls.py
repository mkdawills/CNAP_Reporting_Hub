from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("tasks/", views.tasks, name="tasks"),
    path("tasks/<int:pk>/", views.form, name="form"),
    path("tasks/<int:pk>/preview/", views.preview, name="preview"),
    path("tasks/<int:pk>/opt-out/", views.opt_out, name="opt_out"),
    path("history/", views.history, name="history"),
    path("results/", views.center_results, name="center_results"),
    path("profile/", views.profile, name="profile"),
    path("files/<int:file_pk>/", views.download, name="download"),
]
