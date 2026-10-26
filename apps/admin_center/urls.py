from django.urls import path

from .views import audit, home, people, roster

app_name = "manage"

urlpatterns = [
    path("", home.home, name="home"),
    # people and relationships
    path("people/", people.people, name="people"),
    path("people/new/", people.person_new, name="person_new"),
    path("people/<int:pk>/", people.person, name="person"),
    path("people/<int:pk>/edit/", people.person_edit, name="person_edit"),
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
    # audit
    path("audit/", audit.audit, name="audit"),
]
