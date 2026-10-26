from django.urls import path

from . import outcome_views as ov
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
    # publications and grants (self-entry)
    path("outcomes/", ov.home, name="outcomes"),
    path("outcomes/new/<slug:kind>/", ov.new, name="outcome_new"),
    path("outcomes/<slug:kind>/<int:pk>/", ov.update, name="outcome_update"),
    path("outcomes/<slug:kind>/<int:pk>/confirm/", ov.confirm, name="outcome_confirm"),
    path("outcomes/plans/<slug:kind>/", ov.plans, name="outcome_plans"),
    path("outcomes/delegates/add/", ov.delegate_add, name="outcome_delegate_add"),
    path("outcomes/delegates/<int:pk>/end/", ov.delegate_end, name="outcome_delegate_end"),
]
