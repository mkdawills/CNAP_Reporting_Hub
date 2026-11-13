# CNAP Member Hub homepage

Built 2026-11-13 from the approved homepage prototype (`design/prototypes/member-hub/index.html`,
published at https://claude.ai/artifact/Ah87xCNMNFoRMTfjZox8QZ). MW approved building it into the app on
the `feature/cnap-ui-redesign` branch. Nothing here is on `main`.

## How it switches on

The homepage is one more screen in the redesign switch (`apps/common/prototype.py`, key `hub`).

- `UI_PROTOTYPE` off (production today): `/` behaves exactly as before. Respondents go to My work,
  administrators to their home.
- `UI_PROTOTYPE` on: `/` shows the homepage to everyone with a person record. The Codespaces test copy
  has it on.
- With `UI_PROTOTYPE_ONLY=false`, a reviewer who picks "Current" on the before/after switch gets the
  old redirect.

The view is `apps.portal.views.home`. The data comes from `apps/portal/hub.py`. The template is
`templates/hub/home.html`, with its own stylesheet and script in `static/hub/`. It doesn't use the
sidebar layout, but it shares the page-feedback button (`templates/_feedback.html`).

## What is real and what is sample content

The homepage reads records and never writes them. No migrations were added.

| Section | Source |
| --- | --- |
| Greeting, date, grant year | The signed-in person, local time, the latest non-draft reporting session |
| Reporting reminder, Your week | The person's assignments in the open session, through `presenters.task_list` (the same numbers as My work). Funding card: the person's own open funding matches. NeuroSync card: the next talk within a week. |
| Center reporting card (administrators only) | The open session's assignments, counted as on the administrator home (exempt assignments left out) |
| Your week roles | The person's current relationships, in plain words, plus who mentors the project they lead |
| Funding: Picked for you | `funding.picked_for(person)`: only the person's own matches |
| Funding news | `funding.news(limit=3)`: the same news every member sees on the funding page |
| Calendar | NeuroSync talks, the open session's due date, deadlines of the person's matches and of opportunities for everyone, and funding events, for the academic year (August to July) |
| NeuroSync | The NeuroSync schedule (`SpeakerTalk`): the next talk and the five after it |
| Research cores, CONNECT Lab, Getting started | Fixed text from MW's core descriptions, the CONNECT flyer, and her onboarding steps. Links go to the cores' pages on the CNAP website. |
| Research at CNAP | **Sample content**, marked on the page |
| Proposal writing toolkit links | **Sample content**, marked on the page |
| Community: stats, web, spotlight, profiles, achievements, conversation threads, listserv | **Sample content**, marked on the page |
| 2026 Site Visit photographs | **Sample content** (placeholders), marked on the page |

## Backend each sample section needs (not built, each needs MW's approval)

1. **Research stories**: a story model (title, kind, summary, image, author, date, link), with an
   administrator screen to post them.
2. **Proposal writing toolkit**: a resource list by stage. The existing `HelpfulDocument` could carry a
   stage field.
3. **Community profiles and "share your interest"**: a member directory with research interests. This
   is a **permissions decision**, because members don't see each other's names and roles today.
4. **Achievements**: a feed of confirmed publications, awards, and talks. This also needs a decision
   about which outcome records members may see.
5. **Conversation threads**: posts, replies, and moderation (the funding-follow-up spec, phase 2).
6. **Listserv**: forwarding the Outlook group's emails into the Hub, with an approval queue.
7. **Photographs**: an upload and gallery screen.
8. **Core requests, consultations, vouchers, schedule of charges**: request forms per core.
9. **My meetings and K-State dates on the calendar**: a calendar feed (Outlook) and the academic
   calendar. Neither is connected.
10. **Speaker portraits, keywords, and talk start times**: `SpeakerTalk` records only when a talk ends.
    A talk that ends at 3:30 p.m. shows the series time (2:30 to 3:30, from MW). Any other talk shows
    only its end time.

## For MW to confirm

- The NeuroSync talk titles and speaker names are now on every member's homepage. Before, only the
  administrator screen listed the schedule. They are public seminars, so this should be fine, but it
  is a change in who sees the schedule.
- The "Talk through a draft" button opens an email to the evaluator address (`EVALUATOR_EMAIL`) until
  booking exists. It should probably go to the Assistant Director for Grants and Contracts.
