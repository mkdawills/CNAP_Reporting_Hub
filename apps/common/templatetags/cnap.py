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
def reveal(value):
    """Like stack, but each sentence is its own line that fades in once, one after another (MW 2026-10-28)."""
    if value is None:
        return ""
    text = str(conditional_escape(str(value)))
    parts = _SPLIT.sub("\\1\x00", text).split("\x00")
    return mark_safe(
        "".join(
            f'<span class="rl" style="--i:{i}">{p}</span>' for i, p in enumerate(parts) if p.strip()
        )
    )


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
        if line.endswith(":") and len(line) < 60:
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
    # mark_safe: simple_tag output is escaped, which turned the quotes into &quot; and broke the highlight
    return mark_safe('aria-current="page"') if match and match.url_name in names else ""


@register.filter(is_safe=True)
def caption(value):
    """Short section directions shown under a heading, as plain sentences (MW 2026-11-02: no parentheses)."""
    text = str(value or "").strip().rstrip(":").strip()
    return stack(text) if text else ""


@register.filter
def lastword(value):
    """'Y10 Fall' -> 'Fall' (period column headings under their grant year)."""
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


_ICONS = {
    # simple 24px line icons, drawn for this site (MW 2026-10-28: one per My tasks group)
    "cores": '<path d="M9 3.5l3.2 1.6-3.6 7.2-3.2-1.6z"/><path d="M10.6 4.3l1-2"/><path d="M8.2 12.4l-.8 1.6"/><path d="M5 20h13"/><path d="M14.5 20a6.5 6.5 0 0 0 1.4-10.3"/><path d="M6 16.5h6.5"/>',
    "grant": '<path d="M12 21v-9"/><path d="M12 12c0-4 3-6 7-6 0 4-3 6-7 6z"/><path d="M12 15c0-3-2.5-5-6-5 0 3 2.5 5 6 5z"/>',
    "mycore": '<path d="M4 9l8-5 8 5"/><path d="M6 10v8M10 10v8M14 10v8M18 10v8"/><path d="M4 20h16"/>',
    "mentoring": '<circle cx="9" cy="8" r="3"/><circle cx="17" cy="10" r="2.3"/><path d="M3.5 19c.5-3.5 3-5 5.5-5s5 1.5 5.5 5"/><path d="M14.5 15.5c.8-.6 1.7-.9 2.5-.9 2 0 3.6 1.3 4 4"/>',
    "admin": '<rect x="5" y="4.5" width="14" height="16" rx="2"/><path d="M9 4.5h6v2.5H9z"/><path d="M8.5 11h7M8.5 14.5h7M8.5 18h4"/>',
    "other": '<rect x="4" y="5.5" width="16" height="14" rx="2"/><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4"/><circle cx="12" cy="14.5" r="1.4"/>',
    "hub": '<path d="M5 5h14a1.5 1.5 0 0 1 1.5 1.5v8A1.5 1.5 0 0 1 19 16h-8l-4.5 3.5V16H5a1.5 1.5 0 0 1-1.5-1.5v-8A1.5 1.5 0 0 1 5 5z"/><path d="M8 9.5h8M8 12.5h5"/>',
    "nih": '<path d="M6.5 3.5h8l4 4v13h-12z"/><path d="M14.5 3.5v4h4"/><path d="M9 12h6M9 15h6M9 18h4"/>',
    "outcomes": '<path d="M5 4.5h10a3 3 0 0 1 3 3v12H8a3 3 0 0 1-3-3z"/><path d="M5 16.5a3 3 0 0 1 3-3h10"/>',
}


@register.simple_tag
def group_icon(code):
    """An inline line icon for a My tasks group (decorative: hidden from screen readers)."""
    body = _ICONS.get(code, _ICONS["other"])
    return mark_safe(
        '<svg class="gicon" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" '
        f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{body}</svg>'
    )


@register.simple_tag
def core_rrids():
    """Cores with an RRID, for the "how to credit CNAP" boxes (MW 2026-10-28)."""
    from apps.people.models import Core

    return list(Core.objects.filter(is_active=True, archived_at__isnull=True).exclude(rrid=""))


@register.filter(is_safe=True)
def title_break(value):
    """Form titles on two lines (MW 2026-11-02): after a colon, or before "User Survey"."""
    text = str(conditional_escape(value or ""))
    if ": " in text:  # "NIH Documents: Biosketch, …": what follows the colon goes on the second line
        head, tail = text.split(": ", 1)
        return mark_safe(f"{head}:<br>{tail}")
    for tail in (" Facility User Survey", " User Survey"):
        if text.endswith(tail):
            return mark_safe(text[: -len(tail)] + "<br>" + tail.strip())
    return mark_safe(text)


def _lead_split(value):
    lines = str(value or "").splitlines()
    first = lines[0].strip() if lines else ""
    if first.endswith(":") and not first.startswith("- ") and len(lines) > 1:
        return first, "\n".join(lines[1:])
    return "", str(value or "")


@register.filter
def lead(value):
    """A section's opening line that ends with ":" introduces the section, so it sits just above the section's
    line (MW 2026-11-02: "Your document should contain the following:")."""
    return _lead_split(value)[0]


@register.filter
def after_lead(value):
    return _lead_split(value)[1]


def period_span(p):
    """'June 1 to November 30, 2026' for a reporting period (year shown once when both dates share it)."""
    s, e = p.start_date, p.end_date
    first = f"{s:%B} {s.day}" + ("" if s.year == e.year else f", {s.year}")
    return f"{first} to {e:%B} {e.day}, {e.year}"


@register.filter
def with_period(value, period):
    """Put the dates after "during the reporting period" in directions (MW 2026-11-02)."""
    if not value or period is None:
        return value
    return str(value).replace(
        "during the reporting period", f"during the reporting period ({period_span(period)})", 1
    )


@register.filter
def span(period):
    return period_span(period) if period else ""


@register.simple_tag
def nih_ack(kind="publication"):
    """The three statements NIH requires on public documents (Stevens Amendment, MW 2026-11-02): grant
    support, the federal and nongovernmental shares of total costs, and the disclaimer."""
    from apps.outcomes.models import FundingStatement

    f = FundingStatement.current()
    support = (
        f"Research reported in this {kind} was supported by the National Institute of General Medical "
        f"Sciences of the National Institutes of Health under award number {f.award_number}."
    )
    if f.ready:
        pf, fed, pn, non = f.shares()
        level = (
            f"Federal funds paid for {pf}% (${fed:,.0f}) of the project’s total costs, and nongovernmental "
            f"sources paid for {pn}% (${non:,.0f})."
        )
    else:
        level = "[Funding level: the CNAP office will add the federal and nongovernmental shares here.]"
    disclaimer = (
        "The content is solely the responsibility of the authors and does not necessarily represent the "
        "official views of the National Institutes of Health."
    )
    return {"support": support, "level": level, "disclaimer": disclaimer, "ready": f.ready,
            "all": f"{support} {level} {disclaimer}"}
