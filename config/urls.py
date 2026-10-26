"""URL configuration: respondent portal at /, administrator screens at /manage/, Django admin at /admin/."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.portal.views import home

admin.site.site_header = "CNAP Reporting Hub: database administration"
admin.site.site_title = "CNAP Reporting Hub"
admin.site.index_title = "Administration"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "accounts/password/",
        auth_views.PasswordChangeView.as_view(success_url="/accounts/password/done/"),
        name="password_change",
    ),
    path(
        "accounts/password/done/",
        auth_views.PasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
    path("manage/", include("apps.admin_center.urls")),
    path("", include("apps.portal.urls")),
    path("", home, name="home"),
]
