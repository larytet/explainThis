# diff-viz: requirements specification

Status: draft 0.2 (adds the guided "Lead me" mode, section 4.3, after CodeRabbit's Change Stack). Mock: `mock/index.html` (open in a browser; all data in it is illustrative).

diff-viz shows a code change (a pull request, a commit range, a branch comparison) as a zoomable picture. At the lowest zoom it
is an ordinary code diff. As the user zooms out, the code is progressively hidden and replaced by AI-written abstractions:
hunk summaries, symbol-level changes, component-level changes, and finally one architecture-level overview of the change.
It is "explain-this for a diff".

A second way in, "Lead me" (section 4.3), takes the same ledger and walks the user through the change one group at a time:
changes grouped by meaning into cohorts, each cohort split into ordered layers, one layer on screen at a time.

It ships as three front ends over one core: a GitHub browser extension, a VS Code extension, and a standalone app.

## 1. Source of the method: the explain-this skill

The method comes from `.claude/skills/explain-this/SKILL.md`. This spec adapts it to diffs and does not weaken it. Where this
spec and the skill disagree on a rule about evidence, the skill wins. The rules carried over, in the skill's own terms:

| Skill rule | Meaning in diff-viz | Requirement |
|---|---|---|
| Code is the primary source, at every level | A summary of a hunk, a function, a component, or the whole PR is grounded in the diff and the files it touches | R-E1, R-E2 |
| Bottom-up review before anything is presented | Pass 1 reads leaves first and builds the ledger; no view is produced before it exists | R-P1 |
| Present top-down: purpose, structure, details, unknowns | Pass 2 renders from the overview downward, in that order | R-P2 |
| Ledger of claims with evidence | The Change Ledger (section 4) is the only input to every abstract view | R-L1 |
| Verified / inferred / stated-in / unverified | Every abstract block carries one of the four labels, visible at all times | R-E3 |
| Verification pass before sending | Every citation is re-checked against the diff before a view is shown | R-V1 |
| Prefer "could not verify" over a plausible guess | An unverified claim is shown as unverified, or omitted; never smoothed over | R-E4 |
| Docs, tickets, threads support but never ground a claim | PR text and linked tickets are labelled "Stated in <source>" and checked against code | R-X1 |
| Read-only | The tool never edits, formats, commits or comments on the code | R-S1 |
| Define terms at first use, running glossary | Project terms and patterns used in a summary are defined once, then listed in a glossary | R-G1 |
| Length budgets and stop points | Each abstract block has a size budget; "details on request" instead of longer text | R-B1 |
| Stay on a piece until the user moves on | The user drives zoom and focus; the tool does not auto-advance | R-U5 |
| Top-down, one piece at a time, stop after each | "Lead me" shows one layer, then waits for the user (next, previous, or jump) | R-GR3 |

## 2. Goals and non-goals

Goals

- G1. A reviewer can understand what a change does, at the depth they choose, without reading every line.
- G2. The user can move from the real code to a fully abstracted view and back with one control, and always see which code
  backs any abstraction.
- G3. Hallucination is minimised by construction: abstractions are generated from a verified ledger and are mechanically
  checked, not trusted.
- G4. The same core and the same views in all three front ends.

Non-goals

- N1. Not a code reviewer: it does not decide whether a change is good or post review comments (a later, separate feature).
- N2. Not a replacement for the raw diff: the raw diff is always one gesture away (zoom level L0).
- N3. Not an editor: no edits to the repository.
- N4. Not a merge or conflict tool.

## 3. Users and front ends

Users: a reviewer who did not write the change; an author checking an AI-generated change they did not fully read; a tech lead
asking "what did this PR do to the architecture"; a new team member reading history.

| Front end | Where | Input | Notes |
|---|---|---|---|
| GitHub extension | Browser extension (Chrome, Firefox, Edge) on a PR's "Files changed" and on compare and commit pages | The PR the page shows, fetched through the GitHub API with the user's own token | Adds a "diff-viz" tab and a zoom bar; leaves GitHub's own views untouched |
| VS Code extension | A webview panel, plus a command "diff-viz: explain this diff" | Working-tree changes, a commit range, a branch compare, or a PR through the GitHub pull-requests extension | Clicking a block opens the real file at the cited lines |
| Standalone app | Desktop app (Electron or Tauri; decision D1) and a CLI that opens it | Any local git repository, any two refs, or a GitHub or GitLab PR URL | Works offline against a local repo with a local model |

All three embed the same renderer and call the same core (section 5). A front end only supplies input, authentication and
navigation to the real file.

## 4. The two passes

### 4.1 Pass 1, bottom-up: build the Change Ledger

Nothing abstract is shown until Pass 1 has finished for the part of the change being shown. Pass 1 mirrors Phase 0.25 and
Phase 1 of the skill, applied to a diff.

1. R-P1.1 Map the change: list files with added and removed line counts; classify each file (source, test, config, migration,
   docs, generated, vendored, lockfile); identify renames and moves; read the commit messages and the PR description as
   claims to check, not as facts.
2. R-P1.2 Split each file into hunks, then into symbols (function, method, type, constant, config key) using a syntax-tree
   parser (tree-sitter). Each changed symbol is classed `added`, `removed`, `modified`, `moved`, `renamed`, or `format-only`.
   This step is deterministic and uses no model. Behaviour-preserving changes (whitespace, import order, rename without body
   change) are detected here, not guessed by a model.
3. R-P1.3 Order work from the leaves up: first symbols that call nothing else that changed (types, constants, helpers), then
   their callers in the diff, then the components that contain them, then the entry points. The call picture comes from the
   syntax tree and the language server (references, definitions); a model may not invent an edge.
4. R-P1.4 For each symbol, read the old and the new body (the full file at both revisions, not the hunk alone) and write a
   ledger entry: what changed, inputs and outputs, side effects, error handling, invariants it relies on. For each caller, read
   it together with the entries of what it calls and write what the composition now does. Note where a caller assumes
   something the callee does not guarantee.
5. R-P1.5 Read the tests changed or touched by the change. Record where code and tests disagree, and where new behaviour has
   no test in the diff.
6. R-P1.6 Check the history when it explains a surprising change (a workaround, a revert, a rewrite).
7. R-P1.7 Only after the code has been read, compare with the PR description, linked tickets and docs. Where they disagree
   with the code, record the disagreement as its own ledger entry. The code wins.

Large changes: independent files and packages are processed in parallel by separate model calls. Each call must report facts
with evidence and separate what it read from what it guessed. Any load-bearing claim (one that appears in the L3 or L4 view)
is re-read by a second, independent call before it enters the ledger (the skill's rule for subagents).

#### The Change Ledger (data contract)

One ledger per diff. One entry per claim.

```
LedgerEntry {
  id            stable id, e.g. "C3"
  level         "hunk" | "symbol" | "component" | "change"      the highest level at which it may appear
  claim         one sentence, plain language
  label         "verified" | "inferred" | "stated" | "unverified"
  evidence[]    { file, revision: "old" | "new", lines: [from, to], hunkId }   at least one unless label = "unverified"
  reasoning     required when label = "inferred": the steps from evidence to claim, in one or two sentences
  source        required when label = "stated": ticket key, page title or PR text, plus "code agrees" | "code disagrees" | "not checked"
  depends_on[]  ids of the lower-level entries this one is composed from (this is what makes the zoom hierarchy)
  kind          "behavior" | "interface" | "risk" | "test-gap" | "format-only" | "disagreement" | "unknown"
  terms[]       project terms and patterns used, each pointing to a glossary entry
}

Cohort {
  id            e.g. "G1"
  name          short name of the purpose, e.g. "Retry failed charges"
  why           one sentence: what ties the layers together (a ledger claim, labelled like any other)
  layers[]      ids of its layers, in reading order
}

Layer {
  id            e.g. "Y3"
  cohort        id of its cohort
  title         short, plain language
  order_reason  one sentence: why it is read at this position ("Charge calls backoff, so read backoff first")
  claims[]      ledger entry ids the summary is made from (the summary is a rephrasing of these, R-L1)
  ranges[]      { file, revision, lines: [from, to], hunkId }   the diff lines the layer owns
  diagram       null, or { type: "sequence" | "state" | "entity-relationship" | "flow", built_from[]: claim ids }
}
```

R-L1. Every abstract view is a function of the ledger only. The renderer and the summariser never receive raw code as a
prompt to "summarise"; they receive ledger entries and render or rephrase them.
R-L2. An entry at level `component` or `change` must list the lower entries it depends on; its label may not be stronger
than the weakest entry it depends on, unless a reasoning step is recorded (and then it is `inferred`).
R-L4. Cohorts and layers are stored in the ledger. They are derived from `depends_on` and the call graph of R-P1.3, so a model
may propose a grouping or a name but may not invent a dependency; a layer's `order_reason` must name a real edge.
R-L3. The ledger is stored with the diff (local cache keyed by the two revisions) so the same diff gives the same views.

### 4.2 Pass 2, top-down: explain from the ledger

Pass 2 mirrors Phases 0.5 to 3 of the skill. It renders, in this order, with each part collapsible:

1. R-P2.1 Purpose: what the change is for, who it affects, what it does not touch. (Level L4.)
2. R-P2.2 Modules: changed components grouped by repository and package; for each, a one-line responsibility and whether it is
   core to the change or supporting. Where the change crosses a boundary (an API, a message, a schema, a config contract),
   name the interface and the side that owns it. (L3.)
3. R-P2.3 How the pieces fit: the direction of dependency among the changed components, and the one to three main flows the
   change alters, at component level. (L3 to L4.)
4. R-P2.4 State and external effects: databases, files, caches, queues, external systems whose behaviour or data shape changes.
5. R-P2.5 Pieces, ordered by architectural role, top-down: the components that carry the change's purpose first, then what they
   use, then shared leaves, then wiring and configuration last. A piece is small enough to read in one sitting.
6. R-P2.6 Key details and decisions per piece: invariants, error handling, concurrency, data shapes, anything surprising.
7. R-P2.7 What could not be determined: every `unverified` entry, every `inferred` entry, every disagreement between text and
   code, and every behaviour with no test in the diff. This section is always reachable from every zoom level (R-E3).

R-P2.8 The "pieces" are the units the zoom works on: zooming in on a piece moves from its L3 card down through its symbols (L2)
to its hunks (L1) to its code (L0).

### 4.3 Guided review ("Lead me"): changes grouped by meaning, one at a time

Zoom (section 5) lets the user choose the depth. "Lead me" is the other mode: the tool chooses the order and the user only
says "next". It is opt-in, the zoom view stays the default, and one control switches between them without losing the place.
The idea follows CodeRabbit's Change Stack (a flat, alphabetical file list becomes a guided walkthrough organised by intent).
Everything the tool shows in this mode still comes from the ledger and keeps the four labels and the checks of section 7.

Grouping

- R-GR1. Cohorts: the change is split into a small number of independent groups of changes, each with one purpose
  (target: 2 to 7 for a 100-file change). Independent means no layer of one cohort depends on a layer of another, so a cohort
  can be read, and judged, alone. Format-only, generated and lockfile changes form their own cohorts, folded by default.
- R-GR2. Layers: each cohort is split into layers in logical reading order: what the others rely on first (types, settings,
  helpers), then what composes them, then entry points and wiring, then tests and gaps last. Order comes from the dependency
  edges (R-L4), not from file path. Each layer owns specific line ranges.
- R-GR2a. Coverage: every changed hunk belongs to exactly one layer. The UI shows "layers cover n of n hunks"; a hunk that no
  layer owns is a build error, not a hidden item. The raw hunks stay one click away (R-Z5).
- R-GR2b. A layer is small enough to read in one sitting (budget: about 1 screen of summary and 60 changed lines, R-B1). A larger
  one is split, or marked as a long layer with the reason.

One at a time

- R-GR3. One layer is on screen at a time: its summary and the lines behind it. The tool never advances on its own (R-U5).
  Controls: next and previous, a jump from the outline, and keys `J` (next) and `K` (previous). The first step is an overview
  of the cohorts and layers, so the user sees the whole route before taking the first step.
- R-GR4. Each layer shows: title, why it is read now (`order_reason`), the summary as claims with label and evidence chips
  (R-Z6), the cited lines with a little surrounding context so the user stays on that layer's part of the change, and where
  relevant the unverified and inferred items that touch it. The layer's lines are the ones backing its claims (R-Z4).
- R-GR5. Diagrams only when the structure warrants one: an API contract or message shape (entity-relationship), a state
  transition (state), a call sequence across components or services (sequence), a loop or branching with several exits (flow).
  A layer with no such structure stays text. A diagram is built from ledger entries, lists them under it, and may not show an
  edge the ledger does not hold (R-V1 applies to a diagram's nodes and edges).
- R-GR6. Progress: each layer has a "reviewed" mark, shown in the outline, with a count per cohort and overall. It is the
  reader's own mark; the tool never sets it. Reviewed marks and the per-file "Viewed" boxes (R-U18) agree: a file is viewed
  when all layers that own its hunks are reviewed, and the UI says so.
- R-GR7. End of the route: the last step lists the cohorts and layers not yet marked reviewed, every `unverified` entry, and
  every disagreement between text and code (R-P2.7), so the reader does not finish without seeing the unknowns.
- R-GR8. Focus mode (`Z`): hides the outline and the evidence rail and leaves one layer on screen. `Esc` leaves focus mode,
  then leaves "Lead me".
- R-GR9. The evidence rail follows the layer: on each step it opens the first claim of the layer, and while the user scrolls
  within a layer it highlights the claim whose lines are in view.
- R-GR10. Snapshots: the walkthrough is built for one pair of revisions (R-L3). The view shows the head commit it was built
  from. If the branch has moved on, a banner says so, names the new commit, and offers to rebuild; earlier snapshots of the
  same change can be selected, with their reviewed marks kept per snapshot.
- R-GR11. Permalinks (R-U20) include the mode, the layer and the snapshot, so "layer 3 of this change" can be sent to
  someone. Sign-in redirects keep the exact link.
- R-GR12. The same settings (audience, focus, noise, detail) apply. Focus "risks" reorders nothing in the route; it only
  emphasises layers that carry risk and flags them in the outline. A layer is never skipped by a setting (R-D2).
- R-GR13. Read-only (R-S1): comments on a layer's line ranges, a draft review and submission to the host belong to R-U21 and are
  not part of version 1.

- R-GR14. Calm screen: the guided view follows the section 8.1 rules. At most three panels (layers, code, evidence), one
  line of header, one line of footer, and everything else behind a menu.

What differs from Change Stack, on purpose: every sentence carries a label (verified, inferred, stated, unverified) and cited
lines that were checked mechanically (R-V1); the grouping and order rest on dependency edges, not on a model's opinion; the
tool shows what it could not determine; and it runs over a local repository as well as a pull request.

## 5. Zoom model

A single zoom control moves the whole canvas between five levels. Each level is a different representation of the same ledger,
and every element at a level links to the elements it is composed from.

| Level | Name | What is on screen | Code visible | Backed by |
|---|---|---|---|---|
| L0 | Code | The real diff, side by side or unified, with syntax highlighting | All | The diff itself |
| L1 | Hunks | Each hunk collapsed to one line of intent, with +/- counts; format-only hunks collapsed to a single grey bar | A peek on hover | `hunk` entries |
| L2 | Symbols | One card per changed function, type, constant or config key: old behaviour, new behaviour, callers affected | Signature only | `symbol` entries |
| L3 | Components | One card per changed component or package: what it now does differently, interfaces it changes, test coverage | None | `component` entries |
| L4 | Change | Purpose, main flows, a component graph with changed parts highlighted, risks and unknowns | None | `change` entries |

Requirements

- R-Z1. The zoom control is continuous (slider, pinch, ctrl+wheel) and snaps to the five levels; a level change cross-fades
  from code to abstraction. Keyboard: `+` and `-`, `0` to `4` to jump to a level.
- R-Z2. Semantic zoom per block: any block can be zoomed independently of the global level (click the block's own +/-), so a
  user can read one function as code inside an otherwise abstract view. A block with a local override shows a marker.
- R-Z3. The pointer position is the zoom anchor: the block under the pointer stays under the pointer across levels.
- R-Z4. Going to a lower level always shows the evidence for the block just left: the cited lines are highlighted on arrival.
- R-Z5. The raw diff (L0) is always reachable in one action from any level, and `Esc` returns to the previous level.
- R-Z6. Every abstract block shows a label chip (verified, inferred, stated, unverified) and an evidence chip listing the cited
  `file:line` ranges. Clicking the chip opens the evidence panel with the cited code, in place.
- R-Z7. Unverified and inferred blocks are visually distinct (dashed border for unverified, tilde for inferred) at every level and
  can never be hidden by a setting.
- R-Z8. Order of blocks follows R-P2.5 (architectural role), not file order. A toggle shows file order.

## 6. Dynamic settings

The AI chooses the presentation, within limits, from settings the user picks. Settings change how much is abstracted and what
is emphasised; they never change what is true. The same ledger is rendered under any settings (R-L3).

| Setting | Values | Effect |
|---|---|---|
| Zoom | L0 to L4 | Section 5 |
| Audience | new to the language, new to the codebase, new to this module, expert (default: expert) | Controls term definitions (R-G1), how much "why" is spelled out, and the default zoom |
| Focus | behaviour, interfaces, risks, tests, everything | Orders and highlights blocks; the rest stay available |
| Noise | show all, fold format-only and generated, fold also test files | Folding is by the class from R-P1.1 and R-P1.2; folded items are counted and openable |
| Detail budget | brief, normal, long | Scales the word budgets in R-B1 |
| Compare to | PR description, none | Whether the text-versus-code disagreements (R-X1) are shown |
| Mode | zoom view (default), Lead me | Section 4.3 against section 5; the same ledger, switchable at any time |

R-D1. The AI may choose a starting zoom per block from audience, focus and block size (for example, open a large format-only
hunk at L1 and a risky symbol at L0). Every automatic choice is shown ("opened at L0 because: touches payment retry") and is
undone with one click.
R-D2. A setting never removes an entry from the ledger and never raises a label. Only presentation changes.
R-D3. Settings persist per user, and may be overridden per repository by a `.diff-viz.yml` file (section 9).

## 7. Anti-hallucination requirements

This is the core quality requirement. The skill states: "A confident but wrong explanation is worse than none."

- R-E1. Every statement shown in any abstract view carries at least one evidence reference, except entries labelled
  `unverified`, which say so.
- R-E2. A claim about the code cites the code (`file:line`, old or new revision). Summaries of summaries cite the entries they
  are built from, which cite the code.
- R-E3. The four labels are the only way a statement can appear. They are always visible and never collapsed into a single
  "AI summary" badge. Definitions: verified (the cited lines directly state or implement it), inferred (follows from cited lines;
  the reasoning is shown), stated (taken from a ticket, doc or thread; source named; code agreement shown), unverified (not
  confirmed in code: intent, external service behaviour, runtime-only behaviour).
- R-E4. Intent, design rationale and performance are never presented as fact unless a comment, commit message, test or doc
  states it, and then the source is cited. "Should do" is never rendered as "does".
- R-E5. Deterministic first: whatever the parser, the language server or `git` can establish (what changed, what moved, who calls
  whom, whether only formatting changed) is computed without a model and marked verified. A model only words the behaviour of
  bodies and the composition of entries.
- R-V1. Verification pass: after generation and before display, a mechanical check runs on every entry.
  1. Each cited file, revision and line range exists.
  2. Each cited range lies inside, or is directly connected to, the symbol the claim is about.
  3. Identifiers named in the claim (functions, fields, constants, numbers, strings) appear in the cited range. A claim that
     names `MaxRetries` cites a range that contains it.
  4. A second, independent model call is given only the claim and the cited code and answers "does the code state this?":
     yes, partly, no. "Partly" downgrades to `inferred` or splits the claim; "no" drops it and records it in the audit log.
  5. Numbers in a claim (counts, limits, timeouts) are compared with the values in the cited lines.
- R-V2. A claim that fails verification is never shown as a guess. It is dropped, or shown as `unverified` with the reason.
- R-V3. The audit log (what was dropped or downgraded and why) is viewable (section 8, panel "Audit").
- R-V4. Reproducibility: model, version, prompt hash and ledger hash are stored per view, and shown on request.
- R-V5. If Pass 1 could not finish for part of the change (too large, a generated file, a language without a parser, a timeout),
  that part is shown at L0 and L1-by-parser only, with the reason. The tool does not fill the gap with an abstraction.
- R-V6. Coverage meter: the UI always shows how many changed lines are covered by at least one verified or inferred entry, and
  how many are not.

## 8. UI and UX requirements

The mock (`mock/index.html`) shows the intended layout. It is a static page: GitHub Pages serves it from the repository root
at `<pages-url>/diff-viz/mock/` (see `README.md` in this folder).

Layout (all front ends)

- R-U1. Top bar: source (repo, base and head), front-end frame, Pass indicators (section 4), settings menu.
- R-U2. Left: outline in top-down order (the pieces of R-P2.5) with progress and risk markers. Clicking a piece scrolls and
  sets focus; it does not change the zoom unless the user asks.
- R-U3. Centre: the canvas of blocks at the current zoom.
- R-U4. Right: the evidence panel. For the selected block: claim, label, reasoning (if inferred), source (if stated), the
  cited code with the cited lines highlighted, the entries it is built from, and the entries built from it.
- R-U5. Bottom: the zoom bar (five labelled stops), the coverage meter, and the glossary and audit buttons. The tool never
  advances on its own; the user moves between pieces and levels (the skill's stop-and-wait rule). A "next piece" control exists.
- R-U5a. In "Lead me" the bottom bar swaps the zoom slider for previous, next, "layer reviewed" and a "More" menu (R-GR3,
  R-GR6, section 8.1); the left outline lists cohorts and their layers instead of pieces; the evidence panel stays and the
  difference map goes. The "Lead me" button is in the top bar next to the theme toggle and reads "Back to zoom view" while
  active.
- R-U6. Two Pass indicators are always visible: "Pass 1 bottom-up: n of m symbols read, k claims" and "Pass 2 top-down".
  While Pass 1 runs, the views already supported by finished parts are available; the rest show "reading". No abstract view is
  built from a part that is still unread.

### 8.1 Calm layout (after the Change Stack screenshot)

CodeRabbit's Change Stack screen has one thin header line, a narrow list of layers (title and one small line each), a diff
with a two-line summary above it, and a collapsible context rail on the right. No settings row, no zoom bar, no meters. The
mock had all of those on screen at once. The rules below take the same restraint, and keep the evidence rules of section 7.

- R-U21a. Settings (audience, focus, noise, detail, file order, side-by-side) live behind one "View" button and are hidden
  by default in both modes. The settings still apply; only the strip is hidden. A changed setting shows a dot on the button.
- R-U21b. Header: one line. Source, "Lead me" or "Back to zoom view", "View", theme. Pass indicators, front-end switches and
  similar status belong to the zoom view and to a menu, not to the guided header.
- R-U21c. Footer in "Lead me": previous, position ("Layer 3 of 5"), next, "layer reviewed", "More". Coverage meter, glossary,
  audit log, copy as Markdown, legend, snapshot details, panel toggles and keys are inside "More" (and keep their keys).
- R-U21d. Left list: layers only, grouped by cohort, each with its title and a tick when reviewed. No file list and no legend
  in this mode (the reviewed ticks replace the per-file boxes). The list can be hidden (`[`).
- R-U21e. One summary per layer, at most two lines, with one label chip: the weakest label among the claims it is built from.
  The claims behind the summary follow, with this rule for folding: `verified` claims fold under "n verified claims";
  `inferred`, `stated` and `unverified` claims stay visible (R-Z7, R-E3). Nothing is removed from the ledger (R-D2).
- R-U21f. Evidence references: in "Lead me" the per-claim `file:line` chips are replaced by the layer's ranges in the header of
  the code card and by the evidence panel, which opens on a click on any label chip (R-Z6 still holds: one click reaches the
  cited lines). Cited lines in the card are the layer's own lines plus two lines of context.
- R-U21g. Evidence panel: collapsible (`]`), one claim at a time, opens on the layer's first claim, and shows only the selected
  claim, its lines, and what it is built from. It does not repeat the layer's summary.
- R-U21h. Unchanged code is not shown. A collapsed "n unmodified lines" row sits between hunks and expands in place (R-U19).
- R-U21i. One accent colour. Colour is for the four labels and the diff; everything else is grey (R-U11: colour is never the
  only carrier of a label).
- R-U21j. The difference map (R-U14) belongs to the zoom view. In "Lead me" the outline and the position text do its job.

Interaction

- R-U7. Hover a block: highlight its evidence lines in the context of the real file (in VS Code: in the editor).
- R-U8. Click a chip: open the evidence panel. Double click a block: zoom that block in one level.
- R-U9. "Why am I seeing this?" on an automatic choice (R-D1).
- R-U10. Copy as Markdown: the current view, with labels and `file:line` references, hard-wrapped at about 120 columns, for use
  in a PR description or a chat.
- R-U11. Accessibility: keyboard-only operation, screen-reader names for labels and levels, contrast AA in light and dark
  themes, labels are never conveyed by colour alone.
- R-U12. Performance: first view (file list and L0) within 1 s for a 100-file change; L1 by parser within 5 s; abstract
  levels stream in as Pass 1 completes per part. Zoom animation at 60 fps for a canvas of up to 500 blocks (virtualised).

Keyboard map: `0` to `4`, `+`, `-` zoom (zoom view); `F7` and `F8` previous and next block; in "Lead me", `J` next layer, `K`
previous layer, `Z` focus mode, `Esc` leave focus, then leave "Lead me".

Ideas borrowed from existing diff tools (the mock implements the first five, and the "Lead me" mode)

From Beyond Compare:
- R-U13. Side-by-side view at L0 with the changed lines paired across a centre gutter (toggle with unified view).
- R-U14. Difference map: a narrow strip beside the canvas with one mark per block, coloured by label, showing the viewport;
  click to jump. Unverified marks stand out, so the reader can see where the unknowns are in a long change.
- R-U15. Next and previous change on F8 and F7 (also buttons), moving through blocks at the current zoom.
- R-U16. Status colours and counts per file in a tree; "show differences only" is the default (the Noise setting folds the rest).
- R-U17 (later). Intra-line highlighting of the changed words, and connector bands from the old block to the new block for
  moved code.

From GitHub code review:
- R-U18. File list with +/- counts and a per-file "Viewed" checkbox with a progress count; viewed files collapse.
- R-U19. Unified and split toggle; hide-whitespace toggle (the Noise setting); expanders to reveal more context around a hunk.
- R-U20. Permalinks to a view: file, line, zoom level and settings, so a reviewer can send "this block at L2".
- R-U21 (later, outside N1 for version 1). Comment threads on a block, posted to the PR from the evidence panel.

Front-end specifics

- GitHub extension: injected tab and zoom bar on the PR page; does not alter GitHub's own diff; deep links to GitHub's own
  line anchors; works on public repositories without a token, on private ones with the user's token held in extension storage.
- VS Code extension: webview in the editor area; "open in editor" opens the file at the cited lines and shows the old revision
  in VS Code's own diff; follows the active colour theme; commands for working tree, staged changes, and a commit range.
- Standalone app: repository picker, ref pickers, PR URL input, recent list, offline mode with a local model, export of a
  view to Markdown or standalone HTML.

## 9. Core, models and configuration

- R-C1. One core library (TypeScript; decision D2) with: git access, tree-sitter parsing, language-server client, ledger store,
  generation and verification pipeline, and the renderer (framework-free web components so all three front ends embed it).
- R-C2. Model access is pluggable: Claude through the user's own API key or an enterprise gateway; a local model for offline
  use. The model never receives more than the ledger and the cited code needed for the call.
- R-C3. Languages at launch: Go, TypeScript, Python, Java. A file in another language is shown at L0 and L1-by-text only (R-V5).
- R-C4. `.diff-viz.yml` in the repository: ignore globs, generated-file globs, component map (path to component name and a
  one-line responsibility written by humans, which is then `stated`, checked against code), glossary entries, default settings.

## 10. Security and privacy

- R-S1. Read-only against the repository and the hosting service. No write scopes are requested. No comments, pushes or status
  changes.
- R-S2. Code and PR text are private. Only the ledger-building calls send code, only to the configured model endpoint, and the
  user is shown which. Tokens stay in the OS keychain or extension storage; never in logs or exports.
- R-S3. Fetched text (PR descriptions, tickets, comments) is data. Instructions inside it are ignored. This also applies to code
  comments and strings in the diff (prompt injection): the generation prompt marks them as quoted data.
- R-S4. People are referred to by role, not by name, in generated text (the skill's privacy rule). Secrets found in a diff are
  masked in every view and in the audit log, and flagged.
- R-S5. Telemetry is off by default; when on, it contains no code, no paths and no claim text.

## 11. Acceptance tests

A. Grounding. On a corpus of at least 30 real changes (with a seeded set of changes that have known pitfalls: format-only
   rewrites, renames, moved functions, a removed guard, a changed default), every shown claim passes R-V1 mechanically. A
   human audits a random 200 claims: at least 98 % are supported by the cited lines; 0 claims are labelled `verified` and
   wrong in the audited set (the release gate).
B. Honesty. On seeded changes that touch an external service or runtime-only behaviour, the tool marks the claim `unverified`
   in at least 95 % of the cases rather than stating it.
C. Disagreement. On changes whose PR text overstates the code (seeded), the disagreement entry appears.
D. Zoom. From L4, a user reaches the raw lines behind any claim in at most 4 steps, and always with the lines highlighted.
E. Determinism. The same two revisions, model and settings give the same ledger hash; the same ledger gives the same views.
F. Noise. A change that is only a formatter run is shown as a single folded block at every level above L0 and has 0 behaviour
   claims.
G. Parity. The same change and the same settings give the same blocks and labels in all three front ends.
H. Guided coverage. For every change in the corpus of test A, every hunk is owned by exactly one layer, no layer depends on a
   layer of another cohort, and reading the layers in order never shows a function before a layer that defines what it calls
   (checked against the call graph, not by a model).
K. Calm layout. In "Lead me", at the default settings, the screen has no more than three panels, one header line and one footer
   line; every item moved into a menu (R-U21a to R-U21j) is still reachable in at most two actions; no `inferred`, `stated`
   or `unverified` claim is folded.
I. Guided honesty. Every claim and every diagram edge shown in "Lead me" passes R-V1; a layer that has no structure worth a
   diagram has none; the end-of-route step lists 100 % of the `unverified` entries.
J. Never auto-advance. In a scripted session the view stays on one layer until a next, previous or jump action.

## 12. Phases

1. Core and standalone app: git input, parser, deterministic L0 and L1, ledger store.
2. Pass 1 generation and verification pipeline; L2 and L3 views.
3. L4 overview, settings, evidence panel, audit.
3a. Cohorts and layers in the ledger (R-L4), "Lead me" with J, K, Z, reviewed marks and conditional diagrams (section 4.3).
4. VS Code extension.
5. GitHub extension.
6. Local model, `.diff-viz.yml`, export, accessibility audit.

## 13. Open decisions

- D1. Electron or Tauri for the standalone app.
- D2. TypeScript for the whole core, or Rust for the parser and diff engine with a TypeScript shell.
- D3. Whether stated text from tickets (Jira, Notion, Slack) is in scope for version 1 or only the PR description.
- D4. Whether the verification model (R-V1.4) must be a different model from the generating one.
- D6. Cohort and layer naming: a model may name them (from ledger claims only), but should the grouping itself be computed by a
  deterministic graph clustering step, with the model only wording it? Preference: deterministic grouping.
- D7. Whether "Lead me" becomes the default for changes above a size threshold (for example 20 files), and what the threshold is.
- D5. Whether GitLab is in scope for version 1 (the qSpark group uses GitLab; the GitHub extension is as requested).

## 14. Glossary (terms used in this spec)

- Hunk: a contiguous block of changed lines in a diff, with a few lines of context around it.
- Symbol: a named code element a parser can find: function, method, type, constant, config key.
- tree-sitter: an incremental parser library that builds a syntax tree for many languages; used here for deterministic change
  detection.
- Language server: a process, per language, that answers "where is this defined" and "who references this" (the protocol behind
  editor navigation).
- Ledger: the list of claims, each with evidence and a label, that every abstract view is built from (section 4.1).
- Cohort: a group of changes with one purpose, independent of the other groups; read as a unit in "Lead me".
- Layer: one step inside a cohort, in reading order, owning specific line ranges and having its own summary.
- Change Stack: CodeRabbit's pull request review view that groups a change into cohorts and layers, with a three-panel layout
  and keys J, K and Z; the model for section 4.3.
- Webview: an embedded web page inside a VS Code panel.
