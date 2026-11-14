#!/usr/bin/env python3
"""Mechanical verification of a diff-mock ledger (the R-V1 checks). No model, no network.

Usage:
  verify_ledger.py DIFF_JSON LEDGER_JSON [--apply OUT_JSON] [--json]

Without --apply it only reports. With --apply it writes OUT_JSON: the ledger with every claim that failed an evidence check
downgraded to `unverified` (never kept as a guess, R-V2), an `audit` list, and `meta.coverage`. Structural errors (a changed
line no layer owns, a missing hunk, a cohort that depends on another) cannot be repaired automatically: they are reported and
the exit code is 1.
Exit code: 0 clean (warnings allowed), 1 errors.
"""
import argparse, json, re, sys

RANK = {"unverified": 0, "inferred": 1, "stated": 2, "verified": 3}


class Diff:
    def __init__(self, d):
        self.files = {f["path"]: f for f in d["files"]}
        self.hunks = {h["id"]: (f, h) for f in d["files"] for h in f["hunks"]}
        self.new, self.old, self.changed = {}, {}, set()
        for f in d["files"]:
            p = f["path"]
            for h in f["hunks"]:
                for l in h["lines"]:
                    if l["n"] is not None:
                        self.new[(p, l["n"])] = (l["t"][1:], h["id"])
                    if l["o"] is not None:
                        self.old[(p, l["o"])] = (l["t"][1:], h["id"])
                    if l["t"][:1] in "+-":
                        self.changed.add((p, "n" if l["t"][0] == "+" else "o", l["n"] if l["t"][0] == "+" else l["o"]))

    def text(self, file, rev, a, b):
        m = self.new if rev == "new" else self.old
        got = [m[(file, i)] for i in range(a, b + 1) if (file, i) in m]
        return got, (b - a + 1)


def idents(claim):
    return re.findall(r"`([^`]+)`", claim)


def numbers(claim):
    plain = re.sub(r"`[^`]*`", " ", claim)
    return re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])", plain)


def has_token(text, tok):
    if re.search(r"\W", tok):
        return re.sub(r"\s+", " ", tok) in re.sub(r"\s+", " ", text)
    return re.search(rf"(?<![\w]){re.escape(tok)}(?![\w])", text) is not None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("diff"); ap.add_argument("ledger"); ap.add_argument("--apply"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    D = Diff(json.load(open(a.diff)))
    led = json.load(open(a.ledger))
    C = led.get("claims", {})
    errors, warns, audit = [], [], []          # errors: (kind, claim_id|None, message)
    failed = {}                                  # claim id -> reason (evidence-class failures)
    n_ranges = n_ok_ranges = n_ident = n_num = 0

    def err(kind, cid, msg):
        errors.append((kind, cid, msg))
        if cid and kind in ("evidence", "identifier", "number", "format", "label", "missing-why", "missing-src", "missing-evidence"):
            failed.setdefault(cid, msg)

    # ---- per-claim checks ----
    ev_text = {}
    for cid, c in C.items():
        lab = c.get("label")
        if lab not in RANK:
            err("schema", cid, f"label '{lab}' is not one of verified, inferred, stated, unverified"); continue
        if not c.get("claim"):
            err("schema", cid, "empty claim"); continue
        texts = []
        for e in c.get("ev", []):
            file, rev, x, y = e
            n_ranges += 1
            if file not in D.files:
                err("evidence", cid, f"cited file {file} is not in the diff"); continue
            got, want = D.text(file, rev, x, y)
            if not got:
                err("evidence", cid, f"{file} ({rev}) lines {x}-{y} are not in the diff (no cited line exists in the diff)"); continue
            if len(got) < want:
                warns.append(("evidence", cid, f"{file} ({rev}) {x}-{y}: only {len(got)} of {want} lines are in the diff; the rest cannot be checked"))
            n_ok_ranges += 1
            texts.append("\n".join(t for t, _ in got))
        ev_text[cid] = "\n".join(texts)
        if lab != "unverified" and not c.get("ev"):
            err("missing-evidence", cid, f"label {lab} needs at least one cited range")
        if lab == "inferred" and not c.get("why"):
            err("missing-why", cid, "an inferred claim must show its reasoning (`why`)")
        if lab == "stated" and not c.get("src"):
            err("missing-src", cid, "a stated claim must name its source (`src`)")
        for d in c.get("deps", []):
            if d not in C:
                err("schema", cid, f"depends_on {d} does not exist")
    # identifiers, numbers (may also be found in the evidence of the claims this one is built from)
    def reach(cid, seen=None):
        seen = seen or set()
        for d in C.get(cid, {}).get("deps", []):
            if d in C and d not in seen:
                seen.add(d); reach(d, seen)
        return seen
    for cid, c in C.items():
        if cid in failed or c.get("label") == "unverified" or "claim" not in c:
            continue
        pool = ev_text.get(cid, "") + "\n" + "\n".join(ev_text.get(d, "") for d in reach(cid))
        for tok in idents(c["claim"]):
            n_ident += 1
            if not has_token(pool, tok):
                err("identifier", cid, f"`{tok}` is named in the claim but appears in no cited line")
        for num in numbers(c["claim"]):
            n_num += 1
            if not has_token(pool, num):
                err("number", cid, f"the number {num} is in the claim but not in the cited lines")
    # cycles and label strength
    for cid, c in C.items():
        if cid in reach(cid):
            err("schema", cid, "depends_on forms a cycle")
        lab = c.get("label")
        if lab == "verified":
            weak = [d for d in c.get("deps", []) if d in C and RANK.get(C[d].get("label"), 0) < RANK["verified"] and C[d].get("label") != "stated"]
            if weak:
                err("label", cid, f"labelled verified but built from weaker claims {weak}; use inferred and give the reasoning (R-L2)")
    # format-only claims must agree with the parser (R-E5)
    hunk_has_fmt_claim = set()
    for cid, c in C.items():
        if c.get("kind") == "format-only" and c.get("label") != "unverified":
            for e in c.get("ev", []):
                got, _ = D.text(e[0], e[1], e[2], e[3])
                for hid in {h for _, h in got}:
                    hunk_has_fmt_claim.add(hid)
                    if not D.hunks[hid][1].get("fmt") and not D.hunks[hid][1].get("comment_only"):
                        err("format", cid, f"claims format-only, but the parser finds changed tokens in hunk {hid}")
    for hid, (f, h) in D.hunks.items():
        if h.get("fmt") and hid not in hunk_has_fmt_claim:
            warns.append(("format", None, f"hunk {hid} ({f['path']}) is whitespace-only by the parser but has no format-only claim"))

    # ---- structure ----
    seen_h = {}
    for h in led.get("hunks", []):
        if h["id"] not in D.hunks:
            err("structure", None, f"ledger hunk {h['id']} is not in the diff")
        seen_h[h["id"]] = seen_h.get(h["id"], 0) + 1
        for cid in h.get("claims", []):
            if cid not in C: err("structure", None, f"hunk {h['id']} cites unknown claim {cid}")
    for hid in D.hunks:
        if seen_h.get(hid, 0) != 1:
            err("structure", None, f"diff hunk {hid} appears {seen_h.get(hid, 0)} times in ledger.hunks (must be 1)")
    sym_ids = {s["id"] for s in led.get("symbols", [])}
    for s in led.get("symbols", []):
        for hid in s.get("hunks", []):
            if hid not in D.hunks: err("structure", None, f"symbol {s['id']} cites unknown hunk {hid}")
        for cid in s.get("claims", []):
            if cid not in C: err("structure", None, f"symbol {s['id']} cites unknown claim {cid}")
    comp_ids = {k["id"] for k in led.get("components", [])}
    for k in led.get("components", []):
        for sid in k.get("syms", []):
            if sid not in sym_ids: err("structure", None, f"component {k['id']} cites unknown symbol {sid}")
        for cid in k.get("claims", []):
            if cid not in C: err("structure", None, f"component {k['id']} cites unknown claim {cid}")
    for p in led.get("pieces", []):
        if p.get("comp") not in comp_ids: err("structure", None, f"piece {p['id']} cites unknown component {p.get('comp')}")
        if p.get("sym") and p["sym"] not in sym_ids: err("structure", None, f"piece {p['id']} cites unknown symbol {p['sym']}")
    ch = led.get("change", {})
    for key in ("stated", "risks"):
        for cid in ch.get(key, []):
            if cid not in C: err("structure", None, f"change.{key} cites unknown claim {cid}")
    if ch.get("flow", {}).get("claim") and ch["flow"]["claim"] not in C:
        err("structure", None, "change.flow cites an unknown claim")

    # ---- cohorts and layers (R-GR1, R-GR2, R-GR2a, R-L4) ----
    layers = led.get("layers", {})
    owner = {}
    for cohort in led.get("cohorts", []):
        for lid in cohort.get("layers", []):
            if lid not in layers: err("layers", None, f"cohort {cohort['id']} cites unknown layer {lid}")
            elif lid in owner: err("layers", None, f"layer {lid} is in two cohorts")
            else: owner[lid] = cohort["id"]
    for lid in layers:
        if lid not in owner: err("layers", None, f"layer {lid} belongs to no cohort")
    line_owner = {}
    for lid, y in layers.items():
        for cid in y.get("claims", []):
            if cid not in C: err("layers", None, f"layer {lid} cites unknown claim {cid}")
        if not y.get("sum"): err("layers", None, f"layer {lid} has no summary")
        if not y.get("order"): warns.append(("layers", None, f"layer {lid} has no order_reason (`order`)"))
        for r in y.get("ranges", []):
            if r["file"] not in D.files:
                err("layers", None, f"layer {lid} owns lines of {r['file']}, which is not in the diff"); continue
            for kind, key in (("n", "new"), ("o", "old")):
                if key in r:
                    for i in range(r[key][0], r[key][1] + 1):
                        if (r["file"], kind, i) in D.changed:
                            line_owner.setdefault((r["file"], kind, i), []).append(lid)
    unowned = sorted(k for k in D.changed if k not in line_owner)
    dup = sorted(k for k, v in line_owner.items() if len(set(v)) > 1)
    for k in unowned[:8]:
        err("coverage", None, f"changed line {k[0]}:{k[2]} ({'added' if k[1]=='n' else 'removed'}) is owned by no layer")
    if len(unowned) > 8: err("coverage", None, f"... and {len(unowned) - 8} more unowned changed lines")
    for k in dup[:8]:
        err("coverage", None, f"changed line {k[0]}:{k[2]} is owned by layers {sorted(set(line_owner[k]))}")
    # claim -> layer; cross-cohort and order
    claim_layer = {}
    for lid, y in layers.items():
        for cid in y.get("claims", []):
            claim_layer.setdefault(cid, lid)
    order_of = {lid: i for co in led.get("cohorts", []) for i, lid in enumerate(co.get("layers", []))}
    for lid, y in layers.items():
        for cid in y.get("claims", []):
            for d in reach(cid):
                dl = claim_layer.get(d)
                if dl and dl != lid:
                    if owner.get(dl) != owner.get(lid):
                        err("layers", None, f"layer {lid} (cohort {owner.get(lid)}) depends on layer {dl} (cohort {owner.get(dl)}): cohorts must be independent")
                    elif order_of.get(dl, 0) > order_of.get(lid, 0):
                        err("layers", None, f"layer {lid} is read before layer {dl}, which its claim {cid} is built from (reading order)")
        dg = y.get("diagram")
        if dg:
            if dg.get("type") not in ("flow", "state", "sequence", "er"): err("diagram", None, f"layer {lid}: diagram type must be flow, state, sequence or er")
            bf = [c for c in dg.get("built_from", []) if c in C]
            if not bf: err("diagram", None, f"layer {lid}: a diagram must list the claims it is built from")
            pool = "\n".join(ev_text.get(c, "") for c in dg.get("built_from", []))
            labels = []
            for e in dg.get("edges", []): labels += [e[0], e[1]]
            for m in dg.get("messages", []): labels += [m[0], m[1], m[2]]
            for s in dg.get("states", []) + dg.get("participants", []): labels.append(s)
            for ent in dg.get("entities", []): labels += [ent["name"]] + ent.get("fields", [])
            bad = []
            for lab in labels:
                for tok in re.findall(r"\b([A-Za-z_]\w*)(?=\()|\b([A-Za-z]+[A-Z]\w*|\w+_\w+)\b", lab):
                    t = tok[0] or tok[1]
                    if t and t not in bad and not has_token(pool, t):
                        bad.append(t)
                        err("diagram", None, f"layer {lid}: diagram names `{t}`, which is not in the evidence of {dg.get('built_from')}")
    # orphans
    used = set(c for h in led.get("hunks", []) for c in h.get("claims", [])) | set(c for y in layers.values() for c in y.get("claims", [])) \
        | set(c for s in led.get("symbols", []) for c in s.get("claims", [])) | set(c for k in led.get("components", []) for c in k.get("claims", [])) \
        | set(ch.get("stated", []) + ch.get("risks", [])) | ({ch["flow"]["claim"]} if ch.get("flow", {}).get("claim") else set())
    for cid in C:
        if cid not in used: warns.append(("orphan", cid, "claim is not shown in any view"))

    # ---- coverage meter (R-V6) ----
    covered = set()
    for cid, c in C.items():
        if c.get("label") in ("verified", "inferred") and cid not in failed:
            for e in c.get("ev", []):
                for i in range(e[2], e[3] + 1):
                    k = (e[0], "n" if e[1] == "new" else "o", i)
                    if k in D.changed: covered.add(k)
    cov = {"covered": len(covered), "total": len(D.changed), "unverified_claims": sum(1 for c in C.values() if c.get("label") == "unverified")}

    # ---- audit ----
    audit += led.get("dropped", [])
    for cid, why in failed.items():
        audit.append(f"Downgraded to unverified: {cid} - {why}.")
    audit.append(f"Checked: {n_ok_ranges} of {n_ranges} cited ranges exist; {n_ident} named identifiers and {n_num} numbers looked up in the cited lines; "
                 f"{len(D.changed) - len(unowned)} of {len(D.changed)} changed lines are owned by a layer.")

    if a.apply:
        out = json.loads(json.dumps(led))
        for cid, why in failed.items():
            c = out["claims"][cid]
            c["ev_failed"], c["ev"], c["label"] = c.get("ev", []), [], "unverified"
            c["reason"] = why
        out["audit"] = audit
        out.setdefault("meta", {})["coverage"] = cov
        json.dump(out, open(a.apply, "w"), indent=1, ensure_ascii=False)
    if a.json:
        print(json.dumps({"errors": errors, "warnings": warns, "audit": audit, "coverage": cov}, indent=1))
    else:
        for k, cid, m in errors: print(f"ERROR   [{k}] {cid + ': ' if cid else ''}{m}")
        for k, cid, m in warns: print(f"warning [{k}] {cid + ': ' if cid else ''}{m}")
        print(f"{len(errors)} errors, {len(warns)} warnings; {len(C)} claims, {len(layers)} layers; "
              f"{cov['covered']} of {cov['total']} changed lines have a verified or inferred entry")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
