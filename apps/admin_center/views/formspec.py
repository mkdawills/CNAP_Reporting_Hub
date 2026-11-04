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
                "n_questions": len([q for q in schema.questions if q.question_type != "instructions"]),
                "minutes": schema.minutes(),
            }
        )
    return render(request, "manage/forms.html", {"rows": rows})


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
            qs.append({"q": q, "opts": opts, "type": q.get_question_type_display()})
        sections.append({"s": s, "qs": qs})
    return render(
        request,
        "manage/form_detail.html",
        {"fd": fd, "schema": schema, "sections": sections},
    )
