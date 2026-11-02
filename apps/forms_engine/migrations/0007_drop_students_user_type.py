"""NIGMS Table 2 has no "Students" user type (MW 2026-11-02). Remove that choice from the Core Usage Report's
user-type list when no answer uses it; students are counted in their own column."""

from django.db import migrations


def forwards(apps, schema_editor):
    Question = apps.get_model("forms_engine", "Question")
    QuestionOption = apps.get_model("forms_engine", "QuestionOption")
    Answer = apps.get_model("reporting", "Answer")
    sets = set(
        Question.objects.filter(
            code="user_type", form_version__form_definition__code="core_usage_report"
        ).values_list("answer_set_id", flat=True)
    )
    for o in QuestionOption.objects.filter(answer_set_id__in=sets, label="Students"):
        if not Answer.objects.filter(option=o).exists():
            o.delete()


class Migration(migrations.Migration):
    dependencies = [("forms_engine", "0006_plans_wording"), ("reporting", "0001_initial")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
