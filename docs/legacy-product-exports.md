# Legacy product exports (Piestar, Years 6–9): notes for the later import

MW has 30 workbooks: Publications, Presentations and Grants for Years 6–9, three snapshots per year.
The suffix is the month the export was taken (MW, 2026-10-26): **.1 = January** (Fall collection),
**.4 = April** (RPPR), **.6 = June** (Spring collection / site visit). MW chose to import them row by row
**later, on the K-State server after the security review**, through the site's own import screen. Nothing
from them is in this repository: these notes record only file layouts and column names, no data.

## What an importer has to handle

- **Snapshots overlap.** The same paper, talk or proposal appears in several snapshots (and years) with its
  status moving on. Import the latest snapshot of each item and build its status history from the earlier ones
  (dates: Created, Updated, Cleaned At, Submitted Date, Publication Date).
- **"First Reported In Year"** gives the RPPR year an item was first reported: map it to the never-twice fields
  (`publications.rppr_year`; grants' `rppr_submitted_year` / `rppr_awarded_year` by status).
- **Layouts differ by year.** The data sheet is "Unique Entries", "Final Data" or "GrantsAwards"; column sets
  vary (counts below). Below the data rows each workbook has MW's summary blocks (counts by core, status, type,
  totals): an importer must stop at the first blank `#` / title row and ignore everything after it.
- **Cores** come from "Involved Cores Names" / "Involved Cores Slugs", the per-core flag columns
  ("BN Core Involved" …) or the Projects / Related Projects text; map to Resources (BN, NI, CN, Admin).
- **Grant dollars:** Amount + Indirect Amount = total costs. "Based on NIH COBRE Funding" (Yes/No) is kept.
- **Statuses** map to the site's: Piestar publication statuses Under Review / Accepted / Awaiting Publication /
  In Pre-Print / Published / Not Published / Submitted / Other; grant statuses Awarded / Pending / Declined.
- **People** are matched by e-mail ("User Email") to existing Person records; unmatched rows go to review, as in
  the roster import. Author and investigator strings are kept as display text.
- Rows marked as drafts ("Is Draft") or incomplete are reviewed, not imported silently.

## Files and columns

### Grant

- **Grant Y6.1**: sheets Codebook, GrantsAwards, Unique Entries; data on *Unique Entries*, 47 named columns
- **Grant Y6.4**: sheets Codebook, GrantsAwards, Unique Entries; data on *Unique Entries*, 33 named columns
- **Grant Y6.6**: sheets Codebook, GrantsAwards, Final Data; data on *Final Data*, 32 named columns
- **Grant Y7.1**: sheets Codebook, Unique Entries; data on *Unique Entries*, 39 named columns
- **Grant Y7.4**: sheets Codebook, GrantsAwards; data on *GrantsAwards*, 50 named columns
- **Grant Y7.6**: sheets Unique Entries; data on *Unique Entries*, 39 named columns
- **Grant Y8.1**: sheets Codebook, Unique Entries; data on *Unique Entries*, 52 named columns
- **Grant Y8.4**: sheets Codebook, Unique Entries; data on *Unique Entries*, 51 named columns
- **Grant Y8.6**: sheets Codebook, Unique Entries; data on *Unique Entries*, 34 named columns
- **Grant Y9.1**: sheets Codebook, GrantsAwards, Unique Entries; data on *Unique Entries*, 48 named columns

  Columns (number of files that have each): Proposal Title (10); Co Principal Investigators (10); Year (10); Status (10); User Name (10); Investigators (10); Proposal Type (10); Submitted Date (10); Funding Agency (10); Amount (9); # (9); Grant Number (9); Based on NIH COBRE Funding (9); Cleaned At (9); Related Projects (9); Indirect Amount (9); First Reported In Year (9); Involved Cores Names (9); Project (9); Updated (9); Performance Period Start Month (8); Performance Period End Year (8); Project Type (8); Performance Period Start Year (8); Performance Period End Month (8); Created (8); Involved Cores Slugs (7); Tags (7); Is Computer Time (7); User Email (7); Relationship (7); Hours (6); No Core Selected (6); Pi (5); Copi (5); Id (5); BN Core Involved (5); CN Core Involved (5); NI Core Involved (5); AD Core Involved (5); Microscope Used (4); Senior Personnel (4); BN Core (3); CN Core (3); NI Core (3); Involved Cores Bn (3); Involved Cores Ad (3); Involved Cores Ni (3); Updated By (3); Personnel Tags (3); Session Id (3); Copied From Id (3); Module Id (3); Is Complete (3); Created By (3); Created In Session Id (3); Duplicates (3); Length (2); AD Core (2); Long Title (2)

### Presentations

- **Presentations Y6.1**: sheets Codebook, Presentations, Unique Entries; data on *Unique Entries*, 17 named columns
- **Presentations Y6.4**: sheets Codebook, Presentations, Unique Entries; data on *Unique Entries*, 21 named columns
- **Presentations Y6.6**: sheets Codebook, Presentations, Unique Entries; data on *Unique Entries*, 20 named columns
- **Presentations Y7.1**: sheets Codebook, Unique Entries; data on *Unique Entries*, 26 named columns
- **Presentations Y7.4**: sheets Codebook, Unique Entries; data on *Unique Entries*, 25 named columns
- **Presentations Y7.6**: sheets Unique Entries; data on *Unique Entries*, 29 named columns
- **Presentations Y8.1**: sheets Codebook, Unique Entries; data on *Unique Entries*, 35 named columns
- **Presentations Y8.4**: sheets Codebook, Unique Entries; data on *Unique Entries*, 35 named columns
- **Presentations Y8.6**: sheets Codebook, Unique Entries; data on *Unique Entries*, 27 named columns
- **Presentations Y9.1**: sheets Codebook, Unique Entries; data on *Unique Entries*, 35 named columns

  Columns (number of files that have each): Type (10); Authors (10); Presentation Date (10); Event (10); Year (10); Title (10); User Name (10); # (10); Location (10); Project (9); First Reported In Year (8); Tags (7); Project Type (7); Id (7); Updated (7); User Email (7); Overall (7); Relationship (7); Cleaned At (6); No Core Involved (6); Created (6); BN Core Involved (5); CN Core Involved (5); NI Core Involved (5); Admin Core Involved (5); BN Core (4); CN Core (4); NI Core (4); Personnel Tags (4); Douplicates accounted for: (4); Is Complete (4); Ad Core (3); Related Projects (3); Updated By (3); Session Id (3); Module Id (3); Created By (3); Created In Session Id (3); Duplicates (3); Other Description (2); Microscope Used (2); Involved Cores Names (2); Involved Cores Bn (2); Involved Cores Ad (2); Conference Name (2); Involved Cores Ni (2); Involved Cores Eeg (2); Cleaned By (2); Admin Core (1); Project+E:M Type (1); Meena Kumari (KSU) - Exosomes and modulation of neuroplasticity by oxycodone using 3D human brain cell culture (1); Charles Pickens - Flexible goal-directed action (1); Tianjun Sun (KSU) - Building AI agents to assess cognitive functioning in older adults (1); No Core Selected (1); Maria Diehl - Prefrontal circuits of active avoidance under social conditions in rats (1); Projects (1); Copied From Id (1); Student Authors (1)

### Publications

- **Publications Y6.1**: sheets Codebook, Publications, Unique Entries; data on *Unique Entries*, 34 named columns
- **Publications Y6.4**: sheets Codebook, Publications, Unique Entries; data on *Unique Entries*, 43 named columns
- **Publications Y6.6**: sheets Codebook, Publications, Final Data; data on *Final Data*, 40 named columns
- **Publications Y7.1**: sheets Codebook, Unique Entries; data on *Unique Entries*, 57 named columns
- **Publications Y7.4**: sheets Codebook, Unique Entries; data on *Unique Entries*, 48 named columns
- **Publications Y7.6**: sheets Unique Entries; data on *Unique Entries*, 55 named columns
- **Publications Y8.1**: sheets Codebook, Unique Entries; data on *Unique Entries*, 46 named columns
- **Publications Y8.4**: sheets Codebook, Unique Entries; data on *Unique Entries*, 63 named columns
- **Publications Y8.6**: sheets Codebook, Unique Entries; data on *Unique Entries*, 25 named columns
- **Publications Y9.1**: sheets Codebook, Unique Entries; data on *Unique Entries*, 61 named columns

  Columns (number of files that have each): # (10); Year (10); Type (10); Status (10); First Reported In Year (10); Involved Cores Names (10); Conference End Date (9); Authors (9); Published Year (9); Publication Identifier (9); First Page Or Elocation Id (9); Volume (9); Publication Location (9); Publication Identifier Type (9); Citation (9); Publication Date (9); Related Projects (9); Peer Reviewed (9); User Name (9); Award Acknowledged (9); Issue (9); Journal (9); PMCID (9); Title (9); Project (9); Project Type (8); Conference Name (8); Status Other (8); Involved Cores Slugs (8); Updated (7); Thesis Institution (7); Thesis Completion Date (7); Publication Identifiers List Names (7); Publication Identifiers List Slugs (7); Relationship (7); Publication Identifiers (7); Microscope Used (6); Cleaned At (6); Tags (6); Id (6); User Email (6); Created (6); BN Core Involved (5); NI core Involved (5); Files (5); CN Core Invovled (5); No Core Specified as Involved  (5); Admin Core Involved (5); Involved Cores Bn (4); Involved Cores Ad (4); Involved Cores Ni (4); Involved Cores Eeg (3); Type Other (3); Elocation Id (3); Personnel Tags (3); Is Complete (3); Keyword List (3); BN Core (2); CN Core (2); Description (2)
