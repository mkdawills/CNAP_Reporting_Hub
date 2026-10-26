"""
The metric registry: every number the platform reports, with a plain-language
definition. MetricDefinition rows mirror this list (manage.py sync_metrics) so a
snapshot can name the registry version that produced it.
"""

REGISTRY_VERSION = 1

METRICS = [
    {
        "code": "completion",
        "name": "Completion rate",
        "domain": "participation",
        "definition_text": "Complete assignments (submitted or structured opt-out) divided by assignments that are not exempt, for one form in one period.",
        "dimensions": ["form"],
    },
    {
        "code": "item_mean",
        "name": "Item mean",
        "domain": "survey",
        "definition_text": "Mean of the numeric answers to one rating item from full responses only. N/A answers and opt-outs are excluded; n is the number of numeric answers. Items with the same measure are combined across form versions.",
        "dimensions": ["form", "measure"],
    },
    {
        "code": "item_distribution",
        "name": "Answer distribution",
        "domain": "survey",
        "definition_text": "Count and percent of numeric answers at each scale point (1 to 5) for one rating item; percents use n as the denominator. Stored in the detail of item_mean.",
        "dimensions": ["form", "measure", "value"],
    },
    {
        "code": "historical_item_mean",
        "name": "Historical item mean (imported)",
        "domain": "survey",
        "definition_text": "An item mean copied from a Year 6 to Year 9 report, with its SD in the detail where the report gives one. There is no n, distribution or drill-down.",
        "dimensions": ["form", "measure"],
    },
]


def sync():
    from .models import MetricDefinition

    for m in METRICS:
        MetricDefinition.objects.update_or_create(
            code=m["code"],
            defaults={
                "name": m["name"],
                "definition_text": m["definition_text"],
                "version": REGISTRY_VERSION,
                "domain": m["domain"],
                "dimensions": m["dimensions"],
            },
        )
