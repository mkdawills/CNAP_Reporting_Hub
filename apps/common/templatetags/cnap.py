"""Template helpers shared by every screen."""

import re

from django import template
from django.utils.html import conditional_escape, format_html
from django.utils.safestring import mark_safe

register = template.Library()

# A sentence ends with . ! or ? (optionally followed by a closing quote or
# bracket) and the next one starts with a capital, digit, quote or bracket.
# Titles such as "Dr." and "e.g." do not end a sentence.
_SPLIT = re.compile(
    r"(?<!\bDr)(?<!\bMr)(?<!\bMs)(?<!\bMrs)(?<!\bvs)(?<!\be\.g)(?<!\bi\.e)(?<!\betc)"
    r"([.!?][\"”’)]?)\s+(?=[A-Z“\"(0-9])"
)


@register.filter(is_safe=True)
def stack(value):
    """Directions with several sentences: one sentence per line (decisions.md)."""
    if value is None:
        return ""
    text = conditional_escape(str(value))
    return mark_safe(_SPLIT.sub(r"\1<br>", str(text)))


@register.filter(is_safe=True)
def guidance(value):
    """
    Section instructions: blank lines separate paragraphs; lines starting with
    "- " become a bulleted list; a line ending with ":" before a list is a
    small heading. Each paragraph's sentences are stacked.
    """
    if not value:
        return ""
    out, bullets = [], []

    def flush():
        if bullets:
            items = "".join(format_html("<li>{}</li>", b) for b in bullets)
            out.append(f'<ul class="guide">{items}</ul>')
            bullets.clear()

    for raw in str(value).splitlines():
        line = raw.strip()
        if line.startswith("- "):
            bullets.append(line[2:])
            continue
        flush()
        if not line:
            continue
        if line.endswith(":") and len(line) < 40:
            out.append(format_html('<p class="guidehead">{}</p>', line))
        else:
            out.append(f'<p class="instructions secintro">{stack(line)}</p>')
    flush()
    return mark_safe("".join(out))


STATUS_LABELS = {
    "not_started": "Not started",
    "in_progress": "In progress",
    "submitted": "Submitted",
    "completed_opt_out": "Opted out",
    "exempt": "Exempt",
}
RESPONDENT_LABELS = {
    "not_started": "To do",
    "in_progress": "In progress",
    "submitted": "Done",
    "completed_opt_out": "Done",
    "exempt": "Not needed",
}


@register.simple_tag
def status_chip(status, respondent=False):
    labels = RESPONDENT_LABELS if respondent else STATUS_LABELS
    return format_html('<span class="chip st-{}">{}</span>', status, labels.get(status, status))


@register.filter
def pct(part, whole):
    try:
        return round(100 * float(part) / float(whole)) if float(whole) else 0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.simple_tag(takes_context=True)
def nav_current(context, *names):
    match = getattr(context.get("request"), "resolver_match", None)
    return 'aria-current="page"' if match and match.url_name in names else ""


@register.filter(is_safe=True)
def caption(value):
    """Short section directions shown under a heading: in parentheses, no trailing colon."""
    text = str(value or "").strip().rstrip(":").strip()
    return mark_safe(f"({stack(text)})") if text else ""


@register.filter
def lastword(value):
    """'Y10 Jan' -> 'Jan' (period column headings under their grant year)."""
    parts = str(value or "").split()
    return parts[-1] if parts else ""


@register.filter
def heatvar(style):
    """Heat shade as --h so the n column can show it when % is hidden."""
    from apps.analytics.report import heat_var

    return heat_var(style or "")


@register.filter
def cut_end_period(text):
    """Drop one trailing period so a quoted item doesn't end in .”."""
    text = str(text or "")
    return text[:-1] if text.endswith(".") else text
