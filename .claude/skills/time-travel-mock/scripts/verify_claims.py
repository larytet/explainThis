#!/usr/bin/env python3
"""Check the evidence ledger of a time-travel mock (no model involved).

usage: verify_claims.py claims.json [--root DIR]

claims.json: {"sources": {"name": "path/relative/to/root"},
              "claims": {"M1": {"label": "verified|inferred|assumed|unverified", "text": "...",
                                 "ev": [["name", from, to], ...],      # 1-based inclusive lines in the SUPPLIED source
                                 "why": "required for inferred", "deps": ["M2"]}}}
Rules (the same discipline as diff-mock): every `backticked identifier` and every number in a verified claim must occur in its cited
lines; inferred claims need `why` and evidence; assumed/unverified claims must not cite evidence as if it proved them;
a claim is never stronger than the claims it depends on. Exit 1 on any error.
"""
import json, re, sys, os
RANK = {"verified": 3, "inferred": 2, "assumed": 1, "unverified": 0}
def main():
    a = sys.argv[1:]
    if not a: print(__doc__); return 2
    root = a[a.index("--root") + 1] if "--root" in a else os.path.dirname(os.path.abspath(a[0]))
    d = json.load(open(a[0])); errs = []; warn = []
    src = {}
    for k, p in d.get("sources", {}).items():
        src[k] = open(os.path.join(root, p), encoding="utf-8").read().split("\n")
    cl = d.get("claims", {})
    for cid, c in cl.items():
        lab = c.get("label")
        if lab not in RANK: errs.append(f"{cid}: bad label {lab!r}"); continue
        text = c.get("text", "")
        cited = []
        for ev in c.get("ev", []):
            n, f, t = ev
            if n not in src: errs.append(f"{cid}: unknown source {n!r}"); continue
            if not (1 <= f <= t <= len(src[n])): errs.append(f"{cid}: lines {f}-{t} outside {n} ({len(src[n])} lines)"); continue
            cited += src[n][f - 1:t]
        blob = "\n".join(cited)
        if lab in ("verified", "inferred") and not c.get("ev"): errs.append(f"{cid}: {lab} claim without evidence")
        if lab == "inferred" and not c.get("why"): errs.append(f"{cid}: inferred claim needs `why`")
        if lab in ("assumed", "unverified") and c.get("ev"): warn.append(f"{cid}: {lab} claim cites lines; fine for context, but they do not prove it")
        if lab == "verified":
            for ident in re.findall(r"`([^`]+)`", text):
                if ident not in blob: errs.append(f"{cid}: `{ident}` not in cited lines")
            for num in re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])", re.sub(r"`[^`]*`", "", text)):
                if num not in blob: errs.append(f"{cid}: number {num} not in cited lines")
        for dep in c.get("deps", []):
            if dep not in cl: errs.append(f"{cid}: dep {dep} missing")
            elif RANK.get(cl[dep].get("label"), 0) < RANK[lab]: errs.append(f"{cid}: {lab} but depends on weaker {dep} ({cl[dep].get('label')})")
    counts = {l: sum(1 for c in cl.values() if c.get("label") == l) for l in RANK}
    for w in warn: print("warning:", w)
    for e in errs: print("ERROR:", e)
    print(f"{len(cl)} claims {counts}; {len(errs)} errors, {len(warn)} warnings")
    return 1 if errs else 0
sys.exit(main())
