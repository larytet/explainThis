# Ledger schema (ledger.json)

One JSON object. Ids are strings. `ev` ranges are `[file, "new"|"old", from, to]` (inclusive line numbers on that revision, as in
`diff.json`). `ranges` (layers, symbols) are `{ "file", "new": [from, to], "old": [from, to] }`; both keys optional: `new` owns added lines
(and shows context lines) by new-side number, `old` owns removed lines by old-side number.

```
{
 "meta":   { "title", "repo", "base", "head", "pr" },        // pr: PR title or commit subject, for the "stated" comparison
 "claims": { "C1": Claim, ... },
 "hunks":  [ { "id": "H1", "text": "one line of intent", "claims": ["C1"] }, ... ],     // exactly one per diff hunk, diff order
 "symbols":    [ Symbol ],     "components": [ Component ],     "pieces": [ Piece ],     "change": Change,
 "cohorts": [ { "id", "name", "why", "layers": ["Y1","Y2"] } ],
 "layers":  { "Y1": Layer, ... },
 "glossary": [ ["term", "definition"], ... ],
 "dropped":  [ "claims written and removed, with the reason" ]
}
```

Claim
```
{ "label": "verified"|"inferred"|"stated"|"unverified",
  "lvl": "hunk"|"symbol"|"component"|"change",          // highest level it may appear at
  "kind": "behavior"|"interface"|"risk"|"test-gap"|"format-only"|"disagreement"|"unknown"|"test",
  "claim": "One sentence. `identifiers` in backticks must occur in the cited lines; numbers too.",
  "ev": [ ["payment/client.go","new",20,28] ],           // required unless unverified
  "deps": ["C1"],                                         // claims it is built from; never stronger than the weakest
  "why": "required when inferred: the steps from evidence to claim",
  "src": "required when stated: PR title, ticket key, doc (and whether the code agrees)" }
```
Symbol: `{ id, name, file, sig, kind: added|removed|modified|moved|renamed|format-only, hunks: ["H2"], ranges?: [...], claims, before, after }`
Component: `{ id, name, role, desc, claims, syms: ["S1"], tests, risk: bool, terms: ["glossary term"] }`
Piece (outline entry): `{ id, name, sub, comp, sym, risk }`
Change: `{ purpose, graph: [{n, chg?}], flow: {text, claim?}, stated: [claim ids], risks: [claim ids] }`
Layer
```
{ "title", "order": "why it is read at this position (names a real dependency)", "sum": "at most two lines",
  "claims": ["C1"], "ranges": [ {file, new?, old?} ],
  "diagram": null | { "type": "flow", "caption", "built_from": ["C1"], "edges": [[from, to, label]] }
              | { "type": "state", ..., "edges": [[from, to, event]] }
              | { "type": "sequence", ..., "participants": [..], "messages": [[from, to, text]] }
              | { "type": "er", ..., "entities": [{name, fields}], "relations": [[a, b, label]] } }
```

A diagram `caption` is one short phrase; the page adds "Built from ..." itself, so do not repeat it.

Rules the verifier enforces: every cited range exists in the diff; named identifiers and numbers occur in the cited lines (or those of
`deps`); `inferred` has `why`, `stated` has `src`, non-unverified has evidence; no `verified` claim built from a weaker claim; no cycles;
a `format-only` claim only on a hunk the parser marked whitespace-only or comment-only; every diff hunk listed once in `hunks`; every
changed line owned by exactly one layer; every layer in one cohort; no layer depends on a layer of another cohort or on a later one in
its own cohort; diagram nodes that look like identifiers occur in the evidence of `built_from`.
