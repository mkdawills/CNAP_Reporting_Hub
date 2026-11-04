/* Column-header explainers (MW 2026-11-04): every table header says, on hover, what its column
   holds and why it matters. One glossary for the whole site, so no table is missed. A header
   that already has its own title keeps it. Where a word means different things in different
   tables ("Status", "Type"), the table's own purpose picks the right meaning. */
(function () {
  function gy(n) {
    n = parseInt(n, 10);
    return "Grant year " + n + ": June 1, " + (2016 + n) + " to May 31, " + (2017 + n) + ".";
  }

  var G = {
    "#": "This row’s number, so you can point to it in a conversation or an email.",
    "Item": "The survey question, numbered as it appears on the form.",
    "n": "How many people chose this answer.",
    "%": "The share of all answers to this item that chose this option.",
    "Mean": "The average rating on this item.",
    "Mean (SD)": "The average rating, with the standard deviation in parentheses.",
    "SD": "Standard deviation: how spread out the answers were. A bigger number means people disagreed more.",
    "Average": "The average rating.",
    "Total": "The total for this row.",
    "Sum": "The total.",
    "Count": "How many.",

    "Publication title": "The paper’s title, as entered or filled in from PubMed. Click it to open and edit the record.",
    "Publication": "The paper’s title.",
    "Journal": "The journal the paper appeared in, or the one it is aimed at while it is planned.",

    "CNAP authors": "The CNAP members among this paper’s authors. The full author list lives on the paper’s record.",
    "CNAP investigators": "The CNAP members on this proposal, with their role, such as PI.",
    "RPLs Credited": "The Research Project Leaders (RPLs) whose CNAP research project this is credited to. These credits feed the by-project counts and the RPPR.",
    "PPLs Credited": "The Pilot Project Leaders (PPLs) whose CNAP pilot project this is credited to. These credits feed the by-project counts and the RPPR.",
    "Cores Credited": "The CNAP cores this used. Each credit counts toward that core in the Counts tab, the dashboards, and the site-visit tables.",
    "Projects Credited": "The CNAP project this row’s counts are credited to.",
    "Core RRID cited?": "Whether the paper cited each credited core’s Research Resource Identifier (RRID) in its methods, so the core’s use can be traced even without the grant citation.",
    "Correct it": "Buttons to record, or correct, whether this acknowledges CNAP, without opening the full record.",

    "Proposal title": "The proposal’s title. Click it to open and edit the record.",
    "Proposal": "The proposal’s title.",
    "Planned proposal": "The planned proposal this check-in asks about.",
    "Round": "Which submission this is: A0 is the first submission, A1 the first resubmission, and so on.",
    "Funder": "The funding agency the proposal went to, such as NIH or NSF.",
    "Agency": "The funding agency.",
    "Mechanism": "The funding opportunity’s type code, such as R01, R21, or K99.",
    "Award total": "The total award, direct plus indirect costs, for the whole project period.",
    "Anticipated submission": "When the person expects to submit the proposal.",
    "Requested $": "The total requested in these proposals, direct plus indirect.",
    "Total $": "All the dollars in this row.",
    "Total count": "All the proposals in this row.",
    "Pending": "Proposals submitted and still waiting on a decision.",
    "Their answer": "What they chose in the monthly check-in, and when they answered.",
    "Their comments": "Anything they added in the check-in’s comments box.",
    "NIH": "RPPR Table 1A: proposals and awards from the National Institutes of Health.",
    "Federal, non-NIH": "RPPR Table 1A: proposals and awards from other federal agencies, such as NSF or USDA.",
    "Non-Federal Sources": "RPPR Table 1A: proposals and awards from foundations, industry, and the state.",
    "Funding Sources": "RPPR Table 1A: where the proposals went, by funder type.",

    "Presentation title": "The talk or poster’s title.",
    "Talk": "The talk’s title.",
    "Event": "The meeting or event where it was given.",
    "Date presented": "The date it was given. A talk counts in the grant year (June to May) that contains this date.",
    "Presenters": "Who presented, in the order shown on the talk or poster.",
    "Speaker": "The NeuroSync speaker. Their survey goes to the email address on file when the talk ends.",
    "Ends": "When the talk ends. The speaker’s survey is sent then.",
    "Ended": "When the talk ended.",

    "Person": "The person this row is about. Click a name to open their page.",
    "Name": "The person this row is about.",
    "Email": "The address that forms, reminders, and sign-in links go to.",
    "Role": "This person’s CNAP role, such as Project Leader or Core Director. Roles decide which forms they receive.",
    "Relationship": "The tie between this person and a project or core, which decides the forms they receive.",
    "Leadership": "Leadership roles: Project Leader, Pilot Project Leader, Program Director, or Associate Director.",
    "Mentoring": "Mentoring roles on a project.",
    "Core roles": "Core Director, core staff, or core user roles.",
    "Other roles": "Every other CNAP role.",
    "Leader": "The project’s leader.",
    "Mentors": "The project’s mentors.",
    "Others": "Everyone else on the team.",
    "Directors": "The core’s directors.",
    "Staff": "The core’s staff members.",
    "eRA Commons ID": "The person’s NIH eRA Commons user name, required for everyone listed in RPPR section D.1.",
    "ORCID iD": "The person’s ORCID iD, a permanent researcher identifier NIH asks for on senior and key personnel.",
    "Person months": "Effort expressed in calendar months: share of full-time effort times 12.",
    "Career level": "The person’s career stage, as RPPR section D.1 asks.",
    "Category": "The RPPR participant category.",
    "Need months": "How many people still need their effort months for RPPR D.1.",
    "Need an ID": "How many people still need an eRA Commons ID for RPPR D.1.",
    "Signs in with": "How this person signs in: K-State single sign-on, a password, or an emailed link.",
    "Cal": "Calendar months: effort on a 12-month appointment.",
    "Aca": "Academic months: effort during a 9-month academic appointment.",
    "Biosketch": "The person’s NIH biosketch for this year: turned in or not.",
    "Current and Pending": "The person’s Current and Pending (Other) Support for this year: turned in or not.",
    "MFTRP": "The Malign Foreign Talent Recruitment Program (MFTRP) certification: turned in or not.",
    "Foreign docs": "Supporting documents about foreign activities, if the person has any.",
    "February check": "The person’s answer to February’s question: has your Current and Pending changed since the fall?",
    "D.2.a": "RPPR section D.2.a: whether this person expects their effort to drop by 25% or more.",
    "Breakdown by Role": "How many people hold each role.",

    "Form": "The form. Click its name to read its questions.",
    "Forms": "How many forms.",
    "Survey": "Whether the survey went out, and whether it was answered.",
    "Questions": "How many questions the form has.",
    "Assigned": "How many people received this form.",
    "Done": "How many have finished: submitted or opted out.",
    "Complete": "How many submitted the full form, out of how many received it.",
    "Opted out": "How many chose the opt-out answer. Opting out completes a survey, so it counts as done.",
    "How it was completed": "A full response, or the opt-out answer.",
    "Reasons given": "Why people opted out, in their own words.",
    "Your access": "What you may see in this report: names, no names, or combined results only.",
    "People who receive it": "How many people this launch sends the form to.",
    "The forms they receive": "Every form this launch sends this person.",
    "Takes about": "About how long the form takes to fill in.",
    "About how long it takes": "About how long the form takes to fill in.",
    "Time": "About how long the form took or takes.",
    "Open it": "Open the submitted form to read it.",
    "What people wrote": "Open-ended answers, word for word.",

    "Period": "The reporting period, such as Year 10 Fall.",
    "Covers": "The dates this reporting period covers.",
    "Year": "The grant year (June 1 to May 31).",
    "People": "How many people this applies to.",
    "Actions": "What you can do with this row.",
    "Details": "The specifics, such as the old and new values.",

    "Project": "The research or pilot project.",
    "Project or core": "The project or core this row is about.",
    "Core": "The CNAP core.",
    "RRID": "The core’s Research Resource Identifier (RRID), a permanent public ID. Papers cite it so the core’s use can be traced.",
    "User lab": "The lab that used the core, as the core director reported it.",

    "Who": "Who made the change.",
    "When": "When it happened.",
    "What": "The record that changed.",
    "Action": "What kind of change it was: added, updated, removed, sent, or downloaded.",
    "By": "Who did it.",
    "Uploaded": "When the file was uploaded.",
    "Added": "When it was added.",
    "Since": "When this started.",
    "Sent": "When the email went out.",
    "File": "The uploaded file’s name.",
    "Row": "The row’s number in the uploaded file, so you can find it there.",
    "Decision": "What accepting this row will do in the Hub.",
    "Document": "The document’s title and file.",
    "Excerpt shown to them": "The lines from the document the person sees on their My tasks page.",
    "Notes": "Anything worth knowing about this row.",
    "What to look at": "The record this check flagged. Click it to fix it, or dismiss it if it is right.",
    "What the reminder covers": "The stale papers or proposals this reminder will list.",
    "What it covered": "How many records that reminder listed, and who it went to.",

    "Step": "The two years being compared.",
    "Prior year non-published": "Papers still in the pipeline (planned or submitted) at the end of the earlier year.",
    "Next year published": "Papers published in the following year.",
    "Conversion ratio": "Next-year published divided by prior-year in-pipeline. A rough estimate, since papers are not tracked one by one.",
    "Counted as": "How this item is counted in the tables.",

    "All CNAP": "The whole Center, with each product counted once.",
    "Papers published": "Peer-reviewed papers published in the year or years shown.",
    "Papers citing a core RRID": "Published papers that cited a core’s RRID in their methods.",
    "Presentations": "Talks and posters given in the year or years shown.",
    "Grants submitted": "Proposals submitted in the year or years shown.",
    "Grants awarded": "Proposals awarded, counted in the year of the award notice.",
    "Awarded dollars": "The award totals for those awards.",
    "Kind": "Whether this is a paper, a talk, or a proposal.",
    "Lab": "The lab that used the core, as the core director reported it.",
    "Services used": "Which of the core’s services the lab used this period.",
    "Users": "How many people from that lab used the core, not counting students.",
    "Students": "How many students from that lab used the core. NIH Table 2 counts them separately.",
    "Payment": "How the lab paid for the core: CNAP-supported (in-kind), voucher, or fee for service. Fee-for-service use should not cite the grant.",
    "Data in a grant or paper?": "Whether data from the core went into a grant proposal or a publication this period.",
    "First name": "The team member’s first name.",
    "Last name": "The team member’s last name.",
    "Role on this project or core": "What this person does on the project or core, such as graduate student or technician.",
    "Calendar months": "Effort on a 12-month appointment, in months.",
    "Academic months": "Effort during a 9-month academic appointment, in months.",
    "Summer months": "Effort during the summer, in months.",
    "RPLs": "Research Project Leaders.",
    "PPLs": "Pilot Project Leaders.",
    "SPLs": "Senior project leaders counted as senior or key personnel in D.1.",
    "Core Staff": "Core staff members.",
    "Dates and amounts": "When the proposal went in and the award was made, with the dollars involved.",
    "Under Review": "Papers submitted and under review at a journal.",
    "Accepted": "Papers accepted by the journal, not yet published.",
    "Awaiting Publication": "Papers accepted and in press.",
    "Not Published": "Papers the journal declined.",
    "Poster or Flyer": "Posters and flyers presented.",
    "Conference Presentation": "Talks given at a conference.",
    "Invited Talk": "Talks given by invitation, such as a departmental seminar.",
    "Other": "Anything that fits none of the other columns."
  };

  // Words whose meaning depends on the table they sit in.
  var BY_CONTEXT = {
    "Acknowledges CNAP?": {
      grant: "Whether the proposal credits CNAP for its preliminary data or support, citing P20GM113109. Yes, No, or not checked yet. (The Stevens Amendment covers public materials; for proposals this is the Center’s own expectation.)",
      _: "Whether it acknowledges CNAP in accordance with the Stevens Amendment: it must cite CNAP’s NIH grant, P20GM113109, say how much of the project NIH paid for, and include the standard disclaimer. Yes, No, or not checked yet. A No is followed up with the author and flagged before the RPPR."
    },
    "Status": {
      grant: "Where the proposal stands: Planned, Submitted / pending, Awarded, or Not funded.",
      pub: "Where the paper stands: Planned, Submitted (under review, accepted, or in press), Published, or Declined.",
      form: "Where this form stands: Not started, In progress, Complete, Opted out, or Exempt.",
      roster: "Whether this upload has been reviewed and applied.",
      period: "Where the reporting period is in its steps, from review before launch to finalized.",
      _: "Where this item stands right now."
    },
    "Type": {
      talk: "Conference presentation, invited talk, or poster or flyer.",
      pub: "Journal article, or conference paper or proceedings.",
      project: "Research project or pilot project.",
      form: "What kind of form this is: a survey or a report.",
      _: "The kind of item."
    },
    "Submitted": {
      pub: "Papers submitted to a journal and waiting on a decision, this year.",
      status: "Papers submitted to a journal and waiting on a decision, this year.",
      grant: "The date the proposal was submitted. RPPR Table 1 counts it in the grant year that contains this date.",
      form: "When the form was submitted.",
      _: "When it was submitted."
    },
    "Published": {
      pub: "The publication date. NIH counts a paper in the grant year (June to May) that contains this date.",
      status: "Papers published this year.",
      _: "The publication date."
    },
    "Title": {
      grant: "The proposal’s title.",
      pub: "The paper’s title.",
      talk: "The talk’s title.",
      _: "The item’s title."
    }
  };

  var PATTERNS = [
    [/^Y(\d+)$/, function (m) { return gy(m[1]); }],
    [/^Year (\d+)$/, function (m) { return gy(m[1]); }],
    [/^Effort in Year (\d+)$/, function (m) { return "Calendar months this person worked on CNAP in " + gy(m[1]).replace(/^G/, "g").replace(/\.$/, "") + ". RPPR section D.1 lists anyone with 1.0 or more."; }],
    [/^(.+) count$/, function (m) { return "How many proposals were " + m[1].toLowerCase() + "."; }],
    [/^(.+) total \$$/, function (m) { return "The dollars for proposals that were " + m[1].toLowerCase() + ": award totals for awards, requested totals otherwise."; }],
    [/^\((\d)\)\s*(.+)$/, function (m) { return "Answer " + m[1] + " on the scale: “" + m[2] + ".” The n and % below show how many chose it."; }],
    [/^(Fall|Spring)$/, function (m) { return "The " + m[1] + " reporting session of that grant year."; }],
    [/^(\d{4})\u2013(\d{4})$/, function (m) { return "The academic year from fall " + m[1] + " to spring " + m[2] + ", with its two reporting sessions below it."; }],
    [/^(.+ Core) counts$/, function (m) { return "How many proposals credited to the " + m[1] + " were awarded, pending, or declined, by grant year."; }],
    [/^(.+ Core) dollars$/, function (m) { return "The dollars for proposals credited to the " + m[1] + ", by grant year: award totals for awards, requested totals otherwise."; }],
    [/^(.+ Core)$/, function (m) { return "The " + m[1] + "’s numbers, one row per measure, with each grant year across the top."; }]
  ];

  function context(table) {
    var t = ((table.getAttribute("title") || "") + " " + (table.className || "")).toLowerCase();
    var heads = Array.from(table.querySelectorAll("thead th")).map(function (h) { return h.textContent; }).join(" ").toLowerCase();
    if (/proposal|grant|award|funder/.test(t) || /proposal title|funder|mechanism/.test(heads)) return "grant";
    if (/by type and status/.test(t)) return /\bsubmitted\b/.test(heads) && /under review/.test(heads) ? "status" : "pub";
    if (/paper|publication|journal/.test(t) || /publication title|journal/.test(heads)) return "pub";
    if (/talk|presentation|poster/.test(t) || /presentation title|presenters/.test(heads)) return "talk";
    if (/roster|upload/.test(t) || /uploaded/.test(heads)) return "roster";
    if (/reporting period/.test(t) || /covers/.test(heads)) return "period";
    if (/project/.test(t) && /leader/.test(heads)) return "project";
    if (/form|assignment|survey/.test(t) || /\bform\b/.test(heads)) return "form";
    return "_";
  }

  function clean(s) {
    return s.replace(/[↕↑↓▴▾▸]/g, "").replace(/\s+/g, " ").trim();
  }

  function describe(th) {
    var label = clean(th.textContent);
    if (!label) return "";
    var table = th.closest("table");
    if (label === "Sum" && table && /\bCal\b/.test(table.querySelector("thead").textContent)) {
      return "Summer months: effort during the summer, on top of a 9-month appointment.";
    }
    if (BY_CONTEXT[label]) {
      var c = context(table);
      return BY_CONTEXT[label][c] || BY_CONTEXT[label]._;
    }
    if (G[label]) return G[label];
    for (var i = 0; i < PATTERNS.length; i++) {
      var m = label.match(PATTERNS[i][0]);
      if (m) return PATTERNS[i][1](m);
    }
    return "";
  }

  function run() {
    document.querySelectorAll("table thead th, table tr > th[scope]").forEach(function (th) {
      if (th.hasAttribute("title")) { th.classList.add("hashelp"); return; }
      var d = describe(th);
      if (d) { th.setAttribute("title", d); th.classList.add("hashelp"); }
      else if (clean(th.textContent)) th.setAttribute("data-nohelp", clean(th.textContent));
    });
  }


  // Buttons, button-like links, and fold-ups (MW 2026-11-04): each says what it does, why it is
  // there, and what to expect after the click. Matched by its words; counts in parentheses vary.
  var B = [
    [/^Sign in$/, "Signs you in to the Reporting Hub with your user name and password."],
    [/^Send me a link$/, "Emails you a one-time sign-in link, so no password is needed. It arrives within a minute and works once."],
    [/^Your commitments, from your Statement of Work$/, "Lines from your signed Statement of Work, as a reminder of the milestones you committed to and why CNAP asks for these reports. Click to show or hide them."],
    [/^Done \(\d+\)$/, "The forms you already finished this period. Click to show or hide them; you can still open and edit them while the period is open."],
    [/^Answer$/, "Opens the quick February question about your Current and Pending (Other) Support. It takes about a minute."],
    [/^Start$/, "Opens this form so you can begin. Your answers save as a draft as you go."],
    [/^Continue$/, "Opens this form where you left off. Everything you entered is still there."],
    [/^Preview$/, "Shows the form’s questions before it opens, so you can see what is coming. Nothing is saved."],
    [/^Back to my tasks$/, "Returns to your to-do list. Anything you saved stays saved."],
    [/^Submit$/, "Sends your answers to CNAP. You can still open and edit them while the period is open."],
    [/^Submit opt-out$/, "Records that you are opting out of this survey. That completes it, so it leaves your to-do list."],
    [/^Save draft$/, "Saves your answers without submitting, so you can come back and finish later."],
    [/^Save$/, "Saves your changes to this record."],
    [/^Save new password$/, "Changes your password. You stay signed in."],
    [/^Remove$/, "Removes this entry from the list. Nothing is sent until you save or submit."],
    [/^Add a project$/, "Adds a blank row for another project, so you can list each one separately."],
    [/^Add a meeting$/, "Adds a blank row for another meeting with your mentee."],
    [/^Add a person$/, "Adds a person. On a form, it adds a blank row for another team member; on the People page, it opens the new-person form."],
    [/^Add person$/, "Saves this new person to the Hub. They receive forms once they have a role."],
    [/^Download the Excel template$/, "Downloads a spreadsheet with this list’s columns, so you can fill it in on your own computer. Optional: it is only a tool, if you prefer Excel."],
    [/^Add the rows from my sheet$/, "Reads your filled-in Excel template and adds its rows to the list above, where you can check and edit them before you submit."],
    [/^Add the talks from my sheet$/, "Reads your filled-in semester spreadsheet and adds every talk to the schedule, matching speakers by email address."],
    [/^Edit my answers$/, "Reopens your submitted form so you can change an answer. Please submit again when you are done."],
    [/^Show each entry in full$/, "Opens every entry in this list with all its details."],
    [/^View your most recently submitted Current and Pending/, "Downloads the Current and Pending (Other) Support PDF you last sent CNAP, so you can compare."],
    [/^Nothing has changed$/, "Tells CNAP your Current and Pending is the same as the one on file. That answers the February check."],
    [/^Upload the new PDF$/, "Sends CNAP your updated Current and Pending PDF, certified in SciENcv and not flattened."],
    [/^(Show all tables|Open every item-by-item table)$/, "Opens every item-by-item table on this report at once. The sections stay as they are; use Show all to open those."],
    [/^(Collapse all tables|Close every item-by-item table)$/, "Closes every item-by-item table on this report again."],
    [/^Show the year-by-year means table/, "Opens the table of every item’s average in every period since Year 6, laid out like the site-visit reports."],
    [/^Show item-by-item (table|trends)/, "Opens the detailed table for every item in this section. Click again to close it."],
    [/^See each item$/, "Opens the item-by-item table just below."],
    [/^I need help with eRA Commons/, "Asks the Center evaluator for help with eRA Commons. Choose this if you do not have an account, or are not sure you need one."],
    [/^I need help setting up eRA Commons$/, "Tells the Center evaluator you need an eRA Commons account. They will email you the next steps."],
    [/^I’m not sure I need eRA Commons$/, "Asks the Center evaluator whether your role needs an eRA Commons ID. They will email you the answer."],
    [/^Confirm no changes$/, "Tells CNAP this record is still accurate, so it stops counting as out of date. No details change."],
    [/^Update status$/, "Records what happened next, such as submitted, published, or awarded, and asks only for that stage’s details."],
    [/^Add a publication$/, "Adds a paper, whether it is planned, submitted, or already published."],
    [/^Add a presentation$/, "Adds a talk or poster you have already given."],
    [/^Add a grant proposal$/, "Adds a grant proposal, whether it is planned, submitted, or already decided."],
    [/^Add a proposal$/, "Adds a grant proposal record: planned, submitted and pending, awarded, or not funded."],
    [/^View or edit$/, "Opens this record to read or change its details."],
    [/^Edit$/, "Opens this record to change its details."],
    [/^Edit the planned details$/, "Keeps it planned and lets you update its title, dates, or plans."],
    [/^Send my answer$/, "Records your check-in answer and comments in the Hub. The CNAP team sees it right away."],
    [/^What happens with your reviewer feedback\?$/, "Explains what happens next: CNAP awardees email their reviewer feedback to the Center Director, who offers support and coaching. Click to read more."],
    [/^Fill in from PubMed$/, "Looks up the PubMed or DOI link above and fills in the title, authors, journal, and date. Nothing is saved until you check it and press Save."],
    [/^Open the dashboard$/, "Opens the period dashboard: every person and form in the open period, with counts you can click for names."],
    [/^Live results$/, "Opens this period’s results as answers come in. They are not final until the period is finalized."],
    [/^Review before launch$/, "Opens the launch checklist: who will receive which forms. Nothing is sent until you approve it."],
    [/^See data checks$/, "Opens the automatic checks for gaps that would hurt later reporting."],
    [/^Add a document$/, "Adds a helpful document or link that every respondent sees on their My tasks page."],
    [/^Add a period$/, "Starts a new reporting period: its dates and type. Nothing is sent until you launch it."],
    [/^Add period$/, "Saves this new reporting period. You review and launch it afterward."],
    [/^Close period$/, "Closes the period to new answers, so the results can be generated and reviewed. Respondents can no longer edit."],
    [/^Approve and open /, "Sends this period’s forms to everyone listed on this page. Please check the list first; this cannot be undone."],
    [/^Pause automatic emails$/, "Stops this period’s scheduled emails until you turn them back on. Nothing else changes."],
    [/^Resume automatic emails$/, "Turns this period’s scheduled emails back on."],
    [/^Send \d+ emails?$/, "Sends this email now to the people listed below. People skipped for a reason are not emailed."],
    [/^Who gets it \(\d+\)$/, "The people this email would reach right now, and who would be skipped, with the reason. Click to show or hide the list."],
    [/^What the email says$/, "The full wording of this email, exactly as people receive it. Click to show or hide it."],
    [/^Assign forms from current relationships$/, "Gives this period’s forms to anyone who gained a role since launch. People who already have their forms are not touched."],
    [/^Filter$/, "Narrows the list below to the choices you made."],
    [/^Add the talk$/, "Adds this talk to the schedule. The speaker’s survey goes out automatically when it ends."],
    [/^All forms$/, "Returns to the list of every form."],
    [/^Remove from roster$/, "Takes this person off the CNAP member roster, so they stop receiving the all-member surveys. Their roles are unchanged."],
    [/^Add to roster$/, "Adds this person to the CNAP member roster, so they receive the all-member surveys."],
    [/^Edit details$/, "Opens this person’s name, institution, and IDs to change them."],
    [/^Turn off sign-in$/, "Stops this person from signing in. Their records stay, and you can turn sign-in back on."],
    [/^Turn on sign-in$/, "Lets this person sign in again."],
    [/^End$/, "Ends this relationship as of the date you choose, so the person stops receiving the forms that came with it."],
    [/^Pass to someone else$/, "Ends this role for this person and gives it to someone else on the same date, so nothing falls through."],
    [/^Add relationship$/, "Gives this person a role on a project, a core, or the Center, which decides the forms they receive."],
    [/^Use these$/, "Copies these values from the NIH documents into this person’s record."],
    [/^Use it$/, "Copies this value from the NIH documents into this person’s record."],
    [/^Expand all: effort and eRA Commons IDs$/, "Opens every project’s team list with each person’s eRA Commons ID and effort."],
    [/^Collapse all$/, "Rolls every section up to its title."],
    [/^Details$/, "Opens this row’s team, with each person’s role, IDs, and effort."],
    [/^Hide details$/, "Closes this row’s team list."],
    [/^Add project$/, "Saves this new project. Add its leader and mentors next, so its forms go to the right people."],
    [/^Show effort, eRA Commons IDs, and ORCID iDs$/, "Opens each team member’s identifiers and effort, the same numbers that feed RPPR section D.1."],
    [/^Upload and review$/, "Uploads the roster spreadsheet and shows each row with what accepting it would do. Nothing changes until you accept."],
    [/^Back to /, "Returns to the page you came from."],
    [/^Check the (papers|proposals)$/, "Shows only the ones still waiting for a yes-or-no on the CNAP acknowledgment, so you can work through them."],
    [/^All CNAP$/, "The whole Center’s counts, each product counted once. Click to roll it up or open it."],
    [/^By project$/, "Counts for each project, with each product counted under every project it credits. Click to roll it up or open it."],
    [/^By core and resource$/, "Counts for each core and resource. Click to roll it up or open it."],
    [/^Each core, year by year$/, "One small table per core, with each grant year across the top. Click to roll it up or open it."],
    [/^What was counted \(\d+\)$/, "Every proposal and award behind these Table 1 numbers, so you can check each one. Click to show or hide the list."],
    [/^Update$/, "Redraws this page for the year and date you chose."],
    [/^Papers and proposals this year that say they used this core/, "The papers and proposals that credit this core, for checking against the core’s Table 2 report. Click to show or hide them."],
    [/^Show all \d+ people$/, "Shows everyone on the D.1 list, not just the first few."],
    [/^Mark these as reported in the Year \d+ RPPR$/, "Stamps every item above as reported in this year’s RPPR, so next year’s lists leave them out. Please press it only after the RPPR is submitted."],
    [/^Still (pending|under review) from earlier years/, "Items submitted in an earlier year and still waiting. They are listed separately so nothing is counted in two years. Click to show or hide them."],
    [/^Individual responses \(\d+\)/, "Each person’s submitted answers, one at a time, for reading in full or quoting in the RPPR narrative. Click to show or hide them."],
    [/^Mark (Yes|No)$/, "Records whether this acknowledges CNAP, without opening the full record."],
    [/^Open report$/, "Opens this form’s combined results for the chosen period."],
    [/^Download /, "Downloads this as a file that opens in Excel or your PDF reader."],
    [/^Open the (publications|presentations|grants) dashboard$/, "A live recreation of the evaluator’s product dashboard, with the same graphs and tables, built from the Hub’s records just now."],
    [/^(Flip the graph’s axes|Flip the graph back|Flip the axes( back)?)$/, "Redraws this graph with its groupings swapped, so you can see the same numbers from the other direction."],
    [/^Reopen$/, "Reopens this person’s submitted form so they can change it. Their answers are kept."],
    [/^Exempt$/, "Removes this form from the person’s list for this period without counting it against completion."],
    [/^Dismiss$/, "Hides this flag because it is correct as is. It will not come back for this record."],
    [/^Add$/, "Adds this item. Nothing else changes."],
    [/^How to acknowledge CNAP$/, "The Stevens Amendment wording to put in your paper, talk, or poster, with copy buttons. Click to show or hide it."],
    [/^Save and add another$/, "Saves this one and opens a blank form for the next."],
    [/^It was at K-State$/, "Fills in Kansas State University, Manhattan, Kansas, United States, so you do not have to type it."],
    [/^View or edit the details$/, "Opens this record to read or change its details."],
    [/^(Submitted \/ pending|Submitted|Published|Awarded|Not funded|Declined)$/, "Records that this moved to that stage, and asks only for that stage’s details."],
    [/^(General members|Research Project Leaders|Pilot Project Leaders|Mentors|Core directors|External core users|Mentees|Core staff)/, "This group, how many people are in it, and the forms each will receive. Click to show or hide the people."],
    [/ · (draft|submitted|in progress)/i, "This report’s research team list and answers, for the RPPR narrative sections. Click to show or hide it."],
    [/^Copy$/, "Copies this wording, ready to paste into your paper, talk, or poster."]
  ];
  var CHECKS = /^(People with no email address|Projects with no leader|Projects with no mentor|Forms still open for people who have left the role|Possible duplicate people|Core directors who are also a project leader|Published papers that used a core but didn’t cite its RRID|Papers with foreign co-authors that cite the grant without approval|Past due and not started)/;

  function bdescribe(el) {
    var t = clean(el.textContent);
    if (!t) return "";
    if (CHECKS.test(t)) return "This data check, with how many records it flagged. Click to show or hide them, then fix each one or dismiss it if it is right.";
    if (el.tagName === "SUMMARY" && el.closest(".dashsec")) return "Click the title to roll this section up or open it again.";
    for (var i = 0; i < B.length; i++) if (B[i][0].test(t)) return B[i][1];
    return "";
  }

  function runButtons() {
    document.querySelectorAll("main a.btn, main button, main summary, main .linkbtn, main .tabdl, main .fchipbtn, main .tabs a").forEach(function (el) {
      if (el.title || el.closest("[title]")) return;
      var d = bdescribe(el);
      if (d) el.title = d; else if (clean(el.textContent)) el.setAttribute("data-nohelp", clean(el.textContent).slice(0, 60));
    });
  }


  // Page and section headings (MW 2026-11-04): every heading says what the section is for.
  var FORMS = {
    "Behavioral Neuroscience (BN) Core Facility User Survey": "The BN Core user survey: people who used the Behavioral Neuroscience Core rate its services and how often they use them. The results go to the core director, the External Advisory Committee, and the RPPR.",
    "Neuroinformatics (NI) Core Facility User Survey": "The NI Core user survey: people who used the Neuroinformatics Core rate its services and how often they use them. The results go to the core director, the External Advisory Committee, and the RPPR.",
    "Cognitive Neuroscience (CN) Core User Survey": "The CN Core user survey: people who used the Cognitive Neuroscience Core rate its services and how often they use them. The results go to the core director, the External Advisory Committee, and the RPPR.",
    "Weekly NeuroSync Speaker Series Survey": "The NeuroSync audience survey: members rate the weekly speaker series, so the series keeps improving.",
    "NeuroSync Speaker Survey": "The NeuroSync speaker survey: each speaker rates their experience right after their talk.",
    "Team Synergy Survey": "The Team Synergy Survey: members rate how well CNAP works as a team, a Team Science measure reported to the External Advisory Committee.",
    "Administrative Core Survey": "The Administrative Core Survey: members rate the Administrative Core’s support, communication, and leadership.",
    "Grant Writing Program Survey": "The Grant Writing Program Survey: members rate the grant-writing support and how it helped their proposals.",
    "CNAP Reporting Hub Survey": "The CNAP Reporting Hub Survey: members rate how easy this site is to use, so it keeps getting better.",
    "Mentee Survey": "The Mentee Survey: project leaders rate the mentoring they receive. Confidential.",
    "Mentor Questionnaire": "The Mentor Questionnaire: mentors describe their mentoring and their mentee’s progress. Confidential.",
    "Pilot Grant Mentor Report": "The Pilot Grant Mentor Report: mentors of pilot projects report on meetings and progress, for the RPPR and the External Advisory Committee.",
    "Primary Research Grant Mentor Report": "The Primary Research Grant Mentor Report: mentors of research projects report on meetings and progress, for the RPPR and the External Advisory Committee.",
    "Research Project Semiannual Progress Report": "The research project progress report: the project leader’s accomplishments, plans, products, and team, written twice a year for the RPPR.",
    "Core Semiannual Progress Report": "The core progress report: the core director’s accomplishments, plans, and team, written twice a year for the RPPR.",
    "Pilot Project Semiannual Progress Report": "The pilot project progress report: the pilot leader’s accomplishments, plans, products, and team, written twice a year for the RPPR.",
    "Core Usage Report": "The Core Usage Report: the core director lists every project that used the core this period. It fills NIH’s Table 2 in the RPPR.",
    "NIH Documents": "Your yearly NIH documents for the RPPR: biosketch, Current and Pending (Other) Support, and the MFTRP certification."
  };
  var H = {
    "A quick monthly check-in": "A one-minute check on your planned proposal, so CNAP can offer help at the right moment.",
    "Add a grant proposal": "A new grant proposal record. The fields shown depend on where the proposal stands.",
    "Add a planned grant proposal": "A proposal you plan to submit. Best guesses are fine; you can update them later.",
    "Add a planned publication": "A paper you plan to write or submit. Best guesses are fine; you can update them later.",
    "Add a presentation": "A talk or poster you have already given, for the Center’s products count.",
    "Add a project": "A new CNAP research or pilot project. Add its leader and mentors next, so its forms go to the right people.",
    "Add a publication": "A new paper record. The fields shown depend on where the paper stands.",
    "CNAP Reporting Hub": "Kansas State University’s Center for Neuroscience Addressing Perception (CNAP) reporting site.",
    "Center results": "What the Center learned from everyone’s answers, with no one’s individual answers shown.",
    "Change password": "Changes the password you sign in with.",
    "Edit a presentation": "Change the details of a talk or poster you entered.",
    "Edit this grant proposal": "Change this proposal’s details, or move it to its next stage.",
    "Edit this publication": "Change this paper’s details, or move it to its next stage.",
    "Email me a sign-in link": "Signs you in without a password: a one-time link is emailed to you.",
    "Has your Current and Pending (Other) Support changed?": "February’s quick question, so the Current and Pending on file is current for the RPPR.",
    "Mark as published": "Records that this paper is published, and asks for the publication details.",
    "Mark as submitted / pending": "Records that this proposal was submitted, and asks for the submission details.",
    "My history": "Everything you have submitted, grouped by reporting period.",
    "My publications, talks, and grants": "Your papers, talks, and proposals, from planned to published or awarded.",
    "Period dashboard": "The open period, person by person and form by form.",
    "Your details (awarded)": "The award’s details, for RPPR Table 1.",
    "Your details (not funded)": "The decision’s details, and your next steps.",
    "Accomplishments": "What the project achieved this period, in the project’s own words, for the RPPR narrative.",
    "Add a relationship": "Gives this person a role on a project, a core, or the Center, which decides the forms they receive.",
    "Add a talk": "Adds a NeuroSync talk, so its speaker gets the Speaker Survey when it ends.",
    "Anything else": "Optional notes that do not fit elsewhere.",
    "Before your talk": "Questions about how the talk was arranged and supported beforehand.",
    "Biosketch": "Your NIH biosketch, built and certified in SciENcv.",
    "Challenges Encountered": "What slowed the work this period, and what helped.",
    "Changes": "Changes to the project’s plans, team, or effort that NIH should know about.",
    "Cores": "Every CNAP core, its RRID, and who runs it.",
    "Credit": "Who and what this product is credited to: CNAP members, projects, and cores. Credits drive the counts and the RPPR.",
    "Current CNAP relationships": "This person’s current roles, which decide the forms they receive.",
    "Current and Pending (Other) Support": "Your current and pending support, certified in SciENcv, for the RPPR.",
    "Email": "This person’s email addresses. Forms and sign-in links go to the primary one.",
    "Evaluation of Pilot Grant Progress": "The mentor’s rating of the pilot project’s progress.",
    "Evaluation of Project Progress": "The mentor’s rating of the research project’s progress.",
    "Evidence of Esteem": "Awards, invitations, and other recognition this period, for the RPPR.",
    "Foreign-activity documents (only if you have any)": "Documents about foreign appointments or support, only if you have any.",
    "Frequency of core use": "How often you used each of the core’s services.",
    "Grant Writing support from the CNAP administrative team": "Help the CNAP administrative team offers with your proposal.",
    "Grant proposals": "Every grant proposal, one row per submission.",
    "Helpful documents": "Guides and links every respondent sees on their My tasks page.",
    "Malign Foreign Talent Recruitment Program (MFTRP) certification": "The yearly certification NIH requires that you are not in a malign foreign talent program.",
    "Meetings": "Each meeting with your mentee this period.",
    "Mentoring": "Who mentors whom on this project.",
    "My Current and Pending Has Changed.": "Choose this if anything changed, then upload the new PDF.",
    "My Current and Pending Has Not Changed.": "Choose this if nothing changed since your last submission.",
    "My mentor or mentors": "Your mentors on this project.",
    "NIH reporting (RPPR D.1)": "The identifiers and effort NIH needs to list you in RPPR section D.1.",
    "Open-ended questions": "Questions answered in your own words.",
    "Or upload a whole semester at once": "Adds a semester of talks from one spreadsheet.",
    "Overall": "Overall ratings.",
    "Papers published": "Papers published by CNAP members, by year.",
    "Papers to check": "Published papers still waiting for a yes-or-no on the CNAP acknowledgment.",
    "Past imports": "Every roster file uploaded before.",
    "People on this project": "Everyone on this project, with their roles.",
    "Planned change in effort (RPPR D.2.a)": "Whether your effort will drop by 25% or more, which NIH asks about in D.2.a.",
    "Plans": "What the project will do next period, for the RPPR.",
    "Please review this product first": "A paper or proposal of yours that is out of date. Please confirm it or update its status.",
    "Presentations": "Talks and posters by CNAP members.",
    "Progress Towards Funding": "Progress toward independent grant funding, the COBRE’s main goal for project leaders.",
    "Progress Towards Graduation": "Progress toward graduating from COBRE support to independent funding.",
    "Projects that used the core this period": "Each project that used the core, one row each. These rows fill NIH’s Table 2.",
    "Proposals awarded": "Proposals that were funded.",
    "Proposals to check": "Submitted proposals still waiting for a yes-or-no on the CNAP acknowledgment.",
    "Publications": "Papers by CNAP members.",
    "Publications, talks, and grants": "Papers, talks, and proposals credited to this person.",
    "Qualitative data": "What people wrote in their own words, word for word, with themes once results are generated.",
    "Quality of services and functions": "How you rate the quality of each of the core’s services.",
    "Quick Research Performance Progress Report (RPPR) questions": "Short questions NIH asks in the RPPR, answered here so you never see the RPPR form itself.",
    "Ratings": "Agreement ratings on each statement.",
    "Recent forms": "The forms this person has been asked to fill in recently.",
    "Research team (RPPR section D.1)": "Everyone who worked on the project, with their effort, for RPPR section D.1.",
    "Send one of these emails by hand": "Sends a period email right now instead of waiting for the schedule.",
    "Sign-in": "How this person signs in, and whether they can.",
    "Suggested RPPR tables (optional)": "Optional tables NIH suggests for the RPPR.",
    "Survey questions": "The survey’s rating questions.",
    "Talks and posters": "Your talks and posters.",
    "Thanks for letting us know.": "A few short questions in place of the full survey.",
    "Upload a list": "Adds many entries at once from a spreadsheet.",
    "What CNAP has produced this year": "The Center’s papers, talks, and awards this grant year.",
    "Who can enter for you": "People you allow to add or update your papers, talks, and proposals for you.",
    "Your CNAP roles": "Your current roles, which decide the forms you receive.",
    "Your details": "Your department, title, and NIH identifiers.",
    "Your documents": "Documents CNAP keeps on file for you, such as your Statement of Work.",
    "Your talk": "Questions about the talk itself.",
    "1A. By funding source": "RPPR Table 1A: applications and awards by funder type.",
    "1B. By role": "RPPR Table 1B: applications and awards by the investigator’s CNAP role.",
    "By funder": "Proposals and dollars by funding agency.",
    "Items from last year that still need to be reported to NIH": "Items dated after last year’s RPPR went in. NIH allows them in this year’s RPPR, so they are included below.",
    "Pending proposals": "Proposals still waiting on a decision, split by the year they were submitted.",
    "Recent check-ins and answers": "The latest monthly check-in emails, and what people answered.",
    "Mentee Survey": FORMS["Mentee Survey"]
  };
  var HP = [
    [/^Good (morning|afternoon|evening), /, "Your to-do list for this reporting period."],
    [/^(To do|Coming up|Past talks|Due now|Check before launching) \((\d+)\)$/, function (m) { return {"To do": "Forms still waiting for you.", "Coming up": "Talks that have not happened yet.", "Past talks": "Talks already given.", "Due now": "Emails due to go out today.", "Check before launching": "Things to confirm before the period opens."}[m[1]]; }],
    [/^(\d+) people$/, "Everyone in the Hub who matches the filter."],
    [/^Year \d+ (Fall|Spring)( Open now| Coming up| is waiting for review)?$/, "This reporting period and where it stands."],
    [/: emails$/, "This period’s three automatic emails, their schedule, and who each would reach."],
    [/^(.+ Core|No core involved) \d+ publications?$/, "This core’s publications by type and status for the grant year."],
    [/ Over Time$/, "This section’s average rating in every reporting period since Year 6, with the biggest changes called out."],
    [/^Table \d+\. .+ Core$/, "This core’s survey results table, laid out like the site-visit reports."]
  ];
  function hdescribe(h) {
    var t = clean(h.textContent).replace(/\s*Roll up$/, "");
    if (!t) return "";
    var key = t.replace(/(Core)(Facility|User)/, "$1 $2");
    for (var name in FORMS) if (key.indexOf(name) === 0) return FORMS[name];
    if (H[t]) return H[t];
    for (var i = 0; i < HP.length; i++) {
      var m = t.match(HP[i][0]);
      if (m) return typeof HP[i][1] === "function" ? HP[i][1](m) : HP[i][1];
    }
    if (h.tagName === "H1") {
      var path = location.pathname;
      if (/\/manage\/people\/\d+/.test(path)) return "This person’s page: their roles, forms, products, documents, and NIH identifiers.";
      if (/\/manage\/projects\/\d+/.test(path)) return "This project’s page: its team, effort, identifiers, and credits.";
      if (/\/outcomes\//.test(path)) return "The record you are updating.";
      if (/^\/profile\/?$/.test(path)) return "Your profile: the details CNAP uses for NIH reporting, such as your department, eRA Commons ID, ORCID iD, effort, roles, and documents on file. Please check them once a year. Open a section below to see or update it.";
    }
    return "";
  }
  function runHeads() {
    document.querySelectorAll("main h1, main h2, main h3").forEach(function (h) {
      if (h.title || h.querySelector(".whyq") || h.closest("[title]")) return;
      var d = hdescribe(h);
      if (h.classList.contains("rollhead")) d = (d ? d + " " : "") + "Click the title to roll this section up or open it again.";
      if (d) h.title = d; else h.setAttribute("data-nohelp", clean(h.textContent).slice(0, 70));
    });
  }
  function runAll() { run(); runButtons(); runHeads(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { setTimeout(runAll, 0); });
  else setTimeout(runAll, 0);
  window.cnapHeadHelp = { describe: describe, run: run };
})();
