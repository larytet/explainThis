#!/usr/bin/env python3
"""Deterministic diff parser for the diff-mock skill. No model, no network.

Turns a unified diff (git range, working tree, patch file, stdin) or a chunk of code (treated as all added) into
diff.json: files, hunks, numbered lines, language, class, format-only and comment-only flags, best-effort symbols.

Usage:
  parse_diff.py --git-range BASE..HEAD [--repo DIR] [--context 3] [--out diff.json]
  parse_diff.py --worktree [--staged] [--repo DIR]
  parse_diff.py --patch FILE|-
  parse_diff.py --code FILE [FILE ...]

Symbols are heuristic (regular expressions per language family, plus the function context git prints in the hunk
header). They are a starting point for the ledger; the model must check each against the cited lines.
"""
import argparse, json, os, re, subprocess, sys

LANG = {
    ".py": "python", ".pyi": "python", ".go": "go", ".rs": "rust", ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp",
    ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp", ".hxx": "cpp", ".java": "java", ".kt": "kotlin", ".kts": "kotlin",
    ".cs": "csharp", ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js", ".ts": "ts", ".tsx": "ts", ".swift": "swift",
    ".php": "php", ".rb": "ruby", ".scala": "scala", ".proto": "proto", ".sql": "sql", ".sh": "shell", ".bash": "shell",
    ".yaml": "yaml", ".yml": "yaml", ".json": "json", ".toml": "toml", ".md": "markdown", ".rst": "docs", ".html": "html",
    ".css": "css", ".lua": "lua", ".dart": "dart", ".m": "objc", ".mm": "objc", ".zig": "zig", ".ex": "elixir",
    ".exs": "elixir", ".hs": "haskell", ".ml": "ocaml", ".r": "r", ".jl": "julia", ".tf": "terraform", ".gradle": "gradle",
}
COMMENT = {  # line-comment prefixes per language
    "python": ["#"], "ruby": ["#"], "shell": ["#"], "yaml": ["#"], "toml": ["#"], "terraform": ["#"], "r": ["#"],
    "sql": ["--"], "lua": ["--"], "haskell": ["--"], "elixir": ["#"], "julia": ["#"],
}
for _l in ("go", "rust", "c", "cpp", "java", "kotlin", "csharp", "js", "ts", "swift", "php", "scala", "proto", "dart",
           "objc", "zig", "gradle", "css"):
    COMMENT[_l] = ["//", "/*", "*", "*/"]

SYM = {  # (regex, kind label) per language family; group 1 is the name
    "python": [(r"^\s*(?:async\s+)?def\s+(\w+)", "function"), (r"^\s*class\s+(\w+)", "class")],
    "go": [(r"^func\s+(?:\([^)]*\)\s*)?(\w+)", "function"), (r"^type\s+(\w+)", "type"), (r"^\s*(\w+)\s+(?:struct|interface)\b", "type")],
    "rust": [(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)", "function"),
             (r"^\s*(?:pub\s+)?(?:struct|enum|trait|union)\s+(\w+)", "type"), (r"^\s*impl(?:<[^>]*>)?\s+(?:\w+\s+for\s+)?(\w+)", "impl")],
    "js": [(r"\bfunction\s*\*?\s*(\w+)", "function"), (r"\bclass\s+(\w+)", "class"),
           (r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>", "function"),
           (r"^\s*(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{\s*$", "method")],
    "ts": [(r"\bfunction\s*\*?\s*(\w+)", "function"), (r"\b(?:class|interface|enum)\s+(\w+)", "type"), (r"^\s*(?:export\s+)?type\s+(\w+)\s*=", "type"),
           (r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*(?::[^=]+)?=>", "function"),
           (r"^\s*(?:public\s+|private\s+|protected\s+|static\s+|async\s+)*(\w+)\s*\([^)]*\)\s*(?::\s*[^{]+)?\{\s*$", "method")],
    "java": [(r"\b(?:class|interface|enum|record)\s+(\w+)", "type"),
             (r"^\s*(?:(?:public|private|protected|static|final|abstract|synchronized|default|native)\s+)+[\w<>\[\],.?\s]+?\s(\w+)\s*\([^;]*$", "method")],
    "kotlin": [(r"\bfun\s+(?:<[^>]*>\s*)?(?:[\w.]+\.)?(\w+)", "function"), (r"\b(?:class|interface|object|enum class)\s+(\w+)", "type")],
    "csharp": [(r"\b(?:class|interface|enum|struct|record)\s+(\w+)", "type"),
               (r"^\s*(?:(?:public|private|protected|internal|static|virtual|override|abstract|async|sealed)\s+)+[\w<>\[\],.?\s]+?\s(\w+)\s*\([^;]*$", "method")],
    "swift": [(r"\bfunc\s+(\w+)", "function"), (r"\b(?:class|struct|enum|protocol|extension)\s+(\w+)", "type")],
    "php": [(r"\bfunction\s+(\w+)", "function"), (r"\b(?:class|interface|trait)\s+(\w+)", "type")],
    "ruby": [(r"^\s*def\s+(?:self\.)?(\w+[?!=]?)", "function"), (r"^\s*(?:class|module)\s+(\w+)", "class")],
    "scala": [(r"\bdef\s+(\w+)", "function"), (r"\b(?:class|object|trait)\s+(\w+)", "type")],
    "proto": [(r"^\s*(?:message|enum|service)\s+(\w+)", "type"), (r"^\s*rpc\s+(\w+)", "function")],
    "sql": [(r"(?i)create\s+(?:or\s+replace\s+)?(?:table|view|function|procedure|index)\s+(?:if\s+not\s+exists\s+)?([\w.\"]+)", "object"),
            (r"(?i)alter\s+table\s+([\w.\"]+)", "object")],
    "shell": [(r"^\s*(?:function\s+)?(\w+)\s*\(\)\s*\{?", "function")],
    "lua": [(r"\bfunction\s+([\w.:]+)", "function")],
    "dart": [(r"\bclass\s+(\w+)", "type")],
    "terraform": [(r'^\s*(?:resource|module|variable|output|data)\s+"([^"]+)"(?:\s+"([^"]+)")?', "resource")],
    "yaml": [], "json": [], "toml": [], "markdown": [], "docs": [], "html": [], "css": [(r"^\s*([.#]?[\w-]+)\s*\{", "rule")],
}
SYM["c"] = SYM["cpp"] = [
    (r"\b(?:class|struct|enum(?:\s+class)?|union|namespace)\s+(\w+)", "type"),
    (r"^[\w:<>,*&~\s]*?[\s*&:](~?\w+)\s*\([^;]*?\)?\s*(?:const|noexcept|override|final|\s)*(?:\{|$)", "function"),
]
SYM["objc"] = SYM["cpp"]
SYM["zig"] = [(r"\bfn\s+(\w+)", "function")]
NOT_FUNCS = {"if", "for", "while", "switch", "return", "else", "catch", "sizeof", "do", "case", "defined", "throw", "new",
             "delete", "using", "typedef", "elif", "when", "match", "with", "assert"}


def classify(path):
    p = path.lower()
    base = os.path.basename(p)
    if base in ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "go.sum", "cargo.lock", "poetry.lock", "pipfile.lock",
                "gemfile.lock", "composer.lock", "uv.lock"):
        return "lockfile"
    if re.search(r"(^|/)(vendor|node_modules|third_party|thirdparty)/", p):
        return "vendored"
    if re.search(r"(\.pb\.go|_pb2(_grpc)?\.py|\.min\.(js|css)|\.generated\.\w+|\.g\.dart)$|(^|/)(generated|gen|__generated__)/", p):
        return "generated"
    if re.search(r"(^|/)(tests?|spec|specs|__tests__|testing)/|_test\.\w+$|\.test\.\w+$|\.spec\.\w+$|(^|/)test_[^/]*$|tests?\.\w+$", p):
        return "test"
    if re.search(r"(^|/)(migrations?|db/migrate)/", p):
        return "migration"
    if p.endswith((".md", ".rst", ".txt", ".adoc")) or re.search(r"(^|/)docs?/", p) or base in ("readme", "license", "changelog"):
        return "docs"
    if p.endswith((".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf", ".env", ".properties", ".tf", ".gradle")) \
            or base in ("makefile", "dockerfile", "cmakelists.txt", ".gitignore") or p.startswith(".github/"):
        return "config"
    return "source"


def lang_of(path):
    base = os.path.basename(path)
    if base.lower() == "makefile":
        return "make"
    if base.lower() == "dockerfile":
        return "docker"
    return LANG.get(os.path.splitext(path)[1].lower(), "text")


def find_symbols(lang, hunk_lines, fn_ctx):
    """Best-effort symbols whose definition line appears in the hunk (added, removed or context)."""
    pats = SYM.get(lang) or []
    seen = {}
    def scan(text, side):
        for rx, kind in pats:
            m = re.search(rx, text)
            if not m:
                continue
            name = next((g for g in m.groups() if g), None)
            if not name or name in NOT_FUNCS or name.isdigit():
                continue
            seen.setdefault(name, {"name": name, "kind_of": kind, "sides": set()})["sides"].add(side)
            return
    for ln in hunk_lines:
        scan(ln["t"][1:], {"+": "add", "-": "del"}.get(ln["t"][:1], "ctx"))
    out = []
    for s in seen.values():
        sides = s["sides"]
        change = "added" if sides == {"add"} else "removed" if sides == {"del"} else "modified" if sides & {"add", "del"} else "context"
        out.append({"name": s["name"], "kind_of": s["kind_of"], "change": change})
    if fn_ctx:
        for rx, kind in pats:
            m = re.search(rx, fn_ctx)
            if m:
                name = next((g for g in m.groups() if g), None)
                if name and name not in NOT_FUNCS and not any(o["name"] == name for o in out):
                    out.append({"name": name, "kind_of": kind, "change": "context"})
                break
    return out


def flags(lang, lines):
    rem = [l["t"][1:] for l in lines if l["t"][:1] == "-"]
    add = [l["t"][1:] for l in lines if l["t"][:1] == "+"]
    squash = lambda xs: re.sub(r"\s+", "", "".join(xs))
    fmt = bool(rem) and bool(add) and squash(rem) == squash(add)
    if not fmt and (rem or add) and not (rem and add):
        fmt = all(not x.strip() for x in (rem or add))      # only blank lines added or removed
    cm = COMMENT.get(lang)
    comment_only = False
    if cm and not fmt and (rem or add):
        comment_only = all((not x.strip()) or any(x.strip().startswith(c) for c in cm) for x in rem + add)
    return fmt, comment_only


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")


def parse_patch(text):
    """State machine: header lines until a hunk starts, then the hunk's declared line counts say when it ends."""
    files, cur, hunk = [], None, None
    rem_o = rem_n = 0
    for raw in text.splitlines():
        if hunk is not None and (rem_o > 0 or rem_n > 0):
            tag = raw[:1]
            if raw.startswith("\\"):
                continue
            if tag == "+":
                hunk["lines"].append({"o": None, "n": hunk["_n"], "t": raw}); hunk["_n"] += 1; rem_n -= 1
            elif tag == "-":
                hunk["lines"].append({"o": hunk["_o"], "n": None, "t": raw}); hunk["_o"] += 1; rem_o -= 1
            else:
                hunk["lines"].append({"o": hunk["_o"], "n": hunk["_n"], "t": " " + raw[1:]})
                hunk["_o"] += 1; hunk["_n"] += 1; rem_o -= 1; rem_n -= 1
            continue
        hunk = None
        if raw.startswith("diff --git "):
            m = re.match(r"diff --git a/(.*?) b/(.*)$", raw)
            cur = {"path": m.group(2) if m else raw[11:], "old_path": m.group(1) if m else None, "status": "modified",
                   "hunks": [], "binary": False, "mode": None, "_git": True}
            files.append(cur)
        elif raw.startswith("--- ") and (cur is None or not cur.get("_git") or cur["hunks"] or cur.get("_seen_old")):
            # plain unified diff (no "diff --git" line), or a second file in one
            if cur is None or not cur.get("_git") or cur["hunks"]:
                cur = {"path": None, "old_path": None, "status": "modified", "hunks": [], "binary": False, "mode": None}
                files.append(cur)
            p = raw[4:].split("\t")[0]
            cur["old_path"] = None if p == "/dev/null" else re.sub(r"^a/", "", p)
            cur["status"] = "added" if p == "/dev/null" else cur["status"]
            cur["_seen_old"] = True
        elif raw.startswith("--- ") and cur is not None:
            p = raw[4:].split("\t")[0]
            cur["status"] = "added" if p == "/dev/null" else cur["status"]
            cur["_seen_old"] = True
        elif raw.startswith("+++ ") and cur is not None:
            p = raw[4:].split("\t")[0]
            if p == "/dev/null":
                cur["status"] = "deleted"
            else:
                cur["path"] = re.sub(r"^b/", "", p)
        elif cur is not None and raw.startswith("rename from "):
            cur["old_path"] = raw[12:]; cur["status"] = "renamed"
        elif cur is not None and raw.startswith("rename to "):
            cur["path"] = raw[10:]
        elif cur is not None and raw.startswith("new file mode"):
            cur["status"] = "added"
        elif cur is not None and raw.startswith("deleted file mode"):
            cur["status"] = "deleted"
        elif cur is not None and (raw.startswith("Binary files") or raw.startswith("GIT binary patch")):
            cur["binary"] = True
        else:
            m = HUNK_RE.match(raw)
            if m and cur is not None:
                o, n = int(m.group(1)), int(m.group(3))
                ol = int(m.group(2)) if m.group(2) is not None else 1
                nl = int(m.group(4)) if m.group(4) is not None else 1
                hunk = {"old_start": o, "old_len": ol, "new_start": n, "new_len": nl, "header": raw,
                        "fn": m.group(5).strip(), "lines": [], "_o": o, "_n": n}
                rem_o, rem_n = ol, nl
                cur["hunks"].append(hunk)
    return files


def finish(files, source):
    out, hid = [], 0
    for f in files:
        if not f.get("path"):
            continue
        lang = lang_of(f["path"])
        added = removed = 0
        hunks = []
        for h in f["hunks"]:
            hid += 1
            for l in h["lines"]:
                added += l["t"][:1] == "+"; removed += l["t"][:1] == "-"
            fmt, cmt = flags(lang, h["lines"])
            hunks.append({"id": f"H{hid}", "header": h["header"], "fn": h["fn"], "old_start": h["old_start"],
                          "old_len": h["old_len"], "new_start": h["new_start"], "new_len": h["new_len"],
                          "fmt": fmt, "comment_only": cmt, "symbols": find_symbols(lang, h["lines"], h["fn"]), "lines": h["lines"]})
        out.append({"path": f["path"], "old_path": f["old_path"] if f["old_path"] != f["path"] else None,
                    "status": f["status"], "binary": f["binary"], "lang": lang, "cls": classify(f["path"]),
                    "added": added, "removed": removed, "fmt_only": bool(hunks) and all(h["fmt"] for h in hunks), "hunks": hunks})
    return {"meta": {**source, "files": len(out), "hunks": hid, "added": sum(f["added"] for f in out),
                     "removed": sum(f["removed"] for f in out)}, "files": out}


def run_git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, errors="replace")
    if r.returncode:
        sys.exit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def code_as_diff(paths):
    files = []
    for p in paths:
        txt = open(p, encoding="utf-8", errors="replace").read().splitlines()
        lines = [{"o": None, "n": i + 1, "t": "+" + t} for i, t in enumerate(txt)]
        files.append({"path": p, "old_path": None, "status": "added", "binary": False, "mode": None,
                      "hunks": [{"old_start": 0, "old_len": 0, "new_start": 1, "new_len": len(txt), "header": f"@@ -0,0 +1,{len(txt)} @@",
                                 "fn": "", "lines": lines, "_open": False}]})
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--git-range"); g.add_argument("--worktree", action="store_true"); g.add_argument("--patch"); g.add_argument("--code", nargs="+")
    ap.add_argument("--staged", action="store_true"); ap.add_argument("--repo", default="."); ap.add_argument("--context", type=int, default=3)
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    meta = {}
    if a.git_range:
        text = run_git(a.repo, "diff", f"-U{a.context}", "--no-color", "-M", a.git_range)
        base, _, head = a.git_range.replace("...", "..").partition("..")
        meta = {"source": "git-range", "range": a.git_range, "base": base, "head": head or "HEAD",
                "commits": [c for c in run_git(a.repo, "log", "--format=%h %s", a.git_range.replace("...", "..")).splitlines()]}
        files = parse_patch(text)
    elif a.worktree:
        text = run_git(a.repo, "diff", f"-U{a.context}", "--no-color", "-M", *(["--cached"] if a.staged else ["HEAD"]))
        meta = {"source": "staged" if a.staged else "worktree"}
        files = parse_patch(text)
    elif a.patch:
        text = sys.stdin.read() if a.patch == "-" else open(a.patch, encoding="utf-8", errors="replace").read()
        meta = {"source": "patch"}
        files = parse_patch(text)
    else:
        meta = {"source": "code"}
        files = code_as_diff(a.code)
    res = finish(files, meta)
    if not res["files"]:
        sys.exit("no changes found in the input")
    data = json.dumps(res, indent=1, ensure_ascii=False)
    if a.out == "-":
        print(data)
    else:
        open(a.out, "w", encoding="utf-8").write(data)
        print(f"{a.out}: {res['meta']['files']} files, {res['meta']['hunks']} hunks, +{res['meta']['added']} -{res['meta']['removed']}")


if __name__ == "__main__":
    main()
