"""Plans section wording on every version of the progress reports (MW 2026-11-02). Directions only."""

from django.db import migrations

SWAPS = [
    ("to accomplish the goals and objectives.", "to accomplish your project goals and objectives."),
    ("ensure that the approach is scientifically rigorous", "ensure that the approach continues to be scientifically rigorous"),
]


def forwards(apps, schema_editor):
    FormSection = apps.get_model("forms_engine", "FormSection")
    for s in FormSection.objects.filter(instructions__contains="scientifically rigorous"):
        text = s.instructions
        for a, b in SWAPS:
            text = text.replace(a, b)
        if text != s.instructions:
            FormSection.objects.filter(pk=s.pk).update(instructions=text)


class Migration(migrations.Migration):
    dependencies = [("forms_engine", "0005_document_contents_line")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
