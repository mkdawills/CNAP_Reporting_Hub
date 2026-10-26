"""
Database rules for assignments, responses and answers that Django's ORM
cannot express (review 15.1, 15.3).

1. An assignment's copied form_definition_id and context_kind must be the
   truth from form_versions and form_definitions. Together with the model's
   context_shape CHECK and the one_assignment_per_context UNIQUE (nulls not
   distinct), this is what makes generation idempotent.
2. A response's form_version must be its assignment's form_version.
3. An answer uses at most one value column.
4. Question options are frozen once any answer references them: their label,
   code, value and N/A flag cannot change, and they cannot move to another
   answer set. Editing a used answer set means cloning it. This is one of the
   two places a trigger is the right tool, because "no referencing rows exist"
   cannot be written as a constraint.
"""

from django.db import migrations

FORWARD = """
-- 1. Copied columns on assignments.
CREATE UNIQUE INDEX assignments_id_form_version_unique ON assignments (id, form_version_id);

ALTER TABLE assignments
  ADD CONSTRAINT assignments_version_definition_fk
  FOREIGN KEY (form_version_id, form_definition_id)
  REFERENCES form_versions (id, form_definition_id);

ALTER TABLE assignments
  ADD CONSTRAINT assignments_definition_context_fk
  FOREIGN KEY (form_definition_id, context_kind)
  REFERENCES form_definitions (id, context_kind);

-- 2. A response answers the version its assignment was issued for.
ALTER TABLE responses
  ADD CONSTRAINT responses_assignment_version_fk
  FOREIGN KEY (assignment_id, form_version_id)
  REFERENCES assignments (id, form_version_id);

-- 3. At most one value column per answer.
ALTER TABLE answers
  ADD CONSTRAINT answers_single_value CHECK (
    (CASE WHEN value_text IS NOT NULL THEN 1 ELSE 0 END)
  + (CASE WHEN value_number IS NOT NULL THEN 1 ELSE 0 END)
  + (CASE WHEN value_date IS NOT NULL THEN 1 ELSE 0 END)
  + (CASE WHEN option_id IS NOT NULL THEN 1 ELSE 0 END)
  + (CASE WHEN person_value_id IS NOT NULL THEN 1 ELSE 0 END)
  + (CASE WHEN project_value_id IS NOT NULL THEN 1 ELSE 0 END) <= 1
  );

-- 4. Freeze options that have been answered.
CREATE OR REPLACE FUNCTION question_options_freeze() RETURNS trigger AS $$
BEGIN
  IF (NEW.label IS DISTINCT FROM OLD.label
      OR NEW.code IS DISTINCT FROM OLD.code
      OR NEW.value IS DISTINCT FROM OLD.value
      OR NEW.is_na_option IS DISTINCT FROM OLD.is_na_option
      OR NEW.answer_set_id IS DISTINCT FROM OLD.answer_set_id)
     AND (EXISTS (SELECT 1 FROM answers a WHERE a.option_id = OLD.id)
          OR EXISTS (SELECT 1 FROM answer_selected_options s WHERE s.option_id = OLD.id)) THEN
    RAISE EXCEPTION 'question option % is frozen: it has been used in a submitted answer. Clone the answer set instead.', OLD.id
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER question_options_freeze_trigger
  BEFORE UPDATE ON question_options
  FOR EACH ROW EXECUTE FUNCTION question_options_freeze();
"""

REVERSE = """
DROP TRIGGER IF EXISTS question_options_freeze_trigger ON question_options;
DROP FUNCTION IF EXISTS question_options_freeze();
ALTER TABLE answers DROP CONSTRAINT IF EXISTS answers_single_value;
ALTER TABLE responses DROP CONSTRAINT IF EXISTS responses_assignment_version_fk;
ALTER TABLE assignments DROP CONSTRAINT IF EXISTS assignments_definition_context_fk;
ALTER TABLE assignments DROP CONSTRAINT IF EXISTS assignments_version_definition_fk;
DROP INDEX IF EXISTS assignments_id_form_version_unique;
"""


class Migration(migrations.Migration):
    dependencies = [("reporting", "0001_initial"), ("forms_engine", "0002_constraints")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
