# explainThis

A Claude Code skill that explains a large subsystem or module top-down, piece by piece. Each piece is reviewed bottom-up
first, so every statement in the explanation is backed by code that was actually read. After each piece it stops and waits
for your follow-up questions.

## Skill

`.claude/skills/explain-this/SKILL.md`

How it works:

1. Maps the subsystem and proposes an ordered list of pieces.
2. For each piece, reviews the code from the leaves upward before writing anything.
3. Presents the piece top-down, with a `file:line` reference on every claim, labelled verified, inferred or unverified.
4. Re-checks each citation against the code before sending.
5. Stops and waits for follow-up questions or "next".

It is read-only and never edits the code it explains.

## Use

Open Claude Code in this repo, or copy `.claude/skills/explain-this` to `~/.claude/skills/` to use it anywhere, then ask:

```
/explain-this internal/auth
```
