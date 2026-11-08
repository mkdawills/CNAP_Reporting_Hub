"""
What a form version does at run time, given a respondent's answers.

Rule semantics (decisions.md, Milestone 3):
- a section or question that is the target of any "show" rule is hidden
  unless one of those rules matches;
- a target of a "hide" rule is hidden when any of those rules matches;
- "require" makes a target question required when it matches;
- "set_pathway" classifies the submission; the first matching rule wins and
  the default is a full response.
Questions inside a hidden section are neither shown nor required, and their
answers are ignored on submit.

`answers` maps question code to a value: an option code for choice questions,
text, an ISO date string, or a file id. Repeatable sections use `rows`: a list
of dicts keyed by question code.
"""

from functools import cached_property

from apps.common.enums import OPTION_QUESTION_TYPES, QuestionType, RuleAction, RuleOperator

from .models import CompletionPathway, FormVersion



class FormSchema:
    def __init__(self, version: FormVersion):
        self.version = version
        self.definition = version.form_definition

    @cached_property
    def sections(self):
        return list(
            self.version.sections.prefetch_related(
                "questions__answer_set__options", "questions__measure"
            ).order_by("sort_order")
        )

    @cached_property
    def questions(self):
        return [q for s in self.sections for q in s.questions.all()]

    @cached_property
    def by_code(self):
        return {q.code: q for q in self.questions}

    @cached_property
    def rules(self):
        return list(
            self.version.rules.select_related(
                "source_question", "value_option", "target_section", "target_question", "pathway"
            ).order_by("sort_order")
        )

    @property
    def display(self):
        return self.definition.display or {}

    @cached_property
    def optout_question(self):
        code = (self.display.get("opt_out") or {}).get("question")
        return self.by_code.get(code) if code else None

    @cached_property
    def optout_pathway(self):
        q = self.optout_question
        if not q:
            return None
        for r in self.rules:
            if r.action == RuleAction.SET_PATHWAY and r.source_question_id == q.pk:
                return r.pathway
        return None

    @cached_property
    def followup_section(self):
        """The section shown only after opting out (core and NeuroSync follow-ups)."""
        q = self.optout_question
        if not q:
            return None
        for r in self.rules:
            if r.action == RuleAction.SHOW and r.source_question_id == q.pk and r.target_section_id:
                return r.target_section
        return None

    # ------------------------------------------------------------------ rules

    @staticmethod
    def _matches(rule, answers):
        val = answers.get(rule.source_question.code)
        answered = val not in (None, "", [])
        if rule.operator == RuleOperator.IS_ANSWERED:
            return answered
        if rule.operator == RuleOperator.IS_NOT_ANSWERED:
            return not answered
        code = rule.value_option.code if rule.value_option_id else None
        if rule.operator == RuleOperator.EQUALS:
            return val == code
        return answered and val != code

    def _visibility(self, answers, *, section=None, question=None):
        shows = [
            r
            for r in self.rules
            if r.action == RuleAction.SHOW
            and (
                (section and r.target_section_id == section.pk)
                or (question and r.target_question_id == question.pk)
            )
        ]
        hides = [
            r
            for r in self.rules
            if r.action == RuleAction.HIDE
            and (
                (section and r.target_section_id == section.pk)
                or (question and r.target_question_id == question.pk)
            )
        ]
        if shows and not any(self._matches(r, answers) for r in shows):
            return False
        if any(self._matches(r, answers) for r in hides):
            return False
        return True

    def section_visible(self, section, answers):
        return self._visibility(answers, section=section)

    def question_visible(self, question, answers):
        sec = next(s for s in self.sections if s.pk == question.form_section_id)
        return self.section_visible(sec, answers) and self._visibility(answers, question=question)

    def visible_sections(self, answers):
        return [s for s in self.sections if self.section_visible(s, answers)]

    def is_required(self, question, answers):
        if not self.question_visible(question, answers):
            return False
        if question.is_required:
            return True
        return any(
            r.action == RuleAction.REQUIRE
            and r.target_question_id == question.pk
            and self._matches(r, answers)
            for r in self.rules
        )

    def pathway(self, answers):
        for r in self.rules:
            if r.action == RuleAction.SET_PATHWAY and self._matches(r, answers):
                return r.pathway
        return CompletionPathway.objects.get(code="full_response")

    def missing_required(self, answers, rows=None):
        """Questions that must be answered before submitting, in form order."""
        missing = []
        for q in self.questions:
            if q.question_type == QuestionType.INSTRUCTIONS:
                continue
            sec = next(s for s in self.sections if s.pk == q.form_section_id)
            if sec.is_repeatable:
                continue
            if self.is_required(q, answers) and answers.get(q.code) in (None, "", []):
                missing.append(q)
        return missing

    # ------------------------------------------------------------------ display

    def minutes(self):
        """Time to complete, shown to respondents (MW 2026-11-07): 10 seconds for each multiple-choice question or short
        entry, 2 minutes for each written answer, rounded up to the nearest 5 minutes. Uploads and instructions add no
        time here; a form whose display gives its own "time_label" (the progress reports' "2 page upload, plus 5 min")
        shows that wording instead. A form's display "minutes" overrides the estimate."""
        if self.display.get("minutes"):
            return int(self.display["minutes"])
        seconds = 0
        followup = self.followup_section
        for s in self.sections:
            if followup and s.pk == followup.pk:
                continue
            for q in s.questions.all():
                if q.config.get("widget") == "optout_checkbox":
                    continue
                if q.question_type in (QuestionType.INSTRUCTIONS, QuestionType.FILE):
                    continue
                seconds += 120 if q.question_type == QuestionType.LONG_TEXT else 10
        return max(5, -(-seconds // 300) * 5)

    def time_label(self):
        label = self.display.get("time_label")
        if label:  # abbreviations spelled out (MW): "plus 5 min" reads "plus about 5 minutes"
            import re

            return re.sub(r"\bplus (\d+) min\b", r"plus about \1 minutes", label).replace(" page upload", "-page upload")
        return f"About {self.minutes()} minutes"

    @staticmethod
    def is_option(question):
        return (
            question.question_type in OPTION_QUESTION_TYPES
            or question.question_type == QuestionType.SINGLE_SELECT
        )
