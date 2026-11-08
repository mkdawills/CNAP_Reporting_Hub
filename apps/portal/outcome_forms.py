"""Forms for each publication and grant status, field for field from MW's Publication flow and Grant flow."""

from django import forms

from apps.common.enums import (
    FundingSourceType,
    GrantRole,
    PresentationType,
    PrimeOrSubaward,
    PublicationType,
)
from apps.people.fields import ProjectChoiceField
from apps.people.models import Resource

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


class _PlannedDay:
    """A planned date: month and year, plus an optional day (MW 2026-11-03)."""

    date_field = ""

    def _combine_day(self, data):
        import calendar

        when, day = data.get(self.date_field), data.pop("anticipated_day", None)
        data["anticipated_day_known"] = bool(when and day)
        if when and day:
            last = calendar.monthrange(when.year, when.month)[1]
            if day > last:
                self.add_error("anticipated_day", f"That month has only {last} days.")
            else:
                data[self.date_field] = when.replace(day=day)
        return data


def planned_day():
    return forms.IntegerField(
        label="Day (optional)", min_value=1, max_value=31, required=False,
        widget=forms.NumberInput(attrs={"style": "max-width:6em", "inputmode": "numeric"}),
        help_text="Please add the day if you know it.",
    )


class _Resources(forms.Form):
    resources = forms.ModelMultipleChoiceField(
        queryset=Resource.objects.filter(is_active=True),  # Admin Core included (MW 2026-10-26)
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Center resources utilized",
    )
    resources_other_text = forms.CharField(required=False, label="If Other, what?", max_length=300)
    projects = ProjectChoiceField(
        required=False,
        label="Which CNAP projects? (choose any that apply)",
    )
    resources_required = False
    anticipated = False  # a planned paper or proposal: resources it will use (MW 2026-11-03)

    def __init__(self, *a, own_projects=(), **kw):
        super().__init__(*a, **kw)
        if self.anticipated:
            self.fields["resources"].label = "Center resources you anticipate using"
            self.fields["projects"].label = "Which CNAP projects will this draw on? (choose any that apply)"
        # the person's own CNAP project is marked "(your project)" (MW 2026-11-03)
        self.fields["projects"].own = {p.pk for p in own_projects}

    def clean(self):
        data = super().clean()
        res = data.get("resources") or []
        if self.resources_required and not res:
            self.add_error("resources", "Please choose at least one Center resource.")
        if any(r.code == "other" for r in res) and not data.get("resources_other_text", "").strip():
            self.add_error("resources_other_text", "Please say what Other means.")
        # projects go with the project resources ticked (MW 2026-11-03)
        codes = {r.code for r in res}
        kinds = {"primary"} if "research_project" in codes else set()
        kinds |= {"pilot"} if "pilot_project" in codes else set()
        prj = [p for p in (data.get("projects") or []) if p.kind in kinds]
        data["projects"] = prj
        for code, kind, what in (("research_project", "primary", "research"), ("pilot_project", "pilot", "pilot")):
            if code in codes and not any(p.kind == kind for p in prj):
                self.add_error("projects", f"Please choose which {what} project or projects.")
        return data


# ----------------------------------------------------------------------------- publications


class PubPlanned(_PlannedDay, _Resources):
    anticipated = True
    date_field = "anticipated_submission_month"
    title = forms.CharField(label="Anticipated title", max_length=500)
    journal = forms.CharField(label="Anticipated journal", max_length=300, required=False)
    anticipated_submission_month = MonthField(
        label="Anticipated submission month and year", required=False
    )
    anticipated_day = planned_day()
    publication_type = forms.ChoiceField(
        choices=PublicationType.choices, initial="journal_article", label="Type"
    )
    publication_type_other = forms.CharField(label="Please describe", max_length=200, required=False, help_text="Shown when you choose Other. For example: data descriptor.")
    field_order = ["title", "journal", "anticipated_submission_month", "anticipated_day", "publication_type", "publication_type_other"]

    def clean(self):
        return self._combine_day(super().clean())


class PubSubmitted(_Resources):
    resources_required = True
    journal = forms.CharField(
        label="Journal", max_length=300, help_text="Please change it only if it’s different."
    )
    submission_date = forms.DateField(label="Date of submission", widget=DATE)
    title = forms.CharField(
        label="Title", max_length=500, help_text="Please change it only if it’s different."
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
        help_text="Please paste the link, then use “Fill in from PubMed” to fill the details below.",
    )
    title = forms.CharField(label="Title", max_length=500)
    author_display_text = forms.CharField(
        label="Authors",
        help_text=(
            "Please list every author, in order, exactly as they appear on the paper. "
            "For example: Okafor A, Kim H, Moreau C. "
            "“Fill in from PubMed” fills this for you."
        ),
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
    )
    publication_date = forms.DateField(label="Publication date", widget=DATE, required=False)
    cnap_cited = yn("Did your journal article acknowledge CNAP in alignment with the Stevens Amendment?")
    cnap_cited.help_text = "The “How to acknowledge CNAP” box at the top of this page explains the Stevens Amendment and gives the wording. If your article did not acknowledge CNAP, continue to report it. However, be very careful that you select No. We will reach out to determine if this can be remedied retrospectively."
    cnap_in_grant_index = yn("Did you list CNAP in the grant index portion of your PubMed entry?")
    cnap_in_grant_index.help_text = "PubMed lists a paper’s grants in its Grant support section. Please choose Yes if P20GM113109 appears there."
    has_foreign_authors = yn("Did your publication include any foreign authors?")
    foreign_component_approved = yn(
        "Has NIGMS given prior approval for the foreign component?", required=False
    )
    has_non_idea_coauthors = yn("Did your publication include any co-authors from non-IDeA states?")
    field_order = [
        "pubmed_url",
        "title",
        "journal",
        "submission_date",
        "author_display_text",
        "publication_date",
        "cnap_cited",
        "cnap_in_grant_index",
        "has_foreign_authors",
        "foreign_component_approved",
        "has_non_idea_coauthors",
    ]


RRID_CHOICES = [("yes", "Yes"), ("no", "No"), ("unsure", "Not sure")]


def _pub_published_init(self, *args, **kwargs):
    """One question per core that has an RRID, shown when that core is ticked (MW 2026-10-28)."""
    from apps.outcomes.services import rrid_resources

    _Resources.__init__(self, *args, **kwargs)
    self.rrid_fields = {}
    for r in rrid_resources():
        name = f"rrid_{r.pk}"
        f = forms.ChoiceField(
            label=f"Did you cite the {r.core.name}’s Research Resource Identifier (RRID), {r.core.rrid}, in your methods?",
            choices=RRID_CHOICES,
            widget=forms.RadioSelect,
            required=False,
            help_text=f"For example: “…recorded in the {r.core.name} ({r.core.rrid}) at Kansas State University.” "
            "The RRID lets the Center find every paper that used the core, even without the grant number.",
        )
        f.res_pk = r.pk
        self.fields[name] = f
        self.rrid_fields[r.pk] = name
    # keep each RRID question right after the resources it depends on
    order = list(self.fields)
    for name in self.rrid_fields.values():
        order.remove(name)
    at = order.index("resources_other_text") + 1 if "resources_other_text" in order else len(order)
    order[at:at] = list(self.rrid_fields.values())
    self.order_fields(order)


def rrid_answers(form):
    """{resource pk: answer} for the cores ticked on a cleaned PubPublished form."""
    picked = {r.pk for r in form.cleaned_data.get("resources") or []}
    return {
        pk: form.cleaned_data.get(name) or ""
        for pk, name in getattr(form, "rrid_fields", {}).items()
        if pk in picked
    }


PubPublished.__init__ = _pub_published_init


def _pub_published_clean(self):
    data = _Resources.clean(self)
    picked = {r.pk for r in data.get("resources") or []}
    for pk, name in self.rrid_fields.items():
        if pk in picked and not data.get(name):
            self.add_error(name, "Please answer, or choose Not sure.")
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


FEDERAL_AGENCIES = [
    ("NIH", "National Institutes of Health (NIH)"),
    ("NSF", "National Science Foundation (NSF)"),
    ("USDA", "U.S. Department of Agriculture (USDA)"),
    ("DOD", "Department of Defense (DOD)"),
    ("DOE", "Department of Energy (DOE)"),
    ("NASA", "National Aeronautics and Space Administration (NASA)"),
    ("ED", "Department of Education (ED)"),
    ("EPA", "Environmental Protection Agency (EPA)"),
    ("VA", "Department of Veterans Affairs (VA)"),
    ("CDC", "Centers for Disease Control and Prevention (CDC)"),
    ("AHRQ", "Agency for Healthcare Research and Quality (AHRQ)"),
    ("other", "Another federal agency"),
]


class _Funding(forms.Form):
    """Funding source first: Federal or Non-federal (MW 2026-11-03). Federal shows an agency list;
    Non-federal takes the funder's name. Stored as funding_source_type + funding_agency."""

    funding_source = forms.ChoiceField(
        label="Funding source",
        choices=[("federal", "Federal"), ("non_federal", "Non-federal")],
        widget=forms.RadioSelect,
    )
    federal_agency = forms.ChoiceField(
        label="Federal funding agency",
        choices=[("", "Please choose the agency")] + FEDERAL_AGENCIES,
        required=False,
    )
    federal_agency_other = forms.CharField(
        label="If another federal agency, which one?", max_length=200, required=False
    )
    funding_agency = forms.CharField(
        label="Funding agency",
        max_length=200,
        required=False,
        help_text="Please give the foundation, state program, or other non-federal funder.",
    )

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        init = self.initial
        src, agency = init.get("funding_source_type"), init.get("funding_agency", "")
        if src and "funding_source" not in init:
            init["funding_source"] = "non_federal" if src == "non_federal" else "federal"
            if src != "non_federal":
                codes = {c for c, _ in FEDERAL_AGENCIES}
                up = (agency or "").upper()
                init["federal_agency"] = up if up in codes else "other"
                if up not in codes:
                    init["federal_agency_other"] = agency
                init["funding_agency"] = ""

    def clean(self):
        data = super().clean()
        src = data.get("funding_source")
        if src == "federal":
            agency = data.get("federal_agency")
            if not agency:
                self.add_error("federal_agency", "Please choose the federal agency.")
            elif agency == "other":
                other = (data.get("federal_agency_other") or "").strip()
                if not other:
                    self.add_error("federal_agency_other", "Please name the federal agency.")
                data["funding_agency"] = other
            else:
                data["funding_agency"] = agency
            data["funding_source_type"] = "nih" if agency == "NIH" else "federal_other"
        elif src == "non_federal":
            if not (data.get("funding_agency") or "").strip():
                self.add_error("funding_agency", "Please give the funder’s name.")
            data["funding_source_type"] = "non_federal"
        return data


class GrantPlanned(_Funding, _PlannedDay, _Resources):
    anticipated = True
    date_field = "anticipated_submission_date"
    opportunity_url = forms.URLField(
        label="Funding opportunity link",
        max_length=500,
        required=False,
        help_text="Please paste the link to the Funding Opportunity Announcement (FOA), Request for Applications (RFA), or other funding announcement, if available.",
    )
    mechanism = forms.CharField(
        label="Funding mechanism",
        max_length=120,
        required=False,
        help_text="The mechanism is the funder’s program type, for example an NIH R01 or R21, an NSF standard grant, or a foundation grant. If you’re not sure, please leave it blank.",
    )
    anticipated_submission_date = MonthField(
        label="Anticipated submission month and year", required=False
    )
    anticipated_day = planned_day()
    project_title = forms.CharField(
        label="Proposal title",
        max_length=500,
        help_text="Please give the title of the proposal you’re submitting, not your CNAP project’s title.",
    )
    role = forms.ChoiceField(
        label="Your role on this proposal",
        choices=GrantRole.choices,
        initial=GrantRole.PI,
        help_text="Please give your role on this proposal, for example Principal Investigator (PI) or Co-Investigator.",
    )
    role_other = forms.CharField(label="Please describe", max_length=200, required=False, help_text="Shown when you choose Other. For example: Senior Personnel.")
    anticipated_total = money("Anticipated total budget (optional)")
    planned_estimated_direct = money("Estimated direct costs (optional, preliminary)")
    field_order = [
        "funding_source",
        "federal_agency",
        "federal_agency_other",
        "funding_agency",
        "opportunity_url",
        "mechanism",
        "anticipated_submission_date",
        "anticipated_day",
        "project_title",
        "role",
        "role_other",
        "anticipated_total",
        "planned_estimated_direct",
    ]

    def clean(self):
        return self._combine_day(super().clean())


class GrantSubmitted(_Funding, _Resources):
    resources_required = True
    opportunity_url = forms.URLField(
        label="Funding opportunity link", max_length=500, required=False
    )
    mechanism = forms.CharField(
        label="Funding mechanism",
        max_length=120,
        required=False,
        help_text="The mechanism is the funder’s program type, for example an NIH R01 or R21, an NSF standard grant, or a foundation grant. If you’re not sure, please leave it blank.",
    )
    submission_date = forms.DateField(label="Submission date", widget=DATE)
    cayuse_ipf = forms.CharField(
        label="Cayuse IPF number (optional)",
        max_length=40,
        required=False,
        help_text="The Cayuse number is the number Cayuse assigned to your proposal in K-State’s central repository. The Center uses it to cross-check this record.",
    )
    project_title = forms.CharField(
        label="Proposal title",
        max_length=500,
        help_text="Please give the title of the proposal you submitted, not your CNAP project’s title.",
    )
    role = forms.ChoiceField(label="Your role", choices=GrantRole.choices)
    role_other = forms.CharField(label="Please describe", max_length=200, required=False, help_text="Shown when you choose Other. For example: Senior Personnel.")
    requested_total = money("Total requested budget", required=True)
    requested_direct = money("Estimated direct costs (optional)")
    requested_indirect = money("Estimated indirect costs (optional)")
    field_order = [
        "funding_source",
        "federal_agency",
        "federal_agency_other",
        "funding_agency",
        "opportunity_url",
        "mechanism",
        "submission_date",
        "cayuse_ipf",
        "project_title",
        "role",
        "role_other",
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
    cnap_portion = money("Your portion of the total award")
    grant_number = forms.CharField(
        label="Grant number (if available)", max_length=120, required=False
    )
    prime_or_subaward = forms.ChoiceField(
        label="Prime institution or subaward",
        choices=[("", "—")] + list(PrimeOrSubaward.choices),
        required=False,
    )
    cnap_acknowledged = yn("Did you acknowledge CNAP in the proposal?")
    cnap_acknowledged.help_text = "A proposal acknowledges CNAP in its Facilities and Other Resources section, or where it describes preliminary data. The “How to acknowledge CNAP” box at the top of this page gives the wording."
    cnap_credited_in_publications = yn("Will CNAP be credited in resulting publications?")
    cnap_credited_in_publications.help_text = "Under the Stevens Amendment, publications from this award must acknowledge CNAP. The box at the top of this page gives the wording."
    has_foreign_component = yn("Will this award have any foreign components?")
    has_foreign_component.help_text = "A foreign component is work done outside the United States, or work by someone employed by a foreign organization. NIH requires prior approval for foreign components."
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

    shared_role = (
        False  # set by the view when the person is MPI, Co-I, key personnel, consultant, or other
    )

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields[
            "award_total"
        ].help_text = "Please give direct plus indirect costs for the entire project period, not one year."
        self.fields["cnap_portion"].help_text = (
            "If you’re the sole Principal Investigator (PI), please leave this blank: the full award counts. "
            "Please fill this in only if you’re a Multiple Principal Investigator (MPI), Co-Principal Investigator (Co-PI), a collaborator, or on a subaward. "
            "Please give the part of the total award that is yours (direct plus indirect, entire project period). NIH counts this part, not the whole award. "
            "For example: on a $1,200,000 award where your subaward is $250,000, please enter 250000."
        )

    def clean(self):
        data = super().clean()
        tot, part = data.get("award_total"), data.get("cnap_portion")
        if (self.shared_role or data.get("prime_or_subaward") == "subaward") and part is None:
            self.add_error(
                "cnap_portion",
                "Because you share this award or it’s a subaward, please give your portion.",
            )
        if tot is not None and part is not None and part > tot:
            self.add_error("cnap_portion", "Your portion can’t be more than the total award.")
        d_, i_ = data.get("award_direct"), data.get("award_indirect")
        if tot is not None and d_ is not None and i_ is not None and abs((d_ + i_) - tot) > 1:
            self.add_error(
                "award_total", "Direct plus indirect costs don’t add up to the total award."
            )
        s, e = data.get("project_start_date"), data.get("project_end_date")
        if s and e and e < s:
            self.add_error("project_end_date", "The end date is before the start date.")
        return data


class GrantNotFunded(forms.Form):
    decision_date = forms.DateField(label="Decision date", widget=DATE)
    decision_comments = forms.CharField(
        label="Your initial reflections on the decision (optional)",
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text="If you like, share your own first thoughts about the decision here. Don’t paste your reviewer comments here. Reviewer comments go to the Center Director by email.",
    )
    discussed_with_program_officer = yn("Was this submission discussed with a Program Officer?")
    feedback_shared_with_cnap = yn("Have you emailed your reviewer feedback to the Center Director?")
    feedback_shared_with_cnap.help_text = (
        "The dropdown at the top of this page explains what happens with your feedback. "
        "If you haven’t sent it yet, please choose No, and please email it when you can."
    )
    plans_to_resubmit = yn("Do you plan to resubmit this proposal?")


class PresentationForm(_Resources):
    presentation_type = forms.ChoiceField(
        label="Type", choices=PresentationType.choices, initial="conference"
    )
    title = forms.CharField(label="Title", max_length=500)
    event = forms.CharField(label="Name of Event or Meeting", max_length=300, required=False)
    venue = forms.CharField(label="University or venue", max_length=300, required=False)
    city = forms.CharField(label="City", max_length=120, required=False)
    state_region = forms.CharField(label="State or province", max_length=120, required=False)
    country = forms.CharField(label="Country", max_length=120, required=False, initial="United States")
    presented_on = forms.DateField(
        label="Date presented",
        widget=DATE,
        help_text="Only add a talk or poster after it has taken place. NeuroSync presentations do not qualify.",
    )
    author_display_text = forms.CharField(
        label="Presenters and authors",
        help_text="Please list them in the order shown on the talk or poster, for example: Okafor A, Kim H, Moreau C.",
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
    )
    cnap_cited = yn("Did your presentation acknowledge CNAP in alignment with the Stevens Amendment?")
    cnap_cited.help_text = "The “How to acknowledge CNAP” box at the top of this page explains the Stevens Amendment and gives the wording. If your presentation did not acknowledge CNAP, continue to report it. However, be very careful that you select No. We will reach out to determine if this can be remedied retrospectively."
    presentation_type_other = forms.CharField(label="Please describe", max_length=200, required=False, help_text="Shown when you choose Other. For example: panel discussion.")
    field_order = [
        "presentation_type",
        "presentation_type_other",
        "title",
        "event",
        "venue",
        "city",
        "state_region",
        "country",
        "presented_on",
        "author_display_text",
        "cnap_cited",
    ]

    def clean_presented_on(self):
        """Talks are entered once given (MW 2026-10-28): counts stay real, and the acknowledgment is known."""
        from django.utils import timezone

        d = self.cleaned_data["presented_on"]
        if d and d > timezone.localdate():
            raise forms.ValidationError(
                "That date hasn’t happened yet. Please add this talk or poster after you’ve given it."
            )
        return d


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


# Faint in-field examples (MW 2026-11-03): every free-text and number field shows what a good
# entry looks like. Dropdowns and yes/no fields can't carry placeholders, and date boxes
# already show their mm/dd/yyyy mask.
PLACEHOLDERS = {
    "title": "For example: Sleep and memory consolidation in adolescent mice",
    "journal": "For example: Journal of Neurophysiology",
    "author_display_text": "For example: Okafor A, Kim H, Moreau C",
    "pubmed_url": "For example: https://pubmed.ncbi.nlm.nih.gov/12345678/",
    "comments": "Anything you would like us to know.",
    "federal_agency_other": "For example: Department of Energy (DOE)",
    "funding_agency": "For example: Kansas INBRE",
    "opportunity_url": "For example: https://grants.nih.gov/grants/guide/pa-files/PAR-25-123.html",
    "mechanism": "For example: R01",
    "project_title": "For example: Neural circuits of flexible decision making",
    "family_title": "For example: the earlier proposal’s title, word for word",
    "cayuse_ipf": "For example: 24-0381",
    "grant_number": "For example: R01NS123456",
    "anticipated_total": "For example: 1200000",
    "planned_estimated_direct": "For example: 800000",
    "requested_total": "For example: 1200000",
    "requested_direct": "For example: 800000",
    "requested_indirect": "For example: 400000",
    "award_total": "For example: 1200000",
    "award_direct": "For example: 800000",
    "award_indirect": "For example: 400000",
    "cnap_portion": "For example: 250000",
    "event": "For example: Society for Neuroscience (SfN) Annual Meeting",
    "venue": "For example: Kansas State University",
    "city": "For example: Manhattan",
    "state_region": "For example: Kansas",
    "resources_other_text": "For example: REDCap support",
    "decision_comments": "Your initial reflections, if you like.",
    "rppr_year": "For example: 9",
    "rppr_submitted_year": "For example: 9",
    "rppr_awarded_year": "For example: 9",
}

_PLACEHOLDER_WIDGETS = (forms.TextInput, forms.Textarea, forms.URLInput, forms.NumberInput)


def apply_placeholders(form_class):
    for name, field in form_class.base_fields.items():
        ph = PLACEHOLDERS.get(name)
        if ph and isinstance(field.widget, _PLACEHOLDER_WIDGETS):
            field.widget.attrs.setdefault("placeholder", ph)


def _apply_all():
    import inspect

    for obj in list(globals().values()):
        if inspect.isclass(obj) and issubclass(obj, forms.BaseForm):
            apply_placeholders(obj)


_apply_all()
