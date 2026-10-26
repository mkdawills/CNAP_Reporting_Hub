"""
Database rules for the form engine that Django's ORM cannot express.

1. A question's copied scale_kind must equal its answer set's, and a measure
   attached to the question must have that same scale (addendum B.1): an
   agreement question can never be attached to a frequency measure.
2. A form assignment rule's copied context kinds must equal the form's and
   the relationship type's (review 15.7), so the rule_shape CHECK in the model
   is checking true values.
"""

from django.db import migrations

FORWARD = """
ALTER TABLE questions
  ADD CONSTRAINT questions_answer_set_scale_fk
  FOREIGN KEY (answer_set_id, scale_kind)
  REFERENCES answer_sets (id, scale_kind);

ALTER TABLE questions
  ADD CONSTRAINT questions_measure_scale_fk
  FOREIGN KEY (measure_id, scale_kind)
  REFERENCES measures (id, scale_kind);

ALTER TABLE form_assignment_rules
  ADD CONSTRAINT form_assignment_rules_form_context_fk
  FOREIGN KEY (form_definition_id, form_context_kind)
  REFERENCES form_definitions (id, context_kind);

ALTER TABLE form_assignment_rules
  ADD CONSTRAINT form_assignment_rules_relationship_context_fk
  FOREIGN KEY (relationship_type_id, relationship_context_kind)
  REFERENCES relationship_types (id, context_kind);
"""

REVERSE = """
ALTER TABLE form_assignment_rules DROP CONSTRAINT IF EXISTS form_assignment_rules_relationship_context_fk;
ALTER TABLE form_assignment_rules DROP CONSTRAINT IF EXISTS form_assignment_rules_form_context_fk;
ALTER TABLE questions DROP CONSTRAINT IF EXISTS questions_measure_scale_fk;
ALTER TABLE questions DROP CONSTRAINT IF EXISTS questions_answer_set_scale_fk;
"""


class Migration(migrations.Migration):
    dependencies = [("forms_engine", "0001_initial"), ("people", "0002_constraints")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
