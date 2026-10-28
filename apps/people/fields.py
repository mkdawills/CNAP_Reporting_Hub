"""Form fields shared by the portal and the admin pages."""

from django import forms

LEAD_TYPES = ("project_leader", "pilot_awardee")


class ProjectChoiceField(forms.ModelMultipleChoiceField):
    """Projects labeled with type, PI and award years (MW 2026-10-28), e.g.
    "Sleep-dependent memory consolidation (Pilot project) · PI: Amara Okafor · 2025–2026"."""

    widget = forms.CheckboxSelectMultiple

    def __init__(self, **kw):
        from .models import Project

        kw.setdefault(
            "queryset",
            Project.objects.filter(archived_at__isnull=True, is_active=True)
            .prefetch_related("relationships__person", "relationships__relationship_type")
            .order_by("title"),
        )
        super().__init__(**kw)

    def label_from_instance(self, p):
        leads = [r for r in p.relationships.all() if r.relationship_type.code in LEAD_TYPES]
        leads.sort(
            key=lambda r: (
                r.effective_to is not None,
                -(r.effective_from.toordinal() if r.effective_from else 0),
            )
        )
        parts = [f"{p.title} ({p.get_kind_display()})"]
        if leads:
            parts.append(f"PI: {leads[0].person.first_name} {leads[0].person.last_name}")
        if p.start_date:
            parts.append(f"{p.start_date.year}–{p.end_date.year if p.end_date else 'present'}")
        return " · ".join(parts)
