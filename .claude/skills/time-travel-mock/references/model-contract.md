# Engine contract (what the page script expects from `<script id="engine">`)

The page (UI script in `template/index.html`) is generic. Everything example-specific lives in the engine block: listings, thread
programs, op semantics, workloads, schedules, chapters. Replace that block; do not edit the UI unless the example needs a new panel.
`scripts/check_contract.mjs` verifies the shapes and soundness below.

Export (`const Engine = ...; if (typeof module !== 'undefined') module.exports = Engine;` so node can load it):

| Name | Shape |
|---|---|
| `THREADS`, `ACTORS` | e.g. `['A','B']`, `['A','B','T']` (`T` = the clock jumps to the next timer; drop it if nothing is timed) |
| `VARIANTS` | `{id: {id, n, name, short, tag, blurb, file, src:[{t,id}], scopes:[[fromId,toId]], prog:[{id,k,lines:[ids],title,holds?}], idx, lineNo}}`. `src` comes from lines ending `//@lineId`; the marker is stripped from `t`. `lineNo`/`idx` are derived after construction. |
| `WORKLOADS` | `{id: {id, name, desc, keys:{A,B}, cache0, lat, val}}`: explicit, shared by all variants |
| `SCHEDULES` | `{id: {id, name, seq, then, note}}`: preference per step, then fallback order (letters from `ACTORS`) |
| `CHAPTERS` | `[{id,title,variant,workload,sched,from,to:int|'end',tab,q,a:(ctx)=>html, free?, codeTab?}]`, `ctx = {m: metrics, agg: aggregate, ...}` |
| `init(variant, workload)` | initial state (plain JSON-able object; must survive `structuredClone`) |
| `runnable(s, actor)` | `{ok, kind, reason, by?}`; `reason` explains every refusal in one sentence naming who or what blocks |
| `status(s, thread)` | `{kind:'ready'\|'blocked'\|'timer'\|'done', label, text}` |
| `step(s, actor)` | `{state, event}`; throws (with `.info = runnable result`) if not runnable; never mutates `s` |
| `event` | `{actor, op, k, title, text, lines:[lineIds], t0, t1, flags, concl:[model conclusions], blocks, wakes, dup?, hold?}` |
| `replay(v, w, choices)` | `{states, events}`: state k is a pure function of the first k choices |
| `pick(s, sched, i)`, `autoRun(v, w, schedId, from)` | schedule policy and run-to-end |
| `metrics(s)` | `{lookups, dups, waitA, waitB, waitMutex, waitFuture, finish, makespan, ...}` (rename for your domain, keep the page's counters in sync) |
| `aggregate(s)` | memoised exhaustive exploration of every legal schedule: `{paths, dead, dupPaths, ...}` |

Soundness rules the checker enforces: every variant x workload x named schedule terminates; no reachable deadlock over all
orderings; replay of every prefix equals the incremental fold; time is monotone; every refusal has a reason and throws; every
line id used exists; chapter cursors are in range; chapter text renders. Write domain claims (the headline conclusions) in a
`claims.mjs` module and run with `--claims`; every sentence the page prints that quotes a number must come from `metrics` or
`aggregate`, never be typed in by hand.

## Adapting the template to a different example

- **Same shape (threads, locks, caches, in-flight work, timers):** change the listings, programs, op handlers, workloads,
  schedules and chapters. Keep the `Supplied / Simulated / Model / Assumption` labels.
- **Different mechanism (state machine, retry/backoff timeline, transaction isolation, event ordering):** keep the UI layout,
  the replay-from-choices design, the inspector, timeline, rejection messages, ledger and checks, and rewrite the engine and the
  resource cards (`renderLanes`). Keep the rule that state is a function of the choice list.
- **Not a good fit:** see "Triage" in `SKILL.md`; say so and use `diff-mock` or plain prose instead.
