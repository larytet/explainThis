# diff-viz

- `REQUIREMENTS.md`: requirements specification (two passes from the explain-this skill: bottom-up ledger, top-down views).
- `mock/index.html`: interactive UI/UX mock (static, no build, illustrative data). Zoom with the slider, `0`-`4`, `+`/`-`,
  or ctrl+wheel; the "Lead me" button starts a guided walkthrough (cohorts of layers, one layer at a time; `J`/`K` step, `Z` focus mode, `Esc` leaves); `F7`/`F8` step through changes; the "front end" buttons show the GitHub, VS Code and standalone frames.

## Publish the mock with GitHub Pages

Repository Settings, Pages, Source: "Deploy from a branch", branch `main`, folder `/ (root)`. The mock is then at
`https://<owner>.github.io/<repo>/diff-viz/mock/`. The `.nojekyll` file in the repo root turns off Jekyll processing.
