"""Read-only form pages for administrators (MW 2026-11-03): every form, and what each one asks."""

from django.shortcuts import get_object_or_404, render

from apps.forms_engine.models import FormDefinition
from apps.forms_engine.runtime import FormSchema

from ..decorators import admin_view


@admin_view
def forms(request):
    rows = []
    for fd in FormDefinition.objects.filter(archived_at__isnull=True).order_by("sort_order"):
        v = fd.active_version
        if not v:
            continue
        schema = FormSchema(v)
        rows.append(
            {
                "fd": fd,
                "version": v,
                "n_questions": len(
                    [q for q in schema.questions if q.question_type != "instructions"]
                ),
                "minutes": schema.minutes(),
            }
        )
    return render(request, "manage/forms.html", {"rows": rows})


@admin_view
def form_blank(request, code):
    """The blank survey or report to print, as PDF or Word (MW 2026-11-09: "where is the print feature?")."""
    from django.core.exceptions import PermissionDenied

    from apps.accounts import access
    from apps.common.enums import ConfidentialityClass
    from apps.reporting.services import documents

    fd = get_object_or_404(FormDefinition, code=code, archived_at__isnull=True)
    if fd.confidentiality_class == ConfidentialityClass.MENTORING and not access.can_read_mentoring(
        request.user
    ):
        raise PermissionDenied
    fmt = "docx" if request.GET.get("fmt") == "docx" else "pdf"
    return documents.file_response(
        [documents.blank_blocks(fd.active_version)], fd.name, f"{fd.name} blank", fmt
    )


@admin_view
def form_detail(request, code):
    fd = get_object_or_404(FormDefinition, code=code, archived_at__isnull=True)
    schema = FormSchema(fd.active_version)
    sections = []
    for s in schema.sections:
        qs = []
        for q in s.questions.all():
            if q.question_type == "instructions":
                continue
            opts = [o.label for o in q.answer_set.options.all()] if q.answer_set_id else []
            kind = q.get_question_type_display()
            # Don't repeat the choices when the type's name already lists them ("Yes / No · Yes / No").
            if " / ".join(opts) == kind:
                opts = []
            qs.append({"q": q, "opts": opts, "type": kind})
        sections.append({"s": s, "qs": qs})
    return render(
        request,
        "manage/form_detail.html",
        {"fd": fd, "schema": schema, "sections": sections},
    )
