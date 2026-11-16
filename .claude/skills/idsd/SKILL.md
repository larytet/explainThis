---
name: idsd
description: Intent-Driven Software Development (IDSD, the ICE method - Intent, Context, Expectations). Use to turn a vague request, ticket or feature idea into one well-formed Intent (five parts) with its Expectations, to find where an agent would still have to guess, and to run the build loop with the human staying in it. Use when the user asks for an intent, expectations, "idsd", "ICE", "close the holes", "write this as an intent instead of a spec", or is about to hand an outcome to a coding agent.
---

# idsd

Method from Kapil Viren Ahuja, "The Method That Replaces Spec-Driven Development - IDSD" (Medium, 2026-05-20).

Spec-driven development fails because one document, written however the keyboard-holder felt that morning, is asked to be the
intent, the definition of done, the workflow and the context at once. Every gap in it is filled by the agent, silently.
IDSD splits it by craft and by owner:

| Craft        | What it is                                                         | Owner                        |
|--------------|--------------------------------------------------------------------|------------------------------|
| Intent       | The outcome the human wants. No stack, no service names.            | Human, always                |
| Expectations | The boundary: when it counts as done, when it failed, the limits.   | Same human who owns the intent |
| Context      | The how: tech, existing system, codebase constraints.               | The harness, fed progressively |

The loop: human gives Intent + Expectations -> harness pulls Context, codes, validates against Expectations -> not met, go again
-> met, merge. The human never hands off the first two and is present while the loop runs, not only at the diff.

This skill makes the human's two crafts hard to skip. It does not invent them.

## Hard rules

- **Never fill a hole yourself.** If the intent, a constraint, a failure scenario or a link is unknown, ask the user or mark it
  `OPEN:` in the file. A plausible guess written into an intent is exactly the failure IDSD exists to prevent.
- **Intent contains no implementation.** No framework, table, endpoint or service name. Words the user would recognise.
  If one is needed to make sense, it belongs in Context, not here.
- **Expectations are in the user's terms**, written as scenarios, not as code or test names.
- **Do not write Context into the intent files.** Pull it from the repo at build time and cite it; keep it out of the human's files.
- **Stay a loop participant.** During a build, stop and report at each validation round (see Phase 4); do not run to the end alone.

## The five parts of an intent

An intent is not one sentence. All five must be present, or the agent fills the gap:

1. **Wanted** - what is wanted, as an outcome.
2. **Constraints** - the limits around it (size, stock, budget, who, when, compliance).
3. **Failure scenarios** - concrete situations in which it has failed.
4. **Success scenarios** - concrete situations in which it has succeeded.
5. **Connections** - links to the other intents it touches, so a change here is traceable to everything it affects.

Worked example (keep as the model of grain and size):

```
# INT-shoe-under-90: Buy a red shoe for under $90

Wanted:       A buyer can buy a red shoe that costs under $90.
Constraints:  In the buyer's size. In stock. Deliverable to the buyer. Price under $90 at checkout, not only at listing.
Fails when:   A $140 shoe is offered. An out-of-stock shoe is offered. A non-red shoe is offered.
Succeeds when: The buyer adds an affordable red shoe in their size to the cart and checks out.
Connects to:  INT-pricing, INT-inventory, INT-checkout (a change in any of these changes this).
```

## Phases

### Phase 1: pick one outcome

Take one real outcome about to be built, not the system. If the user brings a large request, split it into outcomes and work
the first (or the one they name). Say which you took. One intent per file.

### Phase 2: draft the intent

1. Find existing intents (`intents/`, `docs/intents/`, `INT-*.md`) so connections can name real IDs. Never invent a link to an
   intent that does not exist; write `OPEN: link to <thing>?` or propose creating it.
2. Write the five parts from what the user said, quoting their words where possible. Anything not said by the user and not
   derivable from their words is an `OPEN:` line with a specific question.
3. Save as `intents/INT-<slug>.md` (or the repo's existing convention) with the five headings above and `Owner: <user>`.

### Phase 3: guess-hunt, then expectations

**Guess-hunt.** Re-read the intent as someone who was not in the user's head and list every place an agent would still have to
guess. Present them as numbered questions, each one pointing at the sentence that leaves the hole. Typical holes: unstated
bounds ("under" - inclusive? which currency, before or after tax?), who the actor is, what happens at zero or at the limit,
what "available" means, whose data, which of two connected intents wins on conflict. Close those, not the whole system.
Update the intent with the user's answers; remaining unknowns stay `OPEN:`.

**Expectations.** Once the holes the user cares about are closed, write `intents/INT-<slug>.expectations.md`:

- *Done when* - scenarios in which the result counts as done (from the success scenarios, made checkable).
- *Failed when* - scenarios in which it has failed (from the failure scenarios).
- *Limits* - what the result must stay inside (from the constraints), including what must not change in connected intents.

Each line is something the user would recognise and a validator could check. Keep it short. Show it to the user and get their
OK; expectations the user has not seen are the agent deciding "done" for them.

Do not proceed to Phase 4 while any `OPEN:` remains that affects done/failed, unless the user says to.

### Phase 4: run the loop with the human in it

Only when the user asks to build. Hand off intent + expectations; pull Context yourself, progressively, from the repo (cite
`file:line`; never paste a wall of it up front).

For each round:

1. Implement the smallest slice that moves toward the expectations.
2. Validate against each Done/Failed/Limits line. Run real tests or checks where they exist; say plainly which lines were
   checked by running something, which by reading, and which not at all.
3. **Report to the user**: lines met, lines not met, any new hole found, any decision you were about to make that belongs to the
   intent or expectations. Stop for those decisions; do not choose for them.
4. If not met, go again. When all lines are met and the user has seen it, the code is ready to merge.

A new hole found mid-build goes back into the intent/expectations (user-approved edit), not into the code as an assumption.

## Output

- Intent files and expectations files in the repo, as above.
- In chat: which outcome was taken, the guess-hunt questions, and what is still `OPEN:`. Short; the files carry the content.
- Hard-wrap prose at about 120 characters. Define any term the user may not know at first use.

## Checklist before saying "ready"

- [ ] All five parts present, none empty, none containing implementation.
- [ ] Every connection names an intent that exists (or is flagged OPEN).
- [ ] Guess-hunt done and the user answered or deferred each question.
- [ ] Expectations written in the user's terms and seen by the user.
- [ ] No `OPEN:` left that changes what done or failed means.
