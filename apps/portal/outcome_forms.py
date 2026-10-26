"""Forms for each publication and grant status, field for field from MW's Publication flow and Grant flow."""

from django import forms

from apps.common.enums import (
    FundingSourceType,
    GrantRole,
    PresentationType,
    PrimeOrSubaward,
    PublicationType,
)
from apps.people.models import Project, Resource

YN = [("yes", "Yes"), ("no", "No")]
MONTH = forms.DateInput(attrs={"type": "month"}, format="%Y-%m")
DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class MonthField(forms.DateField):
    """A month/year picker stored as the first day of the month."""

    widget = MONTH
    input_formats = ["%Y-%m", "%Y-%m-%d"]


def yn(label, required=True):
    return forms.TypedChoiceField(
        label=label,
        choices=YN,
        widget=forms.RadioSelect,
        required=required,
        coerce=lambda v: v == "yes",
        empty_value=None,
    )


def money(label, required=False):
    return forms.DecimalField(
        label=label,
        required=required,
        min_value=0,
        decimal_places=2,
        max_digits=14,
        widget=forms.NumberInput(attrs={"step": "1", "inputmode": "decimal"}),
    )


class _Resources(forms.Form):
    resources = forms.ModelMultipleChoiceField(
        queryset=Resource.objects.filter(is_active=True).exclude(code="admin_core"),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Center resources utilized",
    )
    resources_other_text = forms.CharField(required=False, label="If Other, what?", max_length=300)
    projects = forms.ModelMultipleChoiceField(
        queryset=Project.objects.filter(archived_at__isnull=True, is_active=True).order_by("title"),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Which CNAP projects? (choose any that apply)",
    )
    resources_required = False

    def clean(self):
        data = super().clean()
        res = data.get("resources") or []
        if self.resources_required and not res:
            self.add_error("resources", "Choose at least one Center resource.")
        if any(r.code == "other" for r in res) and not data.get("resources_other_text", "").strip():
            self.add_error("resources_other_text", "Say what Other means.")
        return data


# ----------------------------------------------------------------------------- publications


class PubPlanned(_Resources):
    title = forms.CharField(label="Anticipated title", max_length=500)
    journal = forms.CharField(label="Anticipated journal", max_length=300, required=False)
    anticipated_submission_month = MonthField(
        label="Anticipated submission month and year", required=False
    )
    publication_type = forms.ChoiceField(
        choices=PublicationType.choices, initial="journal_article", label="Type"
    )
    field_order = ["title", "journal", "anticipated_submission_month", "publication_type"]


class PubSubmitted(_Resources):
    resources_required = True
    journal = forms.CharField(
        label="Journal", max_length=300, help_text="Change it only if it’s different."
    )
    submission_date = forms.DateField(label="Date of submission", widget=DATE)
    title = forms.CharField(
        label="Title", max_length=500, help_text="Change it only if it’s different."
    )
    anticipated_publication_date = forms.DateField(
        label="Anticipated date of publication", widget=DATE, required=False
    )
    field_order = ["journal", "submission_date", "title", "anticipated_publication_date"]


class PubPublished(_Resources):
    resources_required = True
    submission_date = forms.DateField(label="Date of submission", widget=DATE)
    journal = forms.CharField(label="Journal", max_length=300)
    pubmed_url = forms.URLField(
        label="PubMed link",
        max_length=500,
        help_text="Paste the link, then use “Fill in from PubMed” to fill the details below.",
    )
    title = forms.CharField(label="Title", max_length=500)
    author_display_text = forms.CharField(
        label="Authors", widget=forms.Textarea(attrs={"rows": 2}), required=False
    )
    publication_date = forms.DateField(label="Publication date", widget=DATE, required=False)
    cnap_cited = yn("Did you cite CNAP in your journal article?")
    cnap_in_grant_index = yn("Did you list CNAP in the grant index portion of your PubMed entry?")
    has_foreign_authors = yn("Does your publication include any foreign authors?")
    foreign_component_approved = yn(
        "Has NIGMS given prior approval for the foreign component?", required=False
    )
    has_non_idea_coauthors = yn("Does it have any co-authors from non-IDeA states?")
    field_order = [
        "submission_date",
        "journal",
        "pubmed_url",
        "title",
        "author_display_text",
        "publication_date",
        "cnap_cited",
        "cnap_in_grant_index",
        "has_foreign_authors",
        "foreign_component_approved",
        "has_non_idea_coauthors",
    ]


def _pub_published_clean(self):
    data = _Resources.clean(self)
    if data.get("has_foreign_authors") and data.get("foreign_component_approved") is None:
        self.add_error(
            "foreign_component_approved",
            "Please answer: it decides whether the paper can be reported to NIH.",
        )
    if data.get("has_foreign_authors") is False:
        data["foreign_component_approved"] = None
    return data


PubPublished.clean = _pub_published_clean


class PubDeclined(forms.Form):
    decline_date = forms.DateField(label="Date of decline", widget=DATE)
    journal = forms.CharField(label="Journal", max_length=300)
    comments = forms.CharField(
        label="Comments (feedback and/or resubmission plans)",
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
    )
    resubmission_intent = yn("Do you plan to resubmit?", required=False)


# ----------------------------------------------------------------------------- grants


class GrantPlanned(_Resources):
    funding_agency = forms.CharField(label="Funding agency", max_length=200)
    opportunity_url = forms.URLField(
        label="Funding opportunity link",
        max_length=500,
        required=False,
        help_text="Paste the link to the FOA/RFA or funding announcement, if available.",
    )
    mechanism = forms.CharField(
        label="Mechanism (e.g., R01, R21, foundation grant)", max_length=120, required=False
    )
    anticipated_submission_date = MonthField(
        label="Anticipated submission month and year", required=False
    )
    project_title = forms.CharField(label="Project title", max_length=500)
    role = forms.ChoiceField(label="Your role", choices=GrantRole.choices, initial=GrantRole.PI)
    anticipated_total = money("Anticipated total budget (optional)")
    planned_estimated_direct = money("Estimated direct costs (optional; preliminary)")
    field_order = [
        "funding_agency",
        "funding_source_type",
        "opportunity_url",
        "mechanism",
        "anticipated_submission_date",
        "project_title",
        "role",
        "anticipated_total",
        "planned_estimated_direct",
    ]


class GrantSubmitted(_Resources):
    resources_required = True
    funding_agency = forms.CharField(label="Funding agency", max_length=200)
    funding_source_type = forms.ChoiceField(
        label="Funding source",
        choices=list(FundingSourceType.choices),
        help_text="For NIH’s progress report (Table 1A).",
    )
    opportunity_url = forms.URLField(
        label="Funding opportunity link", max_length=500, required=False
    )
    mechanism = forms.CharField(label="Mechanism", max_length=120, required=False)
    submission_date = forms.DateField(label="Submission date", widget=DATE)
    project_title = forms.CharField(label="Project title", max_length=500)
    role = forms.ChoiceField(label="Your role", choices=GrantRole.choices)
    requested_total = money("Total requested budget", required=True)
    requested_direct = money("Estimated direct costs (optional)")
    requested_indirect = money("Estimated indirect costs (optional)")
    field_order = [
        "funding_agency",
        "funding_source_type",
        "opportunity_url",
        "mechanism",
        "submission_date",
        "project_title",
        "role",
        "requested_total",
        "requested_direct",
        "requested_indirect",
    ]


class GrantAwarded(_Resources):
    resources_required = True
    award_notice_date = forms.DateField(label="Award notice date", widget=DATE)
    project_start_date = forms.DateField(label="Project start date", widget=DATE)
    project_end_date = forms.DateField(label="Project end date", widget=DATE)
    award_total = money("Total award amount", required=True)
    award_direct = money("Direct costs", required=True)
    award_indirect = money("Indirect costs", required=True)
    grant_number = forms.CharField(
        label="Grant number (if available)", max_length=120, required=False
    )
    prime_or_subaward = forms.ChoiceField(
        label="Prime institution or subaward",
        choices=[("", "—")] + list(PrimeOrSubaward.choices),
        required=False,
    )
    cnap_acknowledged = yn("Did you acknowledge CNAP in the proposal?")
    cnap_credited_in_publications = yn("Will CNAP be credited in resulting publications?")
    has_foreign_component = yn("Any foreign components?")
    field_order = [
        "award_notice_date",
        "project_start_date",
        "project_end_date",
        "award_total",
        "award_direct",
        "award_indirect",
        "cnap_portion",
        "grant_number",
        "prime_or_subaward",
        "cnap_acknowledged",
        "cnap_credited_in_publications",
        "has_foreign_component",
    ]

    def clean(self):
        data = super().clean()
        s, e = data.get("project_start_date"), data.get("project_end_date")
        if s and e and e < s:
            self.add_error("project_end_date", "The end date is before the start date.")
        return data


class GrantNotFunded(forms.Form):
    decision_date = forms.DateField(label="Decision date", widget=DATE)
    decision_comments = forms.CharField(
        label="Comments (review feedback, summary statement, resubmission plans)",
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
    )
    discussed_with_program_officer = yn("Was this submission discussed with a Program Officer?")
    program_officer_name = forms.CharField(
        label="Program Officer name (optional)", max_length=200, required=False
    )
    discussion_date = forms.DateField(
        label="Date of discussion (optional)", widget=DATE, required=False
    )
    feedback_shared_with_cnap = yn(
        "Was reviewer feedback provided to the CNAP project manager for post-analysis support?"
    )
    plans_to_resubmit = yn("Do you plan to resubmit this proposal?")


class PresentationForm(_Resources):
    presentation_type = forms.ChoiceField(
        label="Type", choices=PresentationType.choices, initial="conference"
    )
    title = forms.CharField(label="Title", max_length=500)
    event = forms.CharField(label="Event or meeting", max_length=300, required=False)
    location = forms.CharField(label="Location", max_length=300, required=False)
    presented_on = forms.DateField(label="Date presented", widget=DATE)
    author_display_text = forms.CharField(
        label="Presenters and authors (as listed)",
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
    )
    cnap_cited = yn("Did your presentation acknowledge CNAP?")
    field_order = [
        "presentation_type",
        "title",
        "event",
        "location",
        "presented_on",
        "author_display_text",
        "cnap_cited",
    ]


PUB_FORMS = {
    "planned": PubPlanned,
    "submitted": PubSubmitted,
    "published": PubPublished,
    "declined": PubDeclined,
}
GRANT_FORMS = {
    "planned": GrantPlanned,
    "submitted": GrantSubmitted,
    "awarded": GrantAwarded,
    "not_funded": GrantNotFunded,
}
NEXT = {
    "pub": {"planned": ["submitted"], "submitted": ["published", "declined"]},
    "grant": {"planned": ["submitted"], "submitted": ["awarded", "not_funded"]},
}
