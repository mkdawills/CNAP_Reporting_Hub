"""Move "Your document should contain the following:" from the progress report intro to the top of the
Accomplishments section it introduces, on every version (MW 2026-11-02). Directions only."""

from django.db import migrations

LEADS = (" Your document should contain the following:", " Include the following:")
LINE = "Your document should contain the following:"


def forwards(apps, schema_editor):
    FormVersion = apps.get_model("forms_engine", "FormVersion")
    FormSection = apps.get_model("forms_engine", "FormSection")
    for v in FormVersion.objects.filter(form_definition__code__startswith="progress_"):
        text = v.intro_text or ""
        cut = next((lead for lead in LEADS if text.rstrip().endswith(lead.strip())), None)
        if not cut:
            continue
        FormVersion.objects.filter(pk=v.pk).update(intro_text=text.rstrip()[: -len(cut.strip())].rstrip())
        sec = FormSection.objects.filter(form_version=v, code="accomplishments").first()
        if sec and not (sec.instructions or "").startswith(LINE):
            FormSection.objects.filter(pk=sec.pk).update(instructions=LINE + "\n" + (sec.instructions or ""))


class Migration(migrations.Migration):
    dependencies = [("forms_engine", "0004_short_file_name_example")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
