"""Sign-in pages: password (throttled), emailed link, and the 6-digit code for confidential forms."""

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from . import signin


def _safe_next(request, default="/tasks/"):
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return nxt
    return default


class LoginView(auth_views.LoginView):
    """Django's login, refusing for 15 minutes after repeated failures for a username or address."""

    def get_template_names(self):
        from apps.common import prototype

        return [prototype.template(self.request, "login", "registration/login.html")]

    def post(self, request, *args, **kwargs):
        username = request.POST.get("username", "")
        ip = signin.client_ip(request)
        if signin.too_many_failures(username, ip):
            form = self.get_form()
            form.errors.clear()
            return self.render_to_response(
                self.get_context_data(form=form, throttled=True, next=_safe_next(request, ""))
            )
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        signin.note_failure(self.request.POST.get("username", ""), signin.client_ip(self.request))
        return super().form_invalid(form)


def admin_login(request):
    """Django's database-admin sign-in goes through the same throttled page."""
    nxt = _safe_next(request, "/admin/")
    from urllib.parse import quote

    return redirect(f"/accounts/login/?next={quote(nxt)}")


def link_request(request):
    """Enter an email address; get a sign-in link if it's on file. The reply is the same either way."""
    sent = False
    if request.method == "POST":
        signin.request_link(request.POST.get("email", ""), ip=signin.client_ip(request))
        sent = True
    from apps.common import prototype

    return render(
        request,
        prototype.template(request, "link", "registration/link_request.html"),
        {"sent": sent, "days": signin.LINK_DAYS, "email": request.POST.get("email", "")},
    )


def link_login(request, token):
    """GET shows a Sign in button (so mail scanners can't use the link up); POST uses the link."""
    link = signin.find_link(token)
    if request.method == "POST" and link:
        user = signin.use_link(token, ip=signin.client_ip(request))
        if user:
            login(request, user, backend="apps.accounts.backends.RoleBackend")
            request.session["signed_in_by_link"] = True
            request.session["link_email"] = signin.last_link_email(user)
            request.session.pop("code_verified", None)
            request.session.pop("code_sent", None)
            return redirect(_safe_next(request))
        link = None
    return render(
        request,
        "registration/link_login.html",
        {"link": link, "next": _safe_next(request, ""), "days": signin.LINK_DAYS},
    )


@login_required
def link_code(request):
    """Confirm a 6-digit code before opening a confidential mentoring form from a link session."""
    person = request.user.person
    nxt = _safe_next(request)
    if not request.session.get("signed_in_by_link") or request.session.get("code_verified"):
        return redirect(nxt)
    error = ""
    if request.method == "POST" and request.POST.get("action") == "resend":
        if signin.send_code(person, request.session.get("link_email")):
            messages.success(request, "We sent a new code.")
        else:
            messages.warning(
                request,
                "We’ve sent several codes in the last few minutes. Please use the latest one, or try again shortly.",
            )
        return redirect(f"{request.path}?next={nxt}")
    if request.method == "POST":
        if signin.check_code(person, request.POST.get("code", "")):
            request.session["code_verified"] = True
            return redirect(nxt)
        error = "That code didn’t match, or it has expired. Check the newest email, or send a new code."
    elif not request.session.get("code_sent"):
        signin.send_code(person, request.session.get("link_email"))
        request.session["code_sent"] = True
    return render(
        request,
        "registration/link_code.html",
        {
            "next": nxt,
            "error": error,
            "minutes": signin.CODE_MINUTES,
            "email": request.session.get("link_email") or person.primary_email,
        },
    )
