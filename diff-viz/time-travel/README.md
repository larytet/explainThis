# Way Beyond Compare: Time-Travel Edition (mock)

A code diff turned into an explanation of runtime behaviour: C++ on the left, two thread lanes, a mutex, a cache, an in-flight
table and expensive lookups on the right, stepped one event at a time, with rewind.

**What it is:** a deterministic simulation of one hand-written C++ example (a resolver cache, three implementations).
**What it is not:** it does not parse, compile, run or analyse C++. Every event on the page comes from a small state machine
written to mirror the three listings. Simulated time is in made-up units and is not a benchmark.

## Open it

No build, no backend, no network. From the repository root:

```
xdg-open diff-viz/time-travel/index.html      # Linux; on macOS: open ...; or double-click the file
```

or serve it (not needed in Chrome, the only browser tested; the page is one file with inline scripts):

```
python3 -m http.server 8000      # then open http://localhost:8000/diff-viz/time-travel/
```

After GitHub Pages is on (see `diff-viz/README.md`) it is at `/diff-viz/time-travel/`.

Deep links: `?step=4&reveal=1` opens guide step 4 with its answer shown; `?explore=1` skips the intro.
Keyboard (also under the `?` button): `Space` play/pause, `→`/`←` step/back, `A` `B` run that thread next, `T` advance the clock,
`R` reset, `Home`/`End`, `N`/`P` next/previous guide step. Every control and every timeline event is a focusable button.
Reduced motion is honoured (`prefers-reduced-motion`, plus a button): no transitions, and Play jumps to the end.

## Presenter walkthrough (about 4 minutes)

Click **Start the demo**, then **Reveal** / **Next** through the guide. The strongest reveal is steps 3 to 5:

1. **The PR** (step 1). Say it out loud: "every access to `map_` is under a mutex, tests pass". Ask: is it correct?
2. **The schedule tests see** (step 2). A finishes, then B: 1 lookup. Looks fine.
3. **Both miss** (step 3). Pause at the question: "A has missed and the lock is free. What does B see?" Reveal: the same miss.
4. **Duplicate lookup** (step 4). Reveal: B starts a second lookup of the same key. The banner turns red, the timeline shows two
   lookups running at once, and the inspector says why: the lock was released between `get()` and `put()`.
   Point at the lock row in the timeline: it is free for the entire time both lookups run. That is the whole bug.
5. **When does it happen?** (step 6). Press `A`/`B` yourself. The banner says whether a duplicate is still avoidable from the
   current state, checked over every legal ordering of the model: 544 of 546 orderings duplicate. Rewind with `←` or the slider.
6. **Fix 1, coarse lock** (steps 7, 8). Same schedule: B is blocked on `mu_`, 1 lookup. Then the price: with an unrelated key,
   B waits behind a lookup it has nothing to do with.
7. **Fix 2, per-key coalescing** (steps 9, 10). B joins A's `shared_future`: 1 lookup; and with a different key B proceeds alone.
8. **Compare and limits** (step 11). The Compare tab shows all three on the same workload; Model and limits says what none of it
   proves, including that coalescing is not a complete answer (a throwing lookup leaves a broken in-flight entry).

## What is supplied, simulated, concluded, assumed

Labels used on the page (colours follow the existing diff-viz evidence labels):

| Label | Meaning |
|---|---|
| Supplied (green) | The C++ text, shown verbatim, with line numbers. |
| Simulated (blue) | An event, state or counter produced by the state machine. |
| Model (amber) | A conclusion that holds for the model only, e.g. "no duplicate is possible from here", checked over every legal schedule. |
| Assumption (red) | Not modelled or invented for the demo: simulated time, two threads, one global clock, no memory model. |

State machine (in `<script id="engine">`, no DOM): a state is `{now, mu, cache, inflight, futs, lookups, threads}`; an event is
one `step(state, actor)` with actor `A`, `B` or `T` (let the clock jump to the next lookup completion). A run is only its list of
choices (`A B B A T ...`). Rewind, scrub and variant switching rebuild state by replaying that list from the initial state.
Lookups are timers; a thread's next step is blocked when its lock is held (`mu_`) or its shared future is not set. The
engine asserts that every cache access happens while the thread owns `mu_`.

Simulated time (units): cache operation 1; lock, unlock, future wait and `set_value` 0; `slow_lookup("db.internal")` 100;
`slow_lookup("cdn.internal")` 20. One global clock, so cache operations never overlap; lookups do. "Waiting" counts only time
blocked on `mu_` or on a shared lookup; a thread you simply did not step is descheduled, not waiting.

Omitted production concerns (also on the page, "Model and limits"): error propagation and cleanup of in-flight entries
(a throwing `slow_lookup` in variant 3 leaves a broken `inflight_` entry), timeouts, cancellation and shutdown, eviction, TTL,
negative caching, expiry stampedes, more than two threads, contention on the single mutex.

"Export proposed regression test" opens a **specification and sketch, not runnable code**, derived from the model.

## What was verified

| Check | How to run | Covers |
|---|---|---|
| Engine | `node diff-viz/time-travel/check.mjs` | Every variant x workload x named schedule finishes with correct results; **no deadlock in any legal schedule** (exhaustive, memoised); the three headline claims over all schedules; rejection of impossible steps with the reason; every prefix replay equals an incremental run; time and counters monotone; 540 random schedules; every guided chapter's cursor and facts. |
| Browser | open `index.html?selftest` (title becomes `SELFTEST PASS`; results are in a `<pre id="selftest">`), or `google-chrome --headless=new --virtual-time-budget=20000 --dump-dom "file://$PWD/diff-viz/time-travel/index.html?selftest"` | Drives the real DOM: stepping, rewinding, scrubbing, clicking events, rejected steps, branching, switching variants, all 11 guide steps, keyboard keys, focus retention, reduced motion; counters, lane status, mutex and cache cards and highlighted lines are compared with a fresh replay of the engine. |
| Real C++ cross-check | below | The exact listings shown on the page compile (`-Wall -Wextra`, no warnings) and, with real threads and a gate on `slow_lookup`, behave as the model says. **Not shown on the page and not part of its evidence.** |

```
OUT=$(mktemp -d)
node diff-viz/time-travel/check.mjs "$OUT/inc"      # also writes variant1.inc .. variant3.inc, the text shown on the page
for n in 1 2 3; do
  g++ -std=c++17 -Wall -Wextra -pthread -DVARIANT_FILE="\"$OUT/inc/variant$n.inc\"" diff-viz/time-travel/cpp/harness.cpp -o "$OUT/h$n" && echo "== variant $n" && "$OUT/h$n"
done
```

Result on the machine used (g++ 11.4, Linux, one run; the cases use bounded waits of 300 ms):

| | same key, first lookup held open | unrelated key while a lookup is open | lookup throws, then retry |
|---|---|---|---|
| 1 per-operation | 2 lookups | B returns | retry succeeds (2 lookups) |
| 2 coarse | 1 lookup | B does **not** return in 300 ms | retry succeeds (2 lookups) |
| 3 coalescing | 1 lookup | B returns | **retry throws `broken_promise`, no new lookup** |

Not checked: the stale-miss schedule against real C++ (it needs a pause between `get()` and `put()` that the listing has no seam
for); the page on Firefox or Safari, and on a real phone (only a narrow headless window and the light and dark themes in Chrome
146 were looked at); screen-reader behaviour (labels and roles are present but it was not tried with one).

## What a later real C++ tracing implementation would need

Replace the hand-written state machine with events recorded from an actual run, and say so on the page:

1. **A schedule you can control.** Real threads do not offer "step B next". Either instrument synchronisation points (a
   deterministic scheduler or ThreadSanitizer-style interception of mutex, condition-variable, atomic and future operations), or
   inject seams (an injectable lookup, test gates) and record what happens. Without control only the observed schedule can be shown.
2. **A trace format** with thread, operation, object (which mutex), source location (file and line), a timestamp or logical
   clock, and a happens-before relation. The page's event model (`actor, op, lines, t0, t1`, lock owner, waiters) is a subset.
3. **Source mapping** from addresses to the lines highlighted (debug info), so the code panel shows the real source.
4. **Real time kept apart from logical order.** Show measured times labelled as measurements from one run, never mixed with the
   simulated units used here, and say how many runs they come from.
5. **Honest coverage.** A trace shows one or a few schedules. "No duplicate is possible" needs systematic exploration
   (a model checker or stateless exploration such as CHESS or `rr chaos`) and a bound on what was explored; a single clean run proves nothing.
6. **An analysis step that does not guess.** Deciding that a change involves a check-then-act race, and which variables or locks
   matter, has to come from the code and the trace, with evidence cited, not from a template. Not every diff warrants a concurrency
   simulation, and the page should not be generated for one that does not.
