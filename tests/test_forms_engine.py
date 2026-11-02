"""Milestone 3: the real instruments load verbatim, version cleanly, and their rules behave."""

import copy
import json

import pytest

from apps.common.enums import VersionStatus
from apps.forms_engine import loader
from apps.forms_engine.models import FormDefinition, FormVersion, Measure
from apps.forms_engine.runtime import FormSchema


@pytest.fixture
def instruments(reference):
    return loader.load_all()


def schema(code):
    return FormSchema(FormDefinition.objects.get(code=code).active_version)


def test_all_instruments_load(instruments):
    # 16 Piestar instruments plus the yearly NIH documents task (MW 2026-10-27)
    assert len(instruments) == 17
    assert FormDefinition.objects.count() == 17
    assert FormVersion.objects.filter(status=VersionStatus.ACTIVE).count() == 17
    assert loader.universal_rule_check()


def test_loading_again_changes_nothing(instruments):
    again = loader.load_all()
    assert {s for *_, s in again} == {"unchanged"}
    assert FormVersion.objects.count() == 17


def test_item_counts_match_sources(instruments):
    def count(code, section):
        return schema(code).version.sections.get(code=section).questions.count()

    assert count("bn_core_survey", "quality") == 15 and count("bn_core_survey", "frequency") == 11
    assert count("ni_core_survey", "quality") == 7 and count("ni_core_survey", "frequency") == 3
    assert count("cn_core_survey", "quality") == 16 and count("cn_core_survey", "frequency") == 7
    assert count("neurosync_survey", "ratings") == 7
    assert (
        count("mentee_survey", "mentors") == 19 and count("mentor_questionnaire", "mentoring") == 19
    )
    assert count("ts_synergy", "synergy") == 9 and count("ts_admin_core", "admin_core") == 9
    assert (
        count("ts_grant_writing", "grant_writing") == 3
        and count("ts_reporting_hub", "reporting_hub") == 3
    )


def test_source_wording_is_verbatim(instruments):
    me = schema("mentee_survey").by_code
    assert me["item_05"].prompt == "Enhance(s) my performance within the grant program."
    assert (
        me["item_06"].prompt == "Make(s) time to regularly meet with me."
    )  # no period, as in the source
    ts = schema("ts_synergy").version.sections.get(code="synergy")
    assert ts.instructions.startswith("Please indicate how much you agree")
    na = schema("ts_synergy").by_code["item_01"].answer_set.options.get(code="neither")
    assert na.label == "3 - Neither Disagree nor Agree"
    # intros shortened with MW's approval (2026-10-28); question wording stays verbatim
    assert "Word document" in schema("progress_research").version.intro_text
    assert "PDF" not in schema("progress_pilot").version.intro_text


def test_measure_scales_are_consistent(instruments):
    assert Measure.objects.get(code="bn_quality_01").scale_kind == "quality"
    assert Measure.objects.get(code="bn_frequency_01").scale_kind == "frequency"
    assert Measure.objects.get(code="neurosync_01").scale_kind == "agreement"


def test_core_optout_swaps_sections_and_sets_pathway(instruments):
    s = schema("bn_core_survey")
    full = [x.code for x in s.visible_sections({})]
    assert full == ["optout", "quality", "frequency", "open"]
    opted = [x.code for x in s.visible_sections({"optout": "yes"})]
    assert opted == ["optout", "nonuse"]
    assert s.pathway({"optout": "yes"}).code == "core_non_use"
    assert s.pathway({}).code == "full_response"
    assert s.followup_section.code == "nonuse"


def test_team_science_items_required_unless_opted_out(instruments):
    s = schema("ts_synergy")
    assert len(s.missing_required({})) == 12  # 9 items + 3 open-ended
    assert s.missing_required({"optout": "yes"}) == []
    assert s.pathway({"optout": "yes"}).code == "ts_not_involved"


def test_reporting_hub_has_no_optout(instruments):
    assert schema("ts_reporting_hub").optout_question is None


def test_progress_report_file_required(instruments):
    s = schema("progress_pilot")
    quick = ["b1a", "c3", "c4", "c5a", "c5c", "f3", "g9"]  # quick RPPR questions (MW 2026-10-27)
    assert [q.code for q in s.missing_required({})] == ["proj_status", "file"] + quick
    no = {c: "no" for c in quick} | {"c5c": "yes"}
    assert s.missing_required({"file": "12", "proj_status": "ongoing"} | no) == []
    ended = [q.code for q in s.missing_required({"file": "12", "proj_status": "ended"} | no)]
    assert ended == ["ended_on"]  # FY27 guidance: "ENDED AS OF MM/DD/YYYY"
    assert s.time_label() == "1–2 page upload, plus 5 min"


def test_time_estimates_are_sensible(instruments):
    assert 8 <= schema("bn_core_survey").minutes() <= 15
    assert schema("ni_core_survey").minutes() < schema("bn_core_survey").minutes()


def test_assignment_rules_follow_decisions(instruments):
    def rules(code):
        return {
            (r.scope, r.relationship_type.code if r.relationship_type else None, r.per_context)
            for r in FormDefinition.objects.get(code=code).assignment_rules.filter(is_active=True)
        }

    assert rules("bn_core_survey") == {("universal", None, False)}
    assert (
        FormDefinition.objects.get(code="bn_core_survey")
        .assignment_rules.get()
        .excluded_relationship_type.code
        == "core_director"
    )
    assert rules("mentee_survey") == {
        ("relationship", "pilot_awardee", True),
        ("relationship", "project_leader", True),
    }
    assert rules("mentor_questionnaire") == {
        ("relationship", "pilot_mentor", False),
        ("relationship", "primary_mentor", False),
    }
    assert rules("progress_core") == {("relationship", "core_director", True)}


def test_changed_fixture_becomes_new_version(instruments, tmp_path):
    spec = json.loads((loader.FIXTURE_DIR / "ts_reporting_hub.json").read_text())
    changed = copy.deepcopy(spec)
    changed["sections"][0]["questions"][0]["prompt"] = "Changed wording."
    fd, fv, status = loader.load_spec(changed)
    assert status == "new version" and fv.version_no == 2 and fv.status == VersionStatus.ACTIVE
    assert fd.versions.get(version_no=1).status == VersionStatus.RETIRED
    # drafts wait for activation
    changed["sections"][0]["questions"][0]["prompt"] = "Changed again."
    fd, fv3, status = loader.load_spec(changed, draft=True)
    assert fv3.status == VersionStatus.DRAFT and fd.active_version.version_no == 2


def test_measure_scale_conflict_refused(instruments):
    spec = json.loads((loader.FIXTURE_DIR / "neurosync_survey.json").read_text())
    spec["code"] = "conflict_test"
    spec["sections"][1]["questions"][0]["answer_set"] = "Quality"  # neurosync_01 is agreement
    with pytest.raises(loader.FormFixtureError):
        loader.load_spec(spec)
