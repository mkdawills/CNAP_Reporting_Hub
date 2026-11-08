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


# "[[term|what it means]]" in directions becomes a hover term (MW 2026-11-04): a dotted underline and a
# small "i", with the meaning in a tooltip that also opens on keyboard focus or tap.
_TERM = re.compile(r"\[\[([^|\]]+)\|([^\]]+)\]\]")


def _hold_terms(text):
    held = []

    def keep(m):
        held.append(
            f'<span class="term" tabindex="0" title="{m.group(2)}" data-tip="{m.group(2)}">{m.group(1)}'
            '<span class="term-i" aria-hidden="true">i</span></span>'
        )
        return f"\x01{len(held) - 1}\x01"

    return _TERM.sub(keep, text), held


def _put_terms(text, held):
    return re.sub("\x01(\\d+)\x01", lambda m: held[int(m.group(1))], text)


_FIELD_GROUPS = {
    "Progress": ("status", "resubmission_of", "substatus"),
    "The funder": ("funding_source_type", "funding_source", "federal_agency", "federal_agency_other", "funding_agency", "opportunity_url", "mechanism"),
    "Dates": ("anticipated_submission_date", "anticipated_day", "submission_date", "anticipated_submission_month",
              "anticipated_publication_date", "publication_date", "award_notice_date", "project_start_date",
              "project_end_date", "decision_date", "decline_date", "presented_on"),
    "The proposal": ("project_title", "pi", "role", "role_other", "cayuse_ipf", "grant_number", "prime_or_subaward"),
    "Budget": ("anticipated_total", "planned_estimated_direct", "requested_total", "requested_direct", "requested_indirect",
               "award_total", "award_direct", "award_indirect", "cnap_portion"),
    "Credit to CNAP": ("resources", "resources_other_text", "projects"),
    "Acknowledging CNAP": ("cnap_cited_tri", "cnap_index_tri", "ack_tri", "cnap_cited", "cnap_acknowledged", "cnap_credited_in_publications", "cnap_in_grant_index"),
    "Foreign components": ("has_foreign_authors", "foreign_component_approved", "has_non_idea_coauthors", "has_foreign_component"),
    "Outcome and next steps": ("decision_comments", "discussed_with_program_officer", "program_officer_name", "discussion_date",
                      "feedback_shared_with_cnap", "plans_to_resubmit", "comments", "resubmission_intent"),
}
_ITEM_FIELDS = ("title", "journal", "pubmed_url", "author_display_text", "publication_type", "publication_type_other",
                "presentation_type", "presentation_type_other",
                "event", "venue", "city", "state_region", "country")


_OTHER_OF = {"publication_type_other": "publication_type", "presentation_type_other": "presentation_type",
             "role_other": "role"}


@register.filter
def other_of(name):
    """The choice a "Please describe" box belongs to; the box shows only when that choice is Other."""
    return _OTHER_OF.get(name, "")


@register.filter
def field_group(name, kind):
    """The small heading a form field sits under, so long forms read in chunks (MW 2026-11-04)."""
    if name in _ITEM_FIELDS:
        return "The presentation" if kind in ("talk", "presentation", "talks") else "The paper"
    if kind == "grant" and name in ("decision_comments",):
        return "Outcome and next steps"
    for title, names in _FIELD_GROUPS.items():
        if name in names:
            return title
    return ""


@register.filter
def at(seq, i):
    """seq[i], or "" when out of range (prototype charts pair item cells with scale colors)."""
    try:
        return seq[int(i)]
    except (IndexError, TypeError, ValueError, KeyError):
        return ""


@register.filter
def sum_key(rows, key):
    """Add up one number across a list of dicts, e.g. opt-outs across the per-form rows already shown."""
    return sum(int((r.get(key) if isinstance(r, dict) else getattr(r, key, 0)) or 0) for r in rows or [])


@register.filter
def days_until(when):
    """Whole days from today until a date or datetime (negative once past)."""
    from django.utils import timezone

    if not when:
        return ""
    d = timezone.localtime(when).date() if hasattr(when, "hour") else when
    return (d - timezone.localdate()).days


@register.filter
def minus(a, b):
    try:
        return int(a) - int(b)
    except (TypeError, ValueError):
        return a


@register.filter
def pct(n, total):
    """n as a whole-number percent of total (0 when total is 0)."""
    try:
        return round(100 * int(n) / int(total)) if int(total) else 0
    except (TypeError, ValueError):
        return 0


@register.filter
def status_count(rows, status):
    """How many task rows have this assignment status (prototype: submitted vs opted out)."""
    return sum(1 for r in rows or [] if getattr(r.get("a") if isinstance(r, dict) else None, "status", None) == status)


@register.filter
def part_no(code, display):
    """1-based position of a section in a form's document outline (display["doc_outline"]), or 0 (MW 2026-11-04)."""
    parts = (display or {}).get("doc_outline") if isinstance(display, dict) else None
    try:
        return list(parts or []).index(code) + 1
    except ValueError:
        return 0


@register.filter
def short_note(value):
    """A one-line direction under a section header shows as a quiet note (MW 2026-11-04)."""
    v = str(value or "")
    return bool(v) and "\n" not in v and "[[" not in v and len(v) <= 120


@register.filter(is_safe=True)
def stack(value):
    """Directions with several sentences: one sentence per line (decisions.md)."""
    if value is None:
        return ""
    text, held = _hold_terms(str(conditional_escape(str(value))))
    return mark_safe(_put_terms(_SPLIT.sub(r"\1<br>", text), held))


@register.filter(is_safe=True)
def reveal(value):
    """Like stack, but each sentence is its own line that fades in once, one after another (MW 2026-10-28)."""
    if value is None:
        return ""
    text, held = _hold_terms(str(conditional_escape(str(value))))
    parts = _SPLIT.sub("\\1\x00", text).split("\x00")
    return mark_safe(
        "".join(
            f'<span class="rl" style="--i:{i}">{_put_terms(p, held)}</span>' for i, p in enumerate(parts) if p.strip()
        )
    )


# Links for more information under a key-point card, by the card's label (MW 2026-11-05).
# Kept here, so the form definitions and their versions stay unchanged.
CARD_LINKS = {
    "Your core's RRID": [
        ("What a Research Resource Identifier (RRID) is", "https://www.rrids.org/"),
        ("Look up your core's RRID at SciCrunch", "https://scicrunch.org/resources"),
    ],
}


@register.filter(is_safe=True)
def guidance(value):
    """
    Section instructions: blank lines separate paragraphs; lines starting with
    "- " become a bulleted list; a line ending with ":" before a list is a
    small heading. Each paragraph's sentences are stacked.
    """
    if not value:
        return ""
    import re

    # No "Please" in directions (MW 2026-11-07); the questions themselves are not touched here.
    value = re.sub(r"\bPlease (\w)", lambda m: m.group(1).upper(), str(value))
    out, bullets, cards = [], [], []
    state = {"ordered": False}

    def flush():
        if bullets:
            items = "".join(format_html("<li>{}</li>", b) for b in bullets)
            # Steps are numbered (MW 2026-11-08): a list introduced by a line about steps is an ordered list.
            tag = "ol" if state["ordered"] else "ul"
            out.append(f'<{tag} class="guide{" steps" if tag == "ol" else ""}">{items}</{tag}>')
            bullets.clear()
        state["ordered"] = False
        if cards:
            out.append('<div class="gcards">' + "".join(cards) + "</div>")
            cards.clear()

    for raw in str(value).splitlines():
        line = raw.strip()
        # "> Label: body" is a key point, shown as its own small card so busy readers spot it (MW 2026-11-04).
        if line.startswith("> ") and ":" in line:
            label, body = line[2:].split(":", 1)
            if bullets:
                items = "".join(format_html("<li>{}</li>", b) for b in bullets)
                out.append(f'<ul class="guide">{items}</ul>')
                bullets.clear()
            more = "".join(
                format_html('<li><a href="{}" target="_blank" rel="noopener">{} (opens in a new tab)</a></li>', u, t)
                for t, u in CARD_LINKS.get(label.strip().replace("’", "'"), [])
            )
            more = f'<ul class="gcard-links">{more}</ul>' if more else ""
            cards.append(format_html('<div class="gcard"><p class="gcard-h">{}</p><p>{}</p>{}</div>', label.strip(), stack(body.strip()), mark_safe(more)))
            continue
        if line.startswith("- "):
            bullets.append(line[2:])
            continue
        flush()
        if not line:
            continue
        if line.endswith(":") and re.search(r"\bsteps?\b", line, re.I):
            state["ordered"] = True
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


def coverage(p):
    """What a reporting session's answers cover (MW 2026-11-08): everything since the previous reporting session closed,
    through this session's end date. The boundary moves each year (the RPPR session may close around February 20), so it
    comes from the sessions themselves: the day after the previous session closed (or its planned close, or its due date,
    while it is still open). The first session uses its own start date. Worked out each time; nothing is stored.
    Returns (start, end, previous_close) with previous_close None for the first session."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.reporting.models import ReportingPeriod

    prev = (
        ReportingPeriod.objects.filter(display_order__lt=p.display_order).order_by("-display_order").first()
        if getattr(p, "display_order", None) is not None
        else None
    )
    if prev is None:
        return p.start_date, p.end_date, None
    mark = prev.closed_at or prev.closes_at or prev.due_at
    closed = timezone.localtime(mark).date() if mark else None
    if not closed or closed >= p.end_date:
        return p.start_date, p.end_date, None
    return closed + timedelta(days=1), p.end_date, closed


def period_span(p):
    """'June 1 to November 30, 2026' for a reporting session (year shown once when both dates share it).
    The start is the day after the previous session closed (see coverage)."""
    s, e, _ = coverage(p)
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
    """The three statements NIH requires on public documents (Stevens Amendment, MW 2026-11-03): grant
    support, the funding level, and the disclaimer. The funding level is the author's own CNAP project: only
    they know its award total, and CNAP projects are normally paid entirely with federal money."""
    support = (
        f"Research reported in this {kind} was supported by the National Institute of General Medical "
        f"Sciences of the National Institutes of Health under award number P20GM113109."
    )
    level = (
        "100% of the total costs of this project ($[your project’s total award]) were financed with federal "
        "money, and 0% ($0) were financed by nongovernmental sources."
    )
    disclaimer = (
        "The content is solely the responsibility of the authors and does not necessarily represent the "
        "official views of the National Institutes of Health."
    )
    return {"support": support, "level": level, "disclaimer": disclaimer, "all": f"{support} {level} {disclaimer}"}


@register.simple_tag
def why(text):
    """A small "?" next to a heading. Hovering or focusing it explains why the feature exists and
    where its data goes downstream (MW 2026-11-03: the site should teach a brand-new evaluator)."""
    from django.utils.html import format_html

    return format_html(
        '<span class="whyq" tabindex="0" role="note" aria-label="{}">?<span class="whyb">{}</span></span>',
        text,
        text,
    )


@register.simple_tag
def info(text):
    """A small "i" beside a label (MW 2026-11-08): hovering, focusing, or tapping it shows clear directions.
    Same bubble as the "?" on headings; "i" marks practical directions rather than why a feature exists."""
    from django.utils.html import format_html

    return format_html(
        '<span class="whyq whyi" tabindex="0" role="note" aria-label="{}">i<span class="whyb">{}</span></span>',
        text,
        text,
    )


@register.filter
def usd(value):
    """Dollar amounts with thousands separators: 1250000 -> $1,250,000 (MW 2026-11-03)."""
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return value


# Section titles written in the respondent's voice ("My mentor or mentors") read wrongly on an
# administrator's results page. Titles state the subject as a fact, with no pronouns (MW 2026-11-05).
# Display only: the survey itself keeps its wording.
_ADMIN_SECTION_NAMES = {
    "My Mentor or Mentors Survey": "Mentee Survey",
    "My Mentor or Mentors Over Time": "Mentee Survey Over Time",
}


@register.filter
def admin_section_name(value):
    return _ADMIN_SECTION_NAMES.get(str(value or ""), value)


# One sentence under each form's title that says why the form is asked (MW 2026-11-05).
# Kept in the prototype layer, so the form definitions and their versions stay unchanged.
# Nouns, not pronouns, so each sentence stands on its own.
FORM_PURPOSE = {
    "bn_core_survey": "This survey asks how well the Behavioral Neuroscience Core's facilities and services worked for you, and how often you used the Behavioral Neuroscience Core.",
    "cn_core_survey": "This survey asks how well the Cognitive Neuroscience Core's spaces, equipment, and support worked for you, and how often you used the Cognitive Neuroscience Core.",
    "ni_core_survey": "This survey asks how well the Neuroinformatics Core's resources supported your research, and how often you used the Neuroinformatics Core.",
    "core_usage_report": "This report shows the National Institutes of Health who used your core and what came of that use.",
    "mentee_survey": "This survey asks how available, helpful, and supportive your mentor or mentors have been on your CNAP project.",
    "mentor_questionnaire": "This questionnaire asks about your role as a CNAP mentor, considering all of your mentees together.",
    "neurosync_speaker_survey": "This survey asks NeuroSync speakers how the NeuroSync visit went.",
    "neurosync_survey": "Your ratings help the Center choose NeuroSync speakers and topics, and decide how the series is run.",
    "nih_documents": "Each year, the Center reviews Current and Pending (Other) Support, and any foreign activity documents, for Core Directors, Research Project Leaders, Pilot Project Leaders, and the Program Director/Principal Investigator.",
    "pilot_mentor_report": "This report records your meetings with your Pilot Grantee/Mentee. It also records your view of the Pilot Grantee/Mentee's progress toward the pilot program milestones.",
    "primary_mentor_report": "This report records your meetings with your Research Project Leader. It also records your view of the Research Project Leader's progress toward the project milestones.",
    "progress_core": "Your semiannual progress report summarizes your core's accomplishments, plans, and changes.",
    "progress_pilot": "Your semiannual progress report summarizes your pilot project's accomplishments, plans, and changes, including plans for grant submissions.",
    "progress_research": "Your semiannual progress report summarizes your research project's accomplishments, plans, and changes.",
    "ts_admin_core": "This survey asks how well the Administrative Core is serving you.",
    "ts_grant_writing": "This survey asks whether the Grant Writing Program is helping you write and submit grants.",
    "ts_reporting_hub": "This survey asks how well the CNAP Reporting Hub works for completing your Center surveys and reports.",
    "ts_synergy": "This survey asks how well CNAP members work together across disciplines, and whether CNAP has helped your research.",
}


@register.filter
def form_purpose(code):
    return FORM_PURPOSE.get(str(code or ""), "")


@register.filter
def soft_lower(value):
    """Lower-case a label for use mid-sentence, keeping abbreviations: "Papers citing a core RRID" -> "papers citing a core RRID"."""
    return " ".join(w if (w.isupper() and len(w) > 1) else w.lower() for w in str(value).split(" "))


@register.filter
def duration(minutes):
    """"About 45 minutes", "About 1 hour", "About 1 hour 15 minutes" (MW 2026-11-07)."""
    try:
        m = int(minutes)
    except (TypeError, ValueError):
        return ""
    m = -(-m // 5) * 5  # rounded up to the nearest 5 minutes, like every estimate
    h, r = divmod(m, 60)
    if not h:
        return f"about {m} minute{'s' if m != 1 else ''}"
    out = f"about {h} hour{'s' if h != 1 else ''}"
    if r:
        out += f" {r} minute{'s' if r != 1 else ''}"
    return out
