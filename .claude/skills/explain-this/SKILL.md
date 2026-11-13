---
name: explain-this
description: Explain a large subsystem or module top-down, one piece at a time, where every statement is backed by a bottom-up review of the actual code, and stop after each piece to take follow-up questions. Use when the user asks to understand, walk through, or get oriented in a subsystem, module, package or directory ("explain this module", "walk me through X", "help me understand how Y works").
---

# explain-this

Explain a subsystem to the user top-down, piece by piece. Before presenting each piece, review its code bottom-up so that every claim is grounded in something you read. After each piece, stop and wait for the user.

The user is trying to rebuild their own understanding of code they may not have written (often AI-generated). A confident but wrong explanation is worse than none. Prefer "I could not verify this" over a plausible guess.

This skill is read-only. Do not edit, format or refactor the code being explained.

## Inputs

The user names a subsystem, module, package or directory. If it is ambiguous, ask once which path or entry point is meant. Ask for their level (new to the language, new to the codebase, or just new to this module) only if it is not obvious; default to an experienced engineer who has not seen this code.

## Phase 0: map the territory

1. List the files in scope with sizes. Identify entry points (main, handlers, public API, exported symbols, registered routes, CLI commands), configuration, tests and docs.
2. Build the dependency picture: who calls whom, which modules import which. Use the language's tooling or grep; read the code to confirm what a tool reports.
3. Check git history for scope (`git log --oneline -- <path>`, recent churn) and for any design docs, READMEs or spec files that describe intent.
4. Split the subsystem into **pieces**. A piece is a unit that can be explained in one sitting: a component, layer, or flow, small enough to hold in one answer (roughly 100 to 600 lines of code behind it). Order the pieces top-down: the overview and entry points first, then the components they use, then the shared leaves.
5. Present the outline to the user: the pieces in order, with one line each and the files behind each. Mention anything you could not map (generated code, dynamic dispatch, reflection, external services). Then begin with piece 1 without waiting, unless the outline revealed something the user must decide.

## Phase 1: for each piece, review bottom-up first

Do the review before writing the explanation. Work from the leaves of the piece upward:

1. Read the lowest-level functions, types and constants first: the ones that call nothing else in the piece.
2. For each, write private notes: what it does, inputs and outputs, side effects, error handling, invariants it relies on, with `file:line`.
3. Move up one level. For each caller, read it and the notes on what it calls, and write what the composition does. Note where a caller assumes something the callee does not guarantee.
4. Read the tests for the piece. Tests show intended behavior; note where code and tests disagree, and where behavior is untested.
5. Read the git history for the piece when it affects understanding (a surprising workaround, a recent rewrite).
6. Keep a ledger of each claim you intend to make, with its evidence.

## Phase 2: present the piece top-down

Write the explanation from the top: purpose first, then structure, then the details, in this order:

1. **Purpose**: what this piece is for and where it sits in the whole subsystem.
2. **How it works**: the main flow, then the parts, each tied to the pieces you explained earlier where relevant.
3. **Key details and decisions**: invariants, error handling, concurrency, data shapes, anything surprising.
4. **What I could not determine**: unknowns, assumptions and anything inferred rather than read.

### Evidence rules

Every statement about the code must carry a `file:line` reference (or a range). Label the strength of each claim:

- **Verified**: the cited lines directly state or implement it.
- **Inferred**: it follows from cited lines by reasoning that you spell out in the same sentence. Say "inferred".
- **Unverified**: you could not confirm it from the code (intent, behavior of an external service, runtime-only behavior). Say so, or leave it out.

Never describe intent, design rationale or performance as fact unless a comment, doc, commit message or test states it; cite that source when it does. Do not describe what code "should" do as what it does.

### Verification pass

Before sending, re-read each cited location and check that the claim matches the code as it is now. Fix or drop any claim that does not hold. If a claim depends on code you did not read, either read it or downgrade the claim.

## Phase 3: stop

End each piece with:

1. A short recap (two to four lines) of what was established.
2. The open questions: what you could not verify and what the user may want to dig into.
3. A line stating progress ("piece 2 of 7: <name>") and the next piece's name.
4. An explicit invitation: ask follow-up questions, or say "next" to continue.

Then **stop and wait**. Do not start the next piece, and do not offer to "continue automatically". Do not make tool calls after the invitation.

## Handling follow-up questions

Answer them with the same standard: read the relevant code, cite `file:line`, label verified, inferred and unverified. If a question needs a part of the subsystem you have not yet reviewed, review it bottom-up first and say so. If an answer corrects something you said earlier, say that plainly and state which earlier claim was wrong.

Stay on the current piece until the user says to move on. When they say "next" (or name a piece), repeat Phases 1 to 3 for that piece. The user may reorder, skip, split or merge pieces; update the outline and keep the running progress line accurate.

## Finishing

After the last piece, give a short synthesis: how the pieces fit together, the main flows, and the list of everything left unverified across the whole walkthrough. Offer, but do not start, follow-ups such as a refactoring assessment or a test-gap review.
