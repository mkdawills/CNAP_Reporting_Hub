"""Period names: the Center calls the two collections Fall (surveyed in January) and Spring (May/June)."""

from django.db import migrations


def relabel(apps, schema_editor):
    ReportingPeriod = apps.get_model("reporting", "ReportingPeriod")
    for p in ReportingPeriod.objects.filter(sequence__in=[1, 2]):
        season = "Fall" if p.sequence == 1 else "Spring"
        old_word = p.short_label.split()[-1] if p.short_label else ""
        if old_word in {"Jan", "January", "June", "May"}:
            p.short_label = f"Y{p.grant_year} {season}"
            p.name = f"Year {p.grant_year} {season}"
            p.save(update_fields=["short_label", "name"])


class Migration(migrations.Migration):
    dependencies = [("reporting", "0003_alter_assignment_options_alter_response_options")]
    operations = [migrations.RunPython(relabel, migrations.RunPython.noop)]
