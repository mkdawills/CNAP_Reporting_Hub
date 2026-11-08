from django.urls import path

from . import outcome_views as ov
from . import views

app_name = "portal"

urlpatterns = [
    path("tasks/", views.tasks, name="tasks"),
    path("tasks/<int:pk>/", views.form, name="form"),
    path("tasks/<int:pk>/preview/", views.preview, name="preview"),
    path("tasks/<int:pk>/print/", views.print_form, name="print_form"),
    path("tasks/<int:pk>/autosave/", views.autosave, name="autosave"),
    path("tasks/<int:pk>/sheet/<slug:section>/", views.sheet_template, name="sheet_template"),
    path("tasks/<int:pk>/edit/", views.edit_again, name="edit_again"),
    path("tasks/<int:pk>/opt-out/", views.opt_out, name="opt_out"),
    path("tasks/<int:pk>/mftrp-form/", views.mftrp_form, name="mftrp_form"),
    path("tasks/current-pending/<int:pk>/", views.cp_check, name="cp_check"),
    path("documents/<int:pk>/", views.helpful_doc, name="helpful_doc"),
    path("history/", views.history, name="history"),
    path("results/", views.center_results, name="center_results"),
    path("core-reports/", views.core_reports, name="core_reports"),
    path("core-reports/<int:pk>/", views.core_report, name="core_report"),
    path("profile/", views.profile, name="profile"),
    path("profile/documents/<int:pk>/", views.my_document, name="my_document"),
    path("files/<int:file_pk>/", views.download, name="download"),
    # publications and grants (self-entry)
    path("outcomes/", ov.home, name="outcomes"),
    path("outcomes/presentations/new/", ov.presentation, name="presentation_new"),
    path("outcomes/presentations/<int:pk>/", ov.presentation, name="presentation_edit"),
    path("outcomes/nudge/<int:pk>/", ov.nudge, name="outcome_nudge"),
    path("outcomes/new/<slug:kind>/", ov.new, name="outcome_new"),
    path("outcomes/<slug:kind>/<int:pk>/", ov.update, name="outcome_update"),
    path("outcomes/<slug:kind>/<int:pk>/confirm/", ov.confirm, name="outcome_confirm"),
    path("outcomes/<slug:kind>/<int:pk>/people/", ov.people, name="outcome_people"),
    path("outcomes/plans/<slug:kind>/", ov.plans, name="outcome_plans"),
    path("outcomes/delegates/add/", ov.delegate_add, name="outcome_delegate_add"),
    path("outcomes/delegates/<int:pk>/end/", ov.delegate_end, name="outcome_delegate_end"),
]
