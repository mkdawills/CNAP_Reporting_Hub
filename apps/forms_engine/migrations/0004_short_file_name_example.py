"""Shorter file-name example in the progress report directions, on every version (MW 2026-11-02: "Cain_Accomplishments
is sufficient"). Directions only; no answers change."""

import re

from django.db import migrations

NEW = "Name it with your last name and what it is, for example Cain_Accomplishments."
PATTERNS = [
    r"Name it Last name \+ [^.]*?Date, for example Cain_Accomplishments_3-20-20\.",
    r"Please use the following file naming convention: [^(]*\(e\.g\., Cain_Accomplishments_3-20-20[^)]*\)\.",
]


def forwards(apps, schema_editor):
    FormVersion = apps.get_model("forms_engine", "FormVersion")
    for v in FormVersion.objects.filter(intro_text__contains="Cain_Accomplishments_"):
        text = v.intro_text
        for p in PATTERNS:
            text = re.sub(p, NEW, text)
        if text != v.intro_text:
            FormVersion.objects.filter(pk=v.pk).update(intro_text=text)


class Migration(migrations.Migration):
    dependencies = [("forms_engine", "0003_remove_formdefinition_evaluation_staff_can_view_and_more")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
