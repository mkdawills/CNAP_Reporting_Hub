from django.urls import path

from .views import audit, home, outcomes, people, periods, quality, results, roster

app_name = "manage"

urlpatterns = [
    path("", home.home, name="home"),
    path("documents/add/", home.doc_add, name="doc_add"),
    path("documents/<int:pk>/remove/", home.doc_remove, name="doc_remove"),
    # people and relationships
    path("people/", people.people, name="people"),
    path("people/new/", people.person_new, name="person_new"),
    path("people/<int:pk>/", people.person, name="person"),
    path("people/<int:pk>/edit/", people.person_edit, name="person_edit"),
    path("people/<int:pk>/effort/", people.person_effort, name="person_effort"),
    path("people/<int:pk>/apply-docs/", people.person_apply_docs, name="person_apply_docs"),
    path("people/<int:pk>/account/", people.person_account, name="person_account"),
    path("people/<int:pk>/roster/", people.person_roster, name="person_roster"),
    path("people/<int:pk>/emails/add/", people.person_email_add, name="person_email_add"),
    path(
        "people/<int:pk>/emails/<int:email_pk>/remove/",
        people.person_email_remove,
        name="person_email_remove",
    ),
    path(
        "people/<int:pk>/emails/<int:email_pk>/primary/",
        people.person_email_primary,
        name="person_email_primary",
    ),
    path("people/<int:pk>/relationships/add/", people.relationship_add, name="relationship_add"),
    path(
        "people/<int:pk>/relationships/<int:rel_pk>/end/",
        people.relationship_end,
        name="relationship_end",
    ),
    path(
        "people/<int:pk>/relationships/<int:rel_pk>/handoff/",
        people.relationship_handoff,
        name="relationship_handoff",
    ),
    # projects and cores
    path("projects/", people.projects, name="projects"),
    path("projects/new/", people.project_new, name="project_new"),
    path("projects/<int:pk>/", people.project, name="project"),
    # roster import
    path("roster/", roster.roster_imports, name="roster_imports"),
    path("roster/upload/", roster.roster_upload, name="roster_upload"),
    path("roster/<int:pk>/", roster.roster_review, name="roster_import"),
    path("roster/<int:pk>/decide/", roster.roster_decide, name="roster_decide"),
    # periods, launch, dashboard
    path("periods/", periods.periods, name="periods"),
    path("periods/new/", periods.period_new, name="period_new"),
    path("periods/<int:pk>/action/", periods.period_action, name="period_action"),
    path("periods/<int:pk>/emails/", periods.period_emails, name="period_emails"),
    path("periods/<int:pk>/emails/send/", periods.period_emails_send, name="period_emails_send"),
    path("periods/<int:pk>/emails/auto/", periods.period_emails_auto, name="period_emails_auto"),
    path("periods/<int:pk>/launch/", periods.launch, name="launch"),
    path("periods/<int:pk>/launch/go/", periods.launch_go, name="launch_go"),
    path(
        "periods/<int:pk>/launch/roster/<int:person_pk>/",
        periods.roster_from_launch,
        name="roster_from_launch",
    ),
    path("periods/<int:pk>/generate/", periods.generate_assignments, name="generate_assignments"),
    path("dashboard/", periods.dashboard, name="dashboard"),
    path("assignments/<int:pk>/action/", periods.assignment_action, name="assignment_action"),
    # results
    path("results/", results.results, name="results"),
    path("results/<str:label>/<slug:code>/", results.form_report, name="form_report"),
    path("results/<str:label>/<slug:code>/themes/", results.save_themes, name="save_themes"),
    path("results/<str:label>/<slug:code>/export/", results.export_report, name="export_report"),
    path("responses/<int:pk>/", results.response, name="response"),
    # data checks and audit
    # publications and grants
    path("outcomes/", outcomes.outcomes, name="outcomes"),
    path("outcomes/publications/new/", outcomes.publication_edit, name="publication_new"),
    path("outcomes/publications/<int:pk>/", outcomes.publication_edit, name="publication_edit"),
    path("outcomes/grants/new/", outcomes.grant_edit, name="grant_new"),
    path("outcomes/grants/<int:pk>/", outcomes.grant_edit, name="grant_edit"),
    path("outcomes/<str:kind>/<int:pk>/ack/", outcomes.set_ack, name="set_ack"),
    path("outcomes/export/<slug:kind>/", outcomes.export, name="outcomes_export"),
    path("outcomes/reminders/send/", outcomes.send_reminders, name="outcomes_send_reminders"),
    path("outcomes/rppr/mark/", outcomes.mark_rppr, name="outcomes_mark_rppr"),
    path("checks/", quality.checks, name="quality"),
    path("checks/dismiss/", quality.dismiss, name="quality_dismiss"),
    path("audit/", audit.audit, name="audit"),
]
