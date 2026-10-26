"""
Database rules for CNAP relationships that Django's ORM cannot express
(Architecture Review, section 2.1). This migration is the schema of record
for them; read it with the models side by side.

1. Composite foreign keys keep the copied columns on person_relationships
   (context_kind, is_single_holder, project_kind) equal to the truth on
   relationship_types and projects, and limit project-scoped types to the
   project kinds they are allowed to attach to.
2. Exclusion constraints (btree_gist) forbid the same relationship twice with
   overlapping dates, and more than one holder at a time for single-holder
   types (Project Leader, Pilot Awardee). Core Director is not single-holder:
   CNAP allows co-directors (review 15.10).
3. project_people and core_people are views over person_relationships, so a
   person's link to a project or core is stored exactly once.
"""

from django.contrib.postgres.operations import BtreeGistExtension
from django.db import migrations

FORWARD = """
-- 1. Copied columns must match their source rows.
ALTER TABLE person_relationships
  ADD CONSTRAINT person_relationships_type_context_fk
  FOREIGN KEY (relationship_type_id, context_kind)
  REFERENCES relationship_types (id, context_kind);

ALTER TABLE person_relationships
  ADD CONSTRAINT person_relationships_type_single_holder_fk
  FOREIGN KEY (relationship_type_id, is_single_holder)
  REFERENCES relationship_types (id, is_single_holder);

ALTER TABLE person_relationships
  ADD CONSTRAINT person_relationships_project_kind_fk
  FOREIGN KEY (project_id, project_kind)
  REFERENCES projects (id, kind);

ALTER TABLE person_relationships
  ADD CONSTRAINT person_relationships_allowed_project_kind_fk
  FOREIGN KEY (relationship_type_id, project_kind)
  REFERENCES relationship_type_project_kinds (relationship_type_id, project_kind);

-- 2. No duplicate of the same relationship with overlapping dates.
ALTER TABLE person_relationships
  ADD CONSTRAINT person_relationships_no_overlapping_duplicate
  EXCLUDE USING gist (
    person_id WITH =,
    relationship_type_id WITH =,
    coalesce(project_id, 0) WITH =,
    coalesce(core_id, 0) WITH =,
    daterange(effective_from, effective_to, '[]') WITH &&
  );

-- Single-holder types: one person per project or core at a time.
ALTER TABLE person_relationships
  ADD CONSTRAINT person_relationships_single_holder
  EXCLUDE USING gist (
    relationship_type_id WITH =,
    coalesce(project_id, 0) WITH =,
    coalesce(core_id, 0) WITH =,
    daterange(effective_from, effective_to, '[]') WITH &&
  ) WHERE (is_single_holder);

-- 3. Views: who is on a project / in a core, read from relationships.
CREATE VIEW project_people AS
  SELECT pr.id AS person_relationship_id,
         pr.project_id,
         pr.person_id,
         rt.code AS role_code,
         rt.name AS role_name,
         pr.effective_from,
         pr.effective_to,
         (pr.effective_to IS NULL OR pr.effective_to >= CURRENT_DATE) AND pr.effective_from <= CURRENT_DATE AS is_current
    FROM person_relationships pr
    JOIN relationship_types rt ON rt.id = pr.relationship_type_id
   WHERE pr.context_kind = 'project';

CREATE VIEW core_people AS
  SELECT pr.id AS person_relationship_id,
         pr.core_id,
         pr.person_id,
         rt.code AS role_code,
         rt.name AS role_name,
         pr.effective_from,
         pr.effective_to,
         (pr.effective_to IS NULL OR pr.effective_to >= CURRENT_DATE) AND pr.effective_from <= CURRENT_DATE AS is_current
    FROM person_relationships pr
    JOIN relationship_types rt ON rt.id = pr.relationship_type_id
   WHERE pr.context_kind = 'core';
"""

REVERSE = """
DROP VIEW IF EXISTS core_people;
DROP VIEW IF EXISTS project_people;
ALTER TABLE person_relationships DROP CONSTRAINT IF EXISTS person_relationships_single_holder;
ALTER TABLE person_relationships DROP CONSTRAINT IF EXISTS person_relationships_no_overlapping_duplicate;
ALTER TABLE person_relationships DROP CONSTRAINT IF EXISTS person_relationships_allowed_project_kind_fk;
ALTER TABLE person_relationships DROP CONSTRAINT IF EXISTS person_relationships_project_kind_fk;
ALTER TABLE person_relationships DROP CONSTRAINT IF EXISTS person_relationships_type_single_holder_fk;
ALTER TABLE person_relationships DROP CONSTRAINT IF EXISTS person_relationships_type_context_fk;
"""


class Migration(migrations.Migration):
    dependencies = [("people", "0001_initial")]

    operations = [
        BtreeGistExtension(),
        migrations.RunSQL(FORWARD, REVERSE),
    ]
