---
name: stale-check
description: Review a spec, skill, mock, roadmap, design or code for being out of date or resting on stale assumptions about AI/tooling. Extracts the high-level system requirements, matches each against what is available today (commercial or free), and flags parts that sit in a busy niche, can be replaced by an off-the-shelf product or a model feature, or could be better or cheaper with a different approach. Use when the user asks "is this out of date", "stale check", "what could we rent instead of build", "kill review", "what assumptions does this make", or before committing to a build-vs-buy, self-hosting or multi-month plan.
---

# stale-check

Idea from Claudio Lupi, "AI Is Now Building AI Twice as Fast. The Evidence Is Redacted." (Medium, 2026-11): the technology under a plan
is now the volatile variable. Capability per dollar moves in months, so an 18-month plan written in spring had 5 of 14 assumptions
false by autumn. The useful question is not "is AI accelerating" but "how fast are my assumptions expiring".

This skill answers that for one artifact: a spec, a skill, a mock, a roadmap, a design doc or a code base.

## Hard rules

- **Never judge "what is available today" from memory.** Model names, prices, limits and features go stale fastest. Check with
  WebSearch/WebFetch (use `extended` mode for niche or recent facts) and cite the URL and the date you saw it. If you cannot check,
  mark the line `UNVERIFIED` and say so; do not guess a price or a release.
- **Tag every external claim with lineage**: `audited` (independent, data visible), `reproduced` (you ran it), `vendor` (vendor
  claim, e.g. a benchmark or a price list), or `unverified`. A number with no lineage is an opinion with formatting.
- **Do not recommend replacing something you have not read.** Quote the lines (`file:line`) that make the assumption.
- **A flag is a question, not a verdict.** Say what would have to be true for the replacement to be better (cost, quality, data
  residency, lock-in, team skill) and what you could not check.
- **Today's date goes in the report.** Everything in it expires; say when.

## Method

1. **Fix the artifact and its date.** Read it whole (or the named part). Note when it was written (git log, header, file date).
   The gap between that date and today sets how suspicious to be: more than 3 months for pricing or capability, more than 6 for
   anything else.
2. **Extract the high-level requirements.** In the user's words, no implementation: what outcome does the system exist to produce,
   for whom, at what volume, with what limits (latency, privacy, cost, accuracy). Write 3 to 8 lines. If a requirement is unclear,
   ask the user or mark it `OPEN:`; do not invent it.
3. **Extract the assumptions.** For each place the artifact depends on a fact about the world, write one row for the register:
   assumption, `file:line`, evidence in the artifact (if any), date, expiry. Look for these classes:
   - **Pricing and cost**: per-token or per-seat prices, "self-hosting is cheaper than the API at our volume", budgets.
   - **Capability**: "models cannot do X", context-window limits, hand-written workarounds for weak reasoning, chunking, retries
     and prompt scaffolding that exist only to cover a model weakness.
   - **Model and library names and versions**: pinned model IDs, deprecated SDK calls, removed flags, old API shapes.
   - **Build-versus-buy**: anything built in house that is now a product, a managed service, an open-source project or a
     provider feature (RAG, evals, guardrails, agent loops, OCR, transcription, search, memory, tool-calling glue).
   - **Vendor bets**: single-vendor lock-in, a vendor that has since changed terms, merged, or lost ground.
   - **Process**: manual steps, human review gates and plan horizons that assume the old speed of change.
4. **Match each requirement to what exists now.** For each, search for what is available today, commercial and free: provider
   features, managed services, open-source projects and open-weight models. Record 1 to 3 candidates with price/licence, date seen,
   source URL and lineage tag.
5. **Classify each requirement/assumption** as one of:
   - `HOLDS`: still true, evidence checked.
   - `STALE`: false or changed, with the evidence.
   - `COMMODITY`: a busy niche, many competing products or a provider feature covers it; building it is likely waste.
   - `REPLACEABLE`: a specific product or approach does the same job (name it).
   - `IMPROVABLE`: works, but a different approach is cheaper or better (smaller model, batch or cached calls, fewer tokens,
     deterministic code instead of a model call, a model call instead of brittle rules).
   - `UNVERIFIED`: could not check.
6. **Sort decisions by reversibility.** For every one-way door (multi-year contract, self-hosted platform, team or tooling built
   around one vendor), apply the test: *would this still be a good decision if capability per dollar doubled twice before it pays
   back?* Say yes, no or unknown, and why.
7. **Report.** Do not rewrite the artifact. Write the report (format below) and stop; the user decides what to change.

## Report format

- **Artifact, date written, date checked.**
- **Requirements** (3 to 8 lines).
- **Findings table**, worst first: class, `file:line`, what it assumes, what exists now, source + date + lineage tag, what would
  have to be true to switch, effort/risk of switching.
- **Kill list**: things built or planned that a release has made, or probably soon makes, unnecessary.
- **One-way doors that fail the doubling test.**
- **What I could not check.**
- **Assumption register**: the rows from step 3 with expiry dates (pricing/capability 3 months, organisational longer), ready to
  paste into the repo. When an assumption expires, anything depending on it needs a re-review.

Keep it short. A busy reader should get the top three findings from the first screen.

## Not in scope

Correctness bugs (use code-review), spec gaps (use idsd), security (use security-review). This skill is only about what the world
has moved past.
