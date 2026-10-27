"""Forms for the administrator screens. Validation messages are written for MW."""

from django import forms

from apps.common.enums import ProjectKind
from apps.people.models import Core, Person, Project, RelationshipType


class PersonForm(forms.ModelForm):
    email = forms.EmailField(required=False, help_text="Their main e-mail. Sign-in links go here.")

    class Meta:
        model = Person
        fields = ["first_name", "last_name", "institution", "department", "position_title", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}
        help_texts = {
            "institution": "Leave as Kansas State University for K-State people. Anyone else signs in by emailed link."
        }


class PersonEditForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = [
            "first_name",
            "last_name",
            "institution",
            "department",
            "position_title",
            "era_commons_id",
            "orcid",
            "senior_key",
            "degrees",
            "foreign_org",
            "foreign_country",
            "trainee_level",
            "is_active",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
            "senior_key": forms.Select(
                choices=[
                    ("unknown", "Automatic (PD/PI and RP Leaders)"),
                    ("true", "Yes"),
                    ("false", "No"),
                ]
            ),
        }
        labels = {"is_active": "Active (receives forms)"}

    def clean_orcid(self):
        from apps.people.services import normalize_orcid

        try:
            return normalize_orcid(self.cleaned_data.get("orcid"))
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc


class EmailForm(forms.Form):
    email = forms.EmailField()
    make_primary = forms.BooleanField(required=False, label="Make this the main address")


class RelationshipForm(forms.Form):
    relationship_type = forms.ModelChoiceField(
        queryset=RelationshipType.objects.filter(is_active=True), label="Relationship"
    )
    project = forms.ModelChoiceField(
        queryset=Project.objects.active().filter(is_active=True), required=False
    )
    core = forms.ModelChoiceField(
        queryset=Core.objects.active().filter(is_active=True), required=False
    )
    start = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), label="Starts")


class HandoffForm(forms.Form):
    new_person = forms.ModelChoiceField(queryset=Person.objects.active(), label="New holder")
    start = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), label="Starts")


class EndForm(forms.Form):
    end = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), label="Ends")


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["title", "kind", "start_date", "end_date", "is_active", "notes"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {"kind": "Type", "is_active": "Active"}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["kind"].choices = [
            (ProjectKind.PRIMARY, "Research project (RPL)"),
            (ProjectKind.PILOT, "Pilot project (PPL)"),
        ]


class RosterUploadForm(forms.Form):
    file = forms.FileField(
        help_text="A .csv or .xlsx with columns for first name, last name and e-mail."
    )
