#!/usr/bin/env python3
"""Build the single-file mock: template/mock.html + diff.json + (verified) ledger.json -> mock.html.

Usage:
  build_mock.py DIFF_JSON LEDGER_JSON --out mock.html [--template PATH]

Use the output of `verify_ledger.py --apply` as LEDGER_JSON. Sections the ledger leaves out (hunks, symbols, components, pieces,
cohorts, layers) are filled with honest fallbacks: a hunk or layer with no claim says "not analysed". Claim ids that do not exist
are dropped from every view. The page is self-contained (no network), light and dark theme, about 100 KB plus the diff.
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def fill(diff, led):
    files = diff["files"]
    C = led.setdefault("claims", {})
    meta = led.setdefault("meta", {})
    meta.setdefault("title", "Change")
    meta.setdefault("repo", os.path.basename(os.getcwd()))
    meta.setdefault("base", diff["meta"].get("base", ""))
    meta.setdefault("head", diff["meta"].get("head", ""))
    keep = lambda ids: [i for i in ids if i in C]
    hunks_d = {h["id"]: (f, h) for f in files for h in f["hunks"]}
    # hunks
    have = {h["id"]: h for h in led.get("hunks", []) if h["id"] in hunks_d}
    led["hunks"] = []
    for f in files:
        for h in f["hunks"]:
            e = have.get(h["id"]) or {"id": h["id"], "text": (h["symbols"][0]["name"] + ": changed") if h["symbols"] else f["path"], "claims": []}
            e["claims"] = keep(e.get("claims", []))
            led["hunks"].append(e)
    # symbols, components, pieces
    if not led.get("symbols"):
        led["symbols"] = []
        for f in files:
            for h in f["hunks"]:
                names = [s for s in h["symbols"] if s["change"] != "context"] or h["symbols"][:1]
                nm = names[0]["name"] if names else f["path"].split("/")[-1]
                led["symbols"].append({"id": f"S{len(led['symbols']) + 1}", "name": nm, "file": f["path"], "sig": h["fn"] or f["path"],
                                       "kind": "format-only" if h["fmt"] else (names[0]["change"] if names else "modified"),
                                       "hunks": [h["id"]], "claims": [], "before": "not analysed", "after": "not analysed"})
    for s in led["symbols"]:
        s["claims"] = keep(s.get("claims", [])); s["hunks"] = [h for h in s.get("hunks", []) if h in hunks_d]
    if not led.get("components"):
        by = {}
        for s in led["symbols"]:
            by.setdefault(os.path.dirname(s["file"]) or ".", []).append(s["id"])
        led["components"] = [{"id": f"K{i + 1}", "name": d, "role": "not analysed", "desc": "Grouped by directory (no component was written).",
                              "claims": [], "syms": ids, "tests": "n/a", "risk": False, "terms": []} for i, (d, ids) in enumerate(by.items())]
    for k in led["components"]:
        k["claims"] = keep(k.get("claims", [])); k.setdefault("terms", [])
    if not led.get("pieces"):
        led["pieces"] = [{"id": f"P{i + 1}", "name": k["name"], "sub": f"{len(k['syms'])} symbol(s)", "comp": k["id"], "sym": k["syms"][0], "risk": False}
                         for i, k in enumerate(led["components"])]
    ch = led.setdefault("change", {})
    ch.setdefault("purpose", "No purpose was written for this change.")
    ch["stated"] = keep(ch.get("stated", [])); ch["risks"] = keep(ch.get("risks", []))
    if ch.get("flow") and ch["flow"].get("claim") not in C:
        ch["flow"].pop("claim", None)
    # cohorts and layers
    if not led.get("layers") or not led.get("cohorts"):
        led["layers"], groups = {}, {}
        for f in files:
            g = "Formatting and noise" if f["fmt_only"] or f["cls"] in ("generated", "lockfile", "vendored") else \
                "Tests" if f["cls"] == "test" else "Config and docs" if f["cls"] in ("config", "docs", "migration") else "Source"
            for h in f["hunks"]:
                lid = f"Y{len(led['layers']) + 1}"
                rng = {"file": f["path"]}
                if h["new_len"]: rng["new"] = [h["new_start"], h["new_start"] + h["new_len"] - 1]
                if h["old_len"]: rng["old"] = [h["old_start"], h["old_start"] + h["old_len"] - 1]
                hl = next((x for x in led["hunks"] if x["id"] == h["id"]), {"claims": [], "text": f["path"]})
                led["layers"][lid] = {"title": f"{os.path.basename(f['path'])} {h['header'].split('@@')[1].strip()}", "order": "Fallback order: diff order.",
                                      "sum": hl["text"] if hl["claims"] else "Not analysed: no claim was written for this hunk.",
                                      "claims": hl["claims"], "ranges": [rng]}
                groups.setdefault(g, []).append(lid)
        led["cohorts"] = [{"id": f"G{i + 1}", "name": n, "why": "Fallback grouping by file class.", "layers": ls} for i, (n, ls) in enumerate(groups.items())]
    for y in led["layers"].values():
        y["claims"] = keep(y.get("claims", []))
        if y.get("diagram"):
            y["diagram"]["built_from"] = keep(y["diagram"].get("built_from", []))
    for c in C.values():
        c["deps"] = keep(c.get("deps", [])); c.setdefault("ev", [])
    return led


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("diff"); ap.add_argument("ledger"); ap.add_argument("--out", required=True)
    ap.add_argument("--template", default=os.path.join(HERE, "..", "template", "mock.html"))
    a = ap.parse_args()
    diff = json.load(open(a.diff)); led = json.load(open(a.ledger))
    if "audit" not in led:
        print("warning: the ledger has no audit list; run verify_ledger.py --apply first", file=sys.stderr)
    led = fill(diff, led)
    payload = json.dumps({"diff": diff, "ledger": led}, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    tpl = open(a.template, encoding="utf-8").read()
    pat = re.compile(r'(<script type="application/json" id="dv-data">).*?(</script>)', re.S)
    if not pat.search(tpl):
        sys.exit("template has no dv-data script block")
    html = pat.sub(lambda m: m.group(1) + payload + m.group(2), tpl, count=1)
    open(a.out, "w", encoding="utf-8").write(html)
    print(f"{a.out}: {len(html) // 1024} KB, {len(led['claims'])} claims, {len(led['layers'])} layers")
    if len(html) > 8 * 1024 * 1024:
        print("warning: larger than 8 MB; consider --context 1 or a narrower range", file=sys.stderr)


if __name__ == "__main__":
    main()
