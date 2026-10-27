"""
Live results computed from submitted responses (used by Center results, the
administrator Results page and snapshot generation).

Only full responses count toward item results; structured opt-outs are counted
separately. N/A answers are counted but excluded from n and the mean.
"""

import math
from dataclasses import dataclass, field

from django.db.models import Count, Q

from apps.common.enums import AssignmentStatus, QuestionType
from apps.reporting.models import Answer, Assignment, Response

SCALE_TYPES = (QuestionType.LIKERT,)


@dataclass
class ItemStat:
    question: object
    n: int = 0
    mean: float | None = None
    sd: float | None = None
    na: int = 0
    counts: dict = field(default_factory=dict)  # value -> count, values 1..5

    @property
    def distribution(self):
        """[(value, count, percent)] for 1..5."""
        return [
            (v, self.counts.get(v, 0), (100 * self.counts.get(v, 0) / self.n) if self.n else 0)
            for v in range(1, 6)
        ]


def assignments_for(form_definition, period):
    return Assignment.objects.filter(form_definition=form_definition, reporting_period=period)


def completion(form_definition, period):
    qs = assignments_for(form_definition, period)
    agg = qs.aggregate(
        assigned=Count("id", filter=~Q(status=AssignmentStatus.EXEMPT)),
        exempt=Count("id", filter=Q(status=AssignmentStatus.EXEMPT)),
        submitted=Count("id", filter=Q(status=AssignmentStatus.SUBMITTED)),
        opted_out=Count("id", filter=Q(status=AssignmentStatus.COMPLETED_OPT_OUT)),
        in_progress=Count("id", filter=Q(status=AssignmentStatus.IN_PROGRESS)),
        not_started=Count("id", filter=Q(status=AssignmentStatus.NOT_STARTED)),
    )
    agg["complete"] = agg["submitted"] + agg["opted_out"]
    agg["rate"] = round(100 * agg["complete"] / agg["assigned"]) if agg["assigned"] else 0
    pathways = (
        qs.filter(status=AssignmentStatus.COMPLETED_OPT_OUT)
        .values("completion_pathway__name")
        .annotate(n=Count("id"))
    )
    agg["opt_out_by_pathway"] = {p["completion_pathway__name"]: p["n"] for p in pathways}
    return agg


def _ids(responses):
    """Response ids as a plain list. A nested subquery here gets a very slow plan on fresh databases."""
    return list(responses.values_list("pk", flat=True))


def full_responses(form_definition, period):
    return Response.objects.filter(
        is_current=True,
        submitted_at__isnull=False,
        assignment__form_definition=form_definition,
        assignment__reporting_period=period,
        assignment__status=AssignmentStatus.SUBMITTED,
    )


def item_stats(form_definition, period, responses=None):
    """One ItemStat per rating question, in form order, across all versions used in the period."""
    responses = responses if responses is not None else full_responses(form_definition, period)
    answers = Answer.objects.filter(
        response_id__in=_ids(responses), question__question_type__in=SCALE_TYPES
    ).select_related("question__form_section", "question__measure", "option")
    by_key, order = {}, []
    for a in answers:
        q = a.question
        key = q.measure_id or q.code
        if key not in by_key:
            by_key[key] = ItemStat(question=q)
            order.append(key)
        st = by_key[key]
        if a.option and a.option.value is not None:
            st.counts[a.option.value] = st.counts.get(a.option.value, 0) + 1
        elif a.option:
            st.na += 1
    for st in by_key.values():
        vals = [v for v, c in st.counts.items() for _ in range(c)]
        st.n = len(vals)
        if vals:
            st.mean = sum(vals) / st.n
            st.sd = (
                math.sqrt(sum((v - st.mean) ** 2 for v in vals) / (st.n - 1)) if st.n > 1 else 0.0
            )
    order.sort(
        key=lambda k: (by_key[k].question.form_section.sort_order, by_key[k].question.sort_order)
    )
    return [by_key[k] for k in order]
